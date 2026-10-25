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
# recipe it was given, so the tests can read them. It logs the request it
# would send the model where Goose 1.56.0 does, with the tools it offers: the
# recipe's one, and Goose's own load_skill (#139).
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
    tools = ["tools__get_evidence", "load_skill"]
    if mode == "extra-tool":
        tools.append("developer__shell")
    if mode == "no-tools":
        tools = []
    if mode != "no-log":
        logs = os.path.join(os.environ["GOOSE_PATH_ROOT"], "state", "logs")
        os.makedirs(logs)
        with open(os.path.join(logs, "llm_request.0.jsonl"), "w") as f:
            print(json.dumps({{"model_config": {{"model_name": "local"}}, "input": {{
                "messages": [{{"role": "user", "content": "task"}}],
                "tools": [{{"type": "function", "function": {{"name": n}}}} for n in tools],
            }}}}), file=f)
            print(json.dumps({{"data": {{}}, "usage": None}}), file=f)
    print("warning: token {token} in a log line", file=sys.stderr)
    print(json.dumps({{"messages": [
        {{"role": "user", "content": [{{"type": "text", "text": "task"}}]}},
        {{"role": "assistant", "content": [{{"type": "toolRequest",
            "toolCall": {{"value": {{"name": "tools__get_evidence"}}}}}}]}},
        {{"role": "user", "content": [{{"type": "toolResponse",
            "toolResult": {{"status": "success", "value": {{"content": [
                {{"type": "text", "text": "F-0001 evidence, token {token}"}}],
                "isError": False}}}}}}]}},
        {{"role": "assistant", "content": [{{"type": "text", "text": "Confirmed."}}]}},
    ], "metadata": {{"status": "completed", "input_tokens": 700, "output_tokens": 40}}}}))
    """
)


class Erases(BaseHTTPRequestHandler):
    """The model server's erase. Answers each request with the next status in
    statuses, and 200 when none is left."""

    seen: ClassVar[list] = []
    statuses: ClassVar[list] = []

    def do_POST(self):
        Erases.seen.append(self.path)
        self.send_response(Erases.statuses.pop(0) if Erases.statuses else 200)
        self.end_headers()

    def log_message(self, *args):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.server = HTTPServer(("127.0.0.1", 0), Erases)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        Erases.seen = []
        Erases.statuses = []
        self.model_url = f"http://127.0.0.1:{self.server.server_port}"

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
            "AISEC_MODEL_URL": self.model_url,
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
        self.stderr = process.stderr.read()
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
            "an expression": json.dumps({**JOB, "task": "Say {{ 6 * 7 }}."}),
            "a statement": json.dumps({**JOB, "task": "{% if 1 %}x{% endif %}"}),
            "a comment": json.dumps({**JOB, "task": "Is it {# no #} confirmed?"}),
            "a shell command": json.dumps({**JOB, "task": "!ls"}),
            "a shell command after a newline": json.dumps({**JOB, "task": " \n\t!ls"}),
            "a slash command": json.dumps({**JOB, "task": "/compact"}),
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

    def test_a_command_after_any_white_space_rust_strips_is_refused(self):
        # The White_Space property in Unicode's PropList.txt, which Rust's
        # trim_start uses.
        spaces = [*range(0x09, 0x0E), 0x20, 0x85, 0xA0, 0x1680,
                  *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000]  # fmt: skip
        for code in spaces:
            for prefix in agent_job.COMMAND_PREFIXES:
                task = chr(code) + prefix + "x"
                with (
                    self.subTest(f"{code:#x} {prefix}"),
                    self.assertRaises(agent_job.Refused),
                ):
                    agent_job.parse_job(json.dumps({**JOB, "task": task}))

    def test_braces_and_command_characters_inside_a_task_pass(self):
        task = "Is F-0001 {confirmed}? See /etc/hosts, 50% of {1}! {} # }}"
        self.assertEqual(
            agent_job.parse_job(json.dumps({**JOB, "task": task}))["task"], task
        )

    def test_the_system_text_has_no_template_syntax(self):
        self.assertIsNone(
            agent_job.TEMPLATE.search((HERE.parent / "system.txt").read_text())
        )

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
        self.assertIs(result["slot_erased"], True)

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

    def test_the_slot_is_erased_before_and_after_and_the_recipe_is_gone(self):
        self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertFalse((self.tmp / "job" / "recipe.json").exists())
        self.assertEqual(Erases.seen, ["/slots/0?action=erase"] * 2)
        self.assertIn(b'"erase": "before", "slot_erased": true', self.stderr)
        self.assertIn(b'"outcome": "ended", "slot_erased": true', self.stderr)

    def test_an_erase_refused_after_the_job_is_in_the_result(self):
        # What the server on the worker answered on 2026-10-20: 501, without
        # --slot-save-path. The status stays the job's own. The dispatch step
        # fails the workflow on the field.
        Erases.statuses = [200, 501]
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n")
        result = json.loads(data)
        self.assertEqual(result["status"], "completed")
        self.assertIs(result["slot_erased"], False)
        self.assertIn(b'"slot_erased": false', self.stderr)

    def test_an_erase_refused_before_the_job_refuses_it(self):
        # The erase after the last job failed, or never ran because its unit
        # was stopped first. The slot may hold that job's prompt.
        for status in (501, 503):
            with self.subTest(status):
                Erases.seen, Erases.statuses = [], [status]
                code, data = self.run_job(json.dumps(JOB).encode() + b"\n")
                self.assertEqual(code, 2)
                self.assertEqual(
                    json.loads(data),
                    {
                        "status": "refused",
                        "reason": "the model server's slot could not be erased",
                    },
                )
                self.assertEqual(Erases.seen, ["/slots/0?action=erase"])
                self.assertFalse((self.tmp / "job").exists())
                self.assertIn(b'"erase": "before", "slot_erased": false', self.stderr)

    def test_a_model_server_that_is_down_refuses_the_job(self):
        # A port nothing listens on: the connection is refused.
        with socket.socket() as closed:
            closed.bind(("127.0.0.1", 0))
            self.model_url = f"http://127.0.0.1:{closed.getsockname()[1]}"
        code, data = self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(data)["status"], "refused")
        self.assertFalse((self.tmp / "job").exists())

    def test_the_token_never_comes_back_in_the_result(self):
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertNotIn(TOKEN.encode(), data)
        self.assertIn("[token]", json.loads(data)["stderr_tail"])

    def test_the_transcript_comes_back_part_by_part_without_the_token(self):
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertEqual(
            json.loads(data)["transcript"],
            [
                {
                    "role": "system",
                    "type": "instructions",
                    "text": "You investigate security findings.",
                },
                {"role": "user", "type": "text", "text": "task"},
                {
                    "role": "assistant",
                    "type": "toolRequest",
                    "text": '{"name": "tools__get_evidence", "arguments": null}',
                },
                {
                    "role": "user",
                    "type": "toolResponse",
                    "text": "F-0001 evidence, token [token]",
                },
                {"role": "assistant", "type": "text", "text": "Confirmed."},
            ],
        )

    def test_a_goose_that_fails_gives_a_failed_result(self):
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n", mode="fail")
        result = json.loads(data)
        self.assertEqual((result["status"], result["exit_code"]), ("failed", 1))
        self.assertIn("model unreachable", result["stderr_tail"])
        self.assertEqual(Erases.seen, ["/slots/0?action=erase"] * 2)

    def test_the_tools_goose_offered_go_to_the_journal(self):
        self.run_job(json.dumps(JOB).encode() + b"\n")
        self.assertIn(
            b'{"job": "job-1", "offered": ["load_skill", "tools__get_evidence"]}',
            self.stderr,
        )

    def test_a_request_with_no_tools_is_logged_as_an_empty_list(self):
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n", mode="no-tools")
        self.assertIn(b'{"job": "job-1", "offered": []}', self.stderr)
        self.assertEqual(json.loads(data)["status"], "completed")

    def test_a_tool_outside_the_recipe_fails_the_job(self):
        # A Goose release that adds a tool of its own, such as one that runs
        # shell commands, would reach the model unnoticed (#139, A8).
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n", mode="extra-tool")
        result = json.loads(data)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["answer"], "Confirmed.")
        self.assertTrue(
            result["stderr_tail"].endswith(
                "the model was offered tools outside the recipe: developer__shell"
            )
        )

    def test_a_job_whose_requests_were_not_logged_fails(self):
        # Without the log, the offered tools are unknown. The check fails
        # closed, so a Goose that logs elsewhere is seen at its first job.
        _, data = self.run_job(json.dumps(JOB).encode() + b"\n", mode="no-log")
        result = json.loads(data)
        self.assertEqual(result["status"], "failed")
        self.assertIn("offered tools are unknown", result["stderr_tail"])
        self.assertIn(b'{"job": "job-1", "offered": null}', self.stderr)

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
        self.assertEqual(Erases.seen, ["/slots/0?action=erase"] * 2)
        self.assertIn(b'"outcome": "cancelled"', process.stderr.read())
        process.stderr.close()
        ours.close()


class TheResultLine(unittest.TestCase):
    """result_line on its own, with Goose's output written by the test."""

    def line(self, messages=(), answer="Confirmed.", stderr=""):
        tmp = Path(tempfile.mkdtemp())
        out, err = tmp / "out.json", tmp / "err.txt"
        last = {"role": "assistant", "content": [{"type": "text", "text": answer}]}
        metadata = {"status": "completed"}
        out.write_text(
            json.dumps({"messages": [*messages, last], "metadata": metadata})
        )
        err.write_text(stderr)
        return agent_job.result_line(
            JOB, "system text", "ended", 0, time.monotonic(), out, err, True,
            agent_job.OFFERED,
        )  # fmt: skip

    def test_a_long_transcript_is_cut_to_the_limit_and_says_so(self):
        # Characters outside ASCII take 6 or 12 bytes each in the line.
        text = "\U0001f600é" * 3000
        messages = [{"role": "user", "content": [{"type": "text", "text": text}]}] * 40
        line = self.line(messages, answer=text * 3, stderr=text * 3)
        self.assertLessEqual(len(line.encode()), agent_job.RESULT_BYTES)
        result = json.loads(line)
        self.assertEqual(result["transcript"][-1]["type"], "cut")
        self.assertRegex(result["transcript"][-1]["text"], r"^\d+ parts left out$")
        self.assertGreater(len(result["transcript"]), 2)

    def test_no_part_of_the_token_is_left_where_a_text_is_cut(self):
        # Cut first and replaced after, each text would keep half the token.
        # The stderr tail is cut from its start.
        for size in (agent_job.ANSWER_BYTES, agent_job.PART_BYTES):
            text = "x" * (size - 2 - 32) + TOKEN
            messages = [{"role": "user", "content": [{"type": "text", "text": text}]}]
            stderr = TOKEN + "x" * (agent_job.STDERR_BYTES - 2 - 32)
            line = self.line(messages, answer=text, stderr=stderr)
            self.assertNotIn(TOKEN[:16], line)

    def test_without_goose_output_the_transcript_is_the_instructions_only(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "err.txt").write_text("")
        line = agent_job.result_line(
            JOB, "system text", "timeout", None, time.monotonic(),
            tmp / "out.json", tmp / "err.txt", True, None,
        )  # fmt: skip
        self.assertEqual(
            json.loads(line)["transcript"],
            [{"role": "system", "type": "instructions", "text": "system text"}],
        )


