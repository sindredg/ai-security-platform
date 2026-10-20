"""The job program, with a fake Goose and a stub model server.

A whole job runs as a subprocess, with one end of a socket pair as its
standard input and output, as systemd gives it the connection.
"""

import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import agent_job

TOKEN = "ab" * 32
JOB = {
    "job": "job-1",
    "token": TOKEN,
    "task": "Is F-0001 confirmed?",
    "max_turns": 6,
    "seconds": 60,
}

# Prints a transcript with one tool call, as Goose's --output-format json
# does. FAKE_MODE changes what it does. It records its arguments and the
# recipe it was given, so the tests can read them.
FAKE_GOOSE = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys, time
    mode = os.environ.get("FAKE_MODE", "{mode}")
    recipe = sys.argv[sys.argv.index("--recipe") + 1]
    with open(os.path.join(os.environ["HOME"], "seen.json"), "w") as f:
        json.dump({{"argv": sys.argv[1:], "recipe": json.load(open(recipe)),
                   "env": dict(os.environ)}}, f)
    if mode == "sleep":
        time.sleep(60)
    if mode == "fail":
        print("model unreachable", file=sys.stderr)
        sys.exit(1)
    print("warning: token {token} in a log line", file=sys.stderr)
    print(json.dumps({{"messages": [
        {{"role": "user", "content": [{{"type": "text", "text": "task"}}]}},
        {{"role": "assistant", "content": [{{"type": "toolRequest",
            "toolCall": {{"value": {{"name": "tools__get_evidence"}}}}}}]}},
        {{"role": "user", "content": [{{"type": "toolResponse",
            "toolResult": {{"status": "success", "value": {{}}}}}}]}},
        {{"role": "assistant", "content": [{{"type": "text", "text": "Confirmed."}}]}},
    ], "metadata": {{"status": "completed", "input_tokens": 700, "output_tokens": 40}}}}))
    """
)


class Erases(BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def do_POST(self):
        Erases.seen.append(self.path)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.server = HTTPServer(("127.0.0.1", 0), Erases)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        Erases.seen = []

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def fake_goose(self, mode="ok"):
        path = self.tmp / "goose"
        path.write_text(
            FAKE_GOOSE.format(python=sys.executable, mode=mode, token=TOKEN)
        )
        path.chmod(0o755)
        return path

    def start(self, mode="ok"):
        """Start the job program as systemd would. Returns (process, our end)."""
        system = self.tmp / "system.txt"
        system.write_text("You investigate security findings.")
        ours, theirs = socket.socketpair()
        env = {
            "AISEC_GOOSE": str(self.fake_goose(mode)),
            "AISEC_SYSTEM": str(system),
            "AISEC_WORK": str(self.tmp / "job"),
            "AISEC_MODEL_URL": f"http://127.0.0.1:{self.server.server_port}",
            "PATH": os.environ["PATH"],
        }
        process = subprocess.Popen(
            [sys.executable, "-I", str(HERE / "agent_job.py")],
            stdin=theirs,
            stdout=theirs,
            stderr=subprocess.PIPE,
            env=env,
        )
        theirs.close()
        return process, ours

    def run_job(self, line, mode="ok"):
        process, ours = self.start(mode)
        with ours:
            ours.sendall(line)
            data = b""
            while chunk := ours.recv(65536):
                data += chunk
        process.wait(timeout=30)
        process.stderr.close()
        return process.returncode, data

    def seen(self):
        return json.loads((self.tmp / "job" / "seen.json").read_text())


class TheJobLine(unittest.TestCase):
    def test_a_valid_job_passes(self):
        self.assertEqual(agent_job.parse_job(json.dumps(JOB)), JOB)

    def test_each_bad_job_is_refused(self):
        bad = {
            "not JSON": "{",
            "a list": "[]",
            "a field missing": json.dumps(
                {k: v for k, v in JOB.items() if k != "task"}
            ),
            "a field added": json.dumps({**JOB, "tool_url": "https://elsewhere"}),
            "an upper-case ID": json.dumps({**JOB, "job": "Job-1"}),
            "an ID with a slash": json.dumps({**JOB, "job": "../x"}),
            "an ID too long": json.dumps({**JOB, "job": "a" * 64}),
            "a short token": json.dumps({**JOB, "token": "ab" * 31}),
            "a token in upper case": json.dumps({**JOB, "token": "AB" * 32}),
            "an empty task": json.dumps({**JOB, "task": ""}),
            "a task too long": json.dumps({**JOB, "task": "x" * 8001}),
            "turns as a bool": json.dumps({**JOB, "max_turns": True}),
            "turns as text": json.dumps({**JOB, "max_turns": "6"}),
            "no turns": json.dumps({**JOB, "max_turns": 0}),
            "too many turns": json.dumps({**JOB, "max_turns": 21}),
            "too few seconds": json.dumps({**JOB, "seconds": 59}),
            "too many seconds": json.dumps({**JOB, "seconds": 1201}),
        }
        for name, line in bad.items():
            with self.subTest(name), self.assertRaises(agent_job.Refused):
                agent_job.parse_job(line)

    def test_a_line_over_the_limit_is_refused_before_it_is_parsed(self):
        read, write = os.pipe()
        os.write(write, b"x" * 20000)
        os.close(write)
        with self.assertRaisesRegex(agent_job.Refused, "too long"):
            agent_job.read_line(read, agent_job.JOB_BYTES)

    def test_input_that_ends_before_a_newline_is_refused(self):
        read, write = os.pipe()
        os.write(write, b'{"job": "x"')
        os.close(write)
        with self.assertRaisesRegex(agent_job.Refused, "ended"):
            agent_job.read_line(read, agent_job.JOB_BYTES)


class TheRecipe(unittest.TestCase):
    def test_the_token_is_a_header_for_the_fixed_tool_service_only(self):
        path = Path(tempfile.mkdtemp()) / "recipe.json"
        agent_job.write_recipe(JOB, "system text", path)
        recipe = json.loads(path.read_text())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(recipe["prompt"], JOB["task"])
        self.assertEqual(recipe["instructions"], "system text")
        (extension,) = recipe["extensions"]
        self.assertEqual(extension["type"], "streamable_http")
        self.assertEqual(
            extension["uri"], "https://tool-service.aisec.internal:30443/mcp"
        )
        self.assertEqual(extension["headers"], {"Authorization": "Bearer " + TOKEN})

    def test_an_existing_recipe_is_not_overwritten(self):
        path = Path(tempfile.mkdtemp()) / "recipe.json"
        path.write_text("{}")
        with self.assertRaises(FileExistsError):
            agent_job.write_recipe(JOB, "system text", path)


class AWholeJob(Base):
    def test_a_completed_job_returns_one_result_line(self):
        code, data = self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertEqual(code, 0)
        self.assertTrue(data.endswith(b"\n"))
        result = json.loads(data)
        self.assertEqual(result["job"], "job-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual((result["tool_calls"], result["tool_errors"]), (1, 0))
        self.assertEqual(result["answer"], "Confirmed.")
        self.assertEqual(result["input_tokens"], 700)

    def test_goose_gets_the_recipe_and_no_token_on_its_command_line(self):
        self.run_job(json.dumps(JOB).encode() + b"\n")
        seen = self.seen()
        self.assertNotIn(TOKEN, " ".join(seen["argv"]))
        self.assertNotIn(TOKEN, json.dumps(seen["env"]))
        self.assertIn("--max-turns", seen["argv"])
        self.assertEqual(seen["argv"][seen["argv"].index("--max-turns") + 1], "6")
        self.assertEqual(
            seen["recipe"]["extensions"][0]["headers"]["Authorization"],
            "Bearer " + TOKEN,
        )
        self.assertEqual(seen["env"]["SSL_CERT_FILE"], "/etc/aisec/tool-service.crt")

    def test_the_recipe_is_gone_and_the_slot_erased_afterwards(self):
        self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertFalse((self.tmp / "job" / "recipe.json").exists())
        self.assertEqual(Erases.seen, ["/slots/0?action=erase"])

    def test_the_token_never_comes_back_in_the_result(self):
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertNotIn(TOKEN.encode(), data)
        self.assertIn("[token]", json.loads(data)["stderr_tail"])

    def test_a_goose_that_fails_gives_a_failed_result(self):
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n", mode="fail")
        result = json.loads(data)
        self.assertEqual((result["status"], result["exit_code"]), ("failed", 1))
        self.assertIn("model unreachable", result["stderr_tail"])
        self.assertEqual(Erases.seen, ["/slots/0?action=erase"])

    def test_a_bad_job_line_is_refused_and_starts_nothing(self):
        code, data = self.run_job(b'{"job": "x"}\n')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(data)["status"], "refused")
        self.assertFalse((self.tmp / "job").exists())
        self.assertEqual(Erases.seen, [])

    def test_an_end_of_input_during_the_run_is_a_cancel(self):
        process, ours = self.start(mode="sleep")
        ours.sendall(json.dumps(JOB).encode() + b"\n")
        seen = self.tmp / "job" / "seen.json"
        for _ in range(100):
            if seen.exists():
                break
            time.sleep(0.05)
        started = time.monotonic()
        ours.shutdown(socket.SHUT_WR)
        rest = b""
        while chunk := ours.recv(65536):
            rest += chunk
        process.wait(timeout=10)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(rest, b"", "a cancelled job writes nothing back")
        self.assertEqual(process.returncode, 0)
        self.assertEqual(Erases.seen, ["/slots/0?action=erase"])
        self.assertIn(b'"outcome": "cancelled"', process.stderr.read())
        process.stderr.close()
        ours.close()


class TheDeadline(Base):
    def test_a_run_past_its_deadline_is_stopped(self):
        goose = self.fake_goose("sleep")
        work = self.tmp / "work"
        work.mkdir()
        read, write = os.pipe()
        env = {"HOME": str(work), "PATH": os.environ["PATH"], "FAKE_MODE": "sleep"}
        started = time.monotonic()
        recipe = work / "recipe.json"
        recipe.write_text("{}")
        outcome = agent_job.run_goose(
            [str(goose), "--recipe", str(recipe)],
            env,
            time.monotonic() + 1,
            read,
            work / "out",
            work / "err",
        )
        os.close(write)
        self.assertEqual(outcome, ("timeout", None))
        self.assertLess(time.monotonic() - started, 8)


if __name__ == "__main__":
    unittest.main()