class TheOfferedTools(unittest.TestCase):
    """offered_tools on request logs written by the test."""

    def logs(self, *lines):
        work = Path(tempfile.mkdtemp())
        logs = work / "goose" / "state" / "logs"
        logs.mkdir(parents=True)
        for index, line in enumerate(lines):
            (logs / f"llm_request.{index}.jsonl").write_text(line)
        return work

    def request(self, *names):
        tools = [{"type": "function", "function": {"name": n}} for n in names]
        return json.dumps({"model_config": {}, "input": {"tools": tools}}) + "\n"

    def test_the_names_over_every_request(self):
        work = self.logs(
            self.request("tools__get_evidence"),
            self.request("load_skill", "tools__get_evidence"),
        )
        self.assertEqual(
            agent_job.offered_tools(work), {"tools__get_evidence", "load_skill"}
        )

    def test_a_request_with_no_tools_offers_none(self):
        work = self.logs(json.dumps({"model_config": {}, "input": {"messages": []}}))
        self.assertEqual(agent_job.offered_tools(work), set())

    def test_an_empty_log_is_a_request_still_in_its_buffer(self):
        # Goose writes a request's log through a buffer, so a run stopped
        # mid-request can leave the file empty.
        work = self.logs(self.request("tools__get_evidence"), "")
        self.assertEqual(agent_job.offered_tools(work), {"tools__get_evidence"})

    def test_no_log_or_a_log_that_cannot_be_read_gives_none(self):
        for name, lines in {
            "no log": (),
            "only an empty log": ("",),
            "not JSON": ("{",),
            "no input": ('{"model_config": {}}',),
            "a tool without a name": ('{"input": {"tools": [{"type": "function"}]}}',),
            "tools not a list": ('{"input": {"tools": 3}}',),
        }.items():
            with self.subTest(name):
                self.assertIsNone(agent_job.offered_tools(self.logs(*lines)))

    def test_only_the_recipes_tool_and_load_skill_pass(self):
        self.assertIsNone(agent_job.tools_problem(agent_job.OFFERED))
        self.assertIsNone(agent_job.tools_problem({"tools__get_evidence"}))
        self.assertEqual(
            agent_job.tools_problem({"load_skill", "summon", "developer__shell"}),
            "the model was offered tools outside the recipe: developer__shell, summon",
        )
        self.assertRegex(agent_job.tools_problem(None), "unknown")


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
