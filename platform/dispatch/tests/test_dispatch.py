"""The dispatch step against the real worker side, in one process tree.

dispatch.py runs as a subprocess. Its ssh is a fake that runs the real job
runner from worker/agent-runtime/job. The runner connects to a socket where
this test does what systemd does: accept, and start the real job program with
the connection as its standard input and output. The job program runs a fake
Goose. Registration and the model server's slot erase go to stubs.
"""

import hashlib
import json
import os
import signal
import socket
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
JOB_DIR = HERE.parent.parent / "worker" / "agent-runtime" / "job"
sys.path.insert(0, str(HERE))

import dispatch

# A fake Goose: records the recipe, then answers as FAKE_MODE says. It logs
# the request it would send the model, with the tools Goose 1.56.0 offers,
# where the job program reads them (#139).
FAKE_GOOSE = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys, time
    mode = os.environ.get("FAKE_MODE", "{mode}")
    recipe = json.load(open(sys.argv[sys.argv.index("--recipe") + 1]))
    with open({seen!r}, "w") as f:
        json.dump(recipe, f)
    if mode == "sleep":
        time.sleep(60)
    if mode == "fail":
        sys.exit(1)
    logs = os.path.join(os.environ["GOOSE_PATH_ROOT"], "state", "logs")
    os.makedirs(logs)
    with open(os.path.join(logs, "llm_request.0.jsonl"), "w") as f:
        tools = [{{"type": "function", "function": {{"name": n}}}}
                 for n in ("tools__get_evidence", "load_skill")]
        print(json.dumps({{"model_config": {{}}, "input": {{"tools": tools}}}}), file=f)
    calls = [] if mode == "nocall" else [
        {{"role": "assistant", "content": [{{"type": "toolRequest", "toolCall": {{"value": {{}}}}}}]}},
        {{"role": "user", "content": [{{"type": "toolResponse",
          "toolResult": {{"status": "success", "value": {{}}}}}}]}},
    ]
    text = {{
        "long": "x" * 8193,
        "edge": "x" * 8192,
        "braces": "Confirmed. " + "{{" * 2 + "workflow.name" + "}}" * 2,
        "escape": "Confirmed. \x1b[2J",
        "surrogate": "Confirmed. \\ud800",
    }}.get(mode, "Confirmed.")
    print(json.dumps({{"messages": calls + [
        {{"role": "assistant", "content": [{{"type": "text", "text": text}}]}},
    ], "metadata": {{"status": "completed"}}}}))
    """
)

FAKE_SSH = textwrap.dedent(
    """\
    #!{python}
    import json, sys
    with open({argv!r}, "w") as f:
        json.dump(sys.argv[1:], f)
    sys.path.insert(0, {job_dir!r})
    import aisec_job_runner
    sys.exit(aisec_job_runner.main({sock!r}))
    """
)


class Stub(BaseHTTPRequestHandler):
    """The tool service's registration listener, and the model server."""

    calls: ClassVar[list] = []
    register_status: ClassVar[int] = 201
    # One status for each erase in turn, then 200.
    erase_statuses: ClassVar[list] = []

    def answer(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        Stub.calls.append(("POST", self.path, self.headers.get("Authorization"), body))
        if self.path == "/jobs":
            self.answer(Stub.register_status, {"job": json.loads(body)["job"]})
        else:
            status = Stub.erase_statuses.pop(0) if Stub.erase_statuses else 200
            self.answer(status, {"id_slot": 0})

    def do_DELETE(self):
        Stub.calls.append(("DELETE", self.path, self.headers.get("Authorization"), b""))
        self.answer(200, {"job": self.path.rsplit("/", 1)[1]})

    def log_message(self, *args):
        pass


class Chain(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        Stub.calls, Stub.register_status, Stub.erase_statuses = [], 201, []
        self.http = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.sock = str(self.tmp / "agent.sock")
        self.jobs = []
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.sock)
        self.listener.listen(1)
        threading.Thread(target=self.systemd, daemon=True).start()
        (self.tmp / "caller").write_text("caller-token\n")
        (self.tmp / "key").write_text("not a real key\n")
        (self.tmp / "known_hosts").write_text("10.40.0.36 ssh-ed25519 AAAA\n")
        (self.tmp / "system.txt").write_text("You investigate security findings.")
        self.mode = "ok"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.listener.close()
        for job in self.jobs:
            if job.poll() is None:
                job.kill()
            job.wait()
            job.stderr.close()

    def systemd(self):
        """Accept=yes: one job program per connection."""
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            goose = self.tmp / f"goose-{len(self.jobs)}"
            goose.write_text(
                FAKE_GOOSE.format(
                    python=sys.executable,
                    mode=self.mode,
                    seen=str(self.tmp / "recipe-seen.json"),
                )
            )
            goose.chmod(0o755)
            env = {
                "PATH": os.environ["PATH"],
                "AISEC_GOOSE": str(goose),
                "AISEC_SYSTEM": str(self.tmp / "system.txt"),
                "AISEC_WORK": str(self.tmp / f"job-{len(self.jobs)}"),
                "AISEC_MODEL_URL": self.url,
            }
            self.jobs.append(
                subprocess.Popen(
                    [sys.executable, "-I", str(JOB_DIR / "agent_job.py")],
                    stdin=conn,
                    stdout=conn,
                    stderr=subprocess.PIPE,
                    env=env,
                )
            )
            conn.close()

    def env(self):
        fake_ssh = self.tmp / "ssh"
        fake_ssh.write_text(
            FAKE_SSH.format(
                python=sys.executable,
                argv=str(self.tmp / "ssh-argv.json"),
                job_dir=str(JOB_DIR),
                sock=self.sock,
            )
        )
        fake_ssh.chmod(0o755)
        return {
            "PATH": os.environ["PATH"],
            "AISEC_REGISTER_URL": self.url + "/jobs",
            "AISEC_CALLER_TOKEN": str(self.tmp / "caller"),
            "AISEC_DISPATCH_KEY": str(self.tmp / "key"),
            "AISEC_KNOWN_HOSTS": str(self.tmp / "known_hosts"),
            "AISEC_WORK": str(self.tmp / "work"),
            "AISEC_RESULT": str(self.tmp / "result.json"),
            "AISEC_ANSWER": str(self.tmp / "answer.txt"),
            "AISEC_SSH": str(fake_ssh),
        }

    def start(self, *args):
        return subprocess.Popen(
            [sys.executable, "-I", str(HERE / "dispatch.py"), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env(),
        )

    def run_dispatch(self, *args):
        process = self.start(*args)
        out, err = process.communicate(timeout=60)
        return process.returncode, out.decode(), err.decode()

    def registered_digest(self):
        posts = [c for c in Stub.calls if c[0] == "POST" and c[1] == "/jobs"]
        self.assertEqual(len(posts), 1)
        return json.loads(posts[0][3])

    def worker_token(self):
        recipe = json.loads((self.tmp / "recipe-seen.json").read_text())
        return recipe["extensions"][0]["headers"]["Authorization"].removeprefix(
            "Bearer "
        )

    def test_a_job_registers_runs_and_returns_a_checked_result(self):
        code, out, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "Is F-0001 confirmed?"
        )
        self.assertEqual(code, 0, err)
        body = self.registered_digest()
        self.assertEqual(
            {k: body[k] for k in ("job", "target", "tools", "seconds")},
            {
                "job": "job-1",
                "target": "synthetic",
                "tools": ["get_evidence"],
                "seconds": 360,
            },
        )
        self.assertEqual(Stub.calls[0][2], "Bearer caller-token")
        token = self.worker_token()
        self.assertEqual(
            hashlib.sha256(token.encode()).hexdigest(), body["token_sha256"]
        )
        result = json.loads((self.tmp / "result.json").read_text())
        self.assertEqual((result["status"], result["tool_calls"]), ("completed", 1))
        self.assertIs(result["slot_erased"], True)
        erases = [c for c in Stub.calls if c[1] == "/slots/0?action=erase"]
        self.assertEqual(len(erases), 2)
        self.assertIn("Confirmed.", out)

    def test_the_transcript_reaches_the_output_and_the_log(self):
        code, out, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 0, err)
        transcript = json.loads((self.tmp / "result.json").read_text())["transcript"]
        self.assertEqual(
            [(p["role"], p["type"]) for p in transcript],
            [
                ("system", "instructions"),
                ("assistant", "toolRequest"),
                ("user", "toolResponse"),
                ("assistant", "text"),
            ],
        )
        self.assertIn(
            "-- system instructions\nYou investigate security findings.\n", out
        )
        self.assertIn("-- assistant text\nConfirmed.\n-- answer\nConfirmed.\n", out)
        self.assertNotIn('"transcript"', out.splitlines()[0])

    def test_the_token_is_nowhere_but_the_worker(self):
        _, out, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "Is F-0001 confirmed?"
        )
        token = self.worker_token()
        argv = (self.tmp / "ssh-argv.json").read_text()
        for place in (out, err, argv, (self.tmp / "result.json").read_text()):
            self.assertNotIn(token, place)
        self.assertNotIn(token, json.dumps([c[3].decode() for c in Stub.calls]))

    def test_ssh_checks_the_host_key_and_uses_a_private_copy_of_the_key(self):
        self.run_dispatch("dispatch", "job-1", "synthetic", "6", "60", "task")
        argv = json.loads((self.tmp / "ssh-argv.json").read_text())
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn(f"UserKnownHostsFile={self.tmp / 'known_hosts'}", argv)
        self.assertIn("BatchMode=yes", argv)
        self.assertEqual(argv[-2:], ["aisec-job@10.40.0.36", "run"])
        key = Path(argv[argv.index("-i") + 1])
        self.assertEqual(key.parent, self.tmp / "work")
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)

    def test_a_refused_registration_opens_no_session(self):
        Stub.register_status = 409
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("registration refused", err)
        self.assertFalse((self.tmp / "ssh-argv.json").exists())

    def test_a_job_without_a_tool_call_fails_the_step(self):
        self.mode = "nocall"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("called no tool", err)

    def test_a_failed_job_fails_the_step_and_keeps_its_result(self):
        self.mode = "fail"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("ended failed", err)
        self.assertEqual(
            json.loads((self.tmp / "result.json").read_text())["exit_code"], 1
        )

    def test_the_answer_reaches_its_own_output_file(self):
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual((self.tmp / "answer.txt").read_text(), "Confirmed.")

    def test_an_answer_longer_than_the_comparison_reads_fails_the_step(self):
        self.mode = "long"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("reads at most 8192", err)
        self.assertFalse((self.tmp / "answer.txt").exists())
        self.assertTrue((self.tmp / "result.json").exists())

    def test_an_answer_of_8192_bytes_passes(self):
        self.mode = "edge"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len((self.tmp / "answer.txt").read_bytes()), 8192)

    def test_an_answer_with_template_syntax_fails_the_step(self):
        self.mode = "braces"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("template syntax", err)
        self.assertFalse((self.tmp / "answer.txt").exists())

    def test_an_answer_argo_cannot_pass_on_fails_the_step(self):
        self.mode = "escape"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("a character the step does not hand on", err)
        self.assertFalse((self.tmp / "answer.txt").exists())

    def test_an_answer_with_a_lone_surrogate_fails_the_step_cleanly(self):
        # Checked before the size, whose encoding would raise instead.
        self.mode = "surrogate"
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("a character the step does not hand on", err)
        self.assertNotIn("Traceback", err)

    def test_a_slot_not_erased_after_the_job_fails_the_step(self):
        Stub.erase_statuses = [200, 501]
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("slot was not erased", err)
        result = json.loads((self.tmp / "result.json").read_text())
        self.assertEqual(
            (result["status"], result["slot_erased"]), ("completed", False)
        )

    def test_a_slot_not_erased_before_the_job_refuses_it(self):
        Stub.erase_statuses = [501]
        code, _, err = self.run_dispatch(
            "dispatch", "job-1", "synthetic", "6", "60", "task"
        )
        self.assertEqual(code, 1)
        self.assertIn("refused the job", err)
        self.assertIn("slot could not be erased", err)
        self.assertFalse((self.tmp / "recipe-seen.json").exists(), "Goose ran")
        self.assertFalse((self.tmp / "result.json").exists())

    def test_a_stop_is_a_cancel_on_the_worker(self):
        self.mode = "sleep"
        process = self.start("dispatch", "job-1", "synthetic", "6", "60", "task")
        for _ in range(200):
            if (self.tmp / "recipe-seen.json").exists():
                break
            time.sleep(0.05)
        self.assertTrue(
            (self.tmp / "recipe-seen.json").exists(), "the job never started"
        )
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=30)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM)
        (job,) = self.jobs
        job.wait(timeout=15)
        self.assertLess(time.monotonic() - started, 15)
        self.assertIn(b'"outcome": "cancelled"', job.stderr.read())
        self.assertFalse((self.tmp / "result.json").exists())

    def test_revoke_ends_the_job_as_the_dispatch_account(self):
        code, out, _ = self.run_dispatch("revoke", "job-1")
        self.assertEqual(code, 0)
        self.assertEqual(
            Stub.calls, [("DELETE", "/jobs/job-1", "Bearer caller-token", b"")]
        )
        self.assertIn("200", out)

    def test_bad_arguments_register_nothing(self):
        for args in (
            ("dispatch", "Job-1", "synthetic", "6", "60", "task"),
            ("dispatch", "job-1", "synthetic", "0", "60", "task"),
            ("dispatch", "job-1", "synthetic", "6", "59", "task"),
            ("dispatch", "job-1", "synthetic", "6", "1201", "task"),
            ("dispatch", "job-1", "synthetic", "six", "60", "task"),
            ("dispatch", "job-1", "other", "6", "60", "task"),
            ("dispatch", "job-1", "", "6", "60", "task"),
            ("dispatch", "job-1", "Netbox", "6", "60", "task"),
        ):
            with self.subTest(args):
                code, _, _ = self.run_dispatch(*args)
                self.assertEqual(code, 1)
        self.assertEqual(Stub.calls, [])

    def test_an_unknown_target_is_refused_before_registration(self):
        code, _, err = self.run_dispatch("dispatch", "job-1", "other", "6", "60", "t")
        self.assertEqual(code, 1)
        self.assertIn("failed: not a target", err)
        self.assertEqual(Stub.calls, [])

    def test_the_old_form_without_a_target_registers_nothing(self):
        code, _, _ = self.run_dispatch("dispatch", "job-1", "6", "60", "task")
        self.assertEqual(code, 2)
        self.assertEqual(Stub.calls, [])

    def test_the_target_is_registered(self):
        code, _, err = self.run_dispatch("dispatch", "job-1", "netbox", "6", "60", "t")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.registered_digest()["target"], "netbox")


PART = {"role": "assistant", "type": "text", "text": "Confirmed."}


class TheResult(unittest.TestCase):
    GOOD: ClassVar[dict] = {
        "job": "job-1",
        "status": "completed",
        "exit_code": 0,
        "seconds": 12.5,
        "agent_status": "completed",
        "tool_calls": 1,
        "tool_errors": 0,
        "answer": "Confirmed.",
        "stderr_tail": "",
        "slot_erased": True,
        "input_tokens": 700,
        "transcript": [PART],
    }

    def test_a_good_result_passes(self):
        self.assertEqual(
            dispatch.check_result(json.dumps(self.GOOD), "job-1"), self.GOOD
        )

    def test_each_bad_result_fails(self):
        bad = {
            "not JSON": "{",
            "a list": "[]",
            "a refusal": json.dumps(
                {"status": "refused", "reason": "job line too long"}
            ),
            "an added field": json.dumps({**self.GOOD, "next_step": "run this"}),
            "a field missing": json.dumps(
                {k: v for k, v in self.GOOD.items() if k != "answer"}
            ),
            "calls as text": json.dumps({**self.GOOD, "tool_calls": "1"}),
            "calls as a bool": json.dumps({**self.GOOD, "tool_calls": True}),
            "no slot_erased": json.dumps(
                {k: v for k, v in self.GOOD.items() if k != "slot_erased"}
            ),
            "another job": json.dumps({**self.GOOD, "job": "job-2"}),
            "an unknown status": json.dumps({**self.GOOD, "status": "approved"}),
            "a transcript as text": json.dumps({**self.GOOD, "transcript": "x"}),
            "a transcript part as text": json.dumps(
                {**self.GOOD, "transcript": ["Confirmed."]}
            ),
            "a transcript part with a field added": json.dumps(
                {**self.GOOD, "transcript": [{**PART, "next_step": "run this"}]}
            ),
            "a transcript part without its text": json.dumps(
                {**self.GOOD, "transcript": [{"role": "user", "type": "text"}]}
            ),
            "a transcript part's text as a number": json.dumps(
                {**self.GOOD, "transcript": [{**PART, "text": 1}]}
            ),
        }
        for name, line in bad.items():
            with self.subTest(name), self.assertRaises(dispatch.Failed):
                dispatch.check_result(line, "job-1")

    def test_a_job_that_did_not_complete_may_give_no_counts(self):
        # Goose writes its transcript when it ends, so a stopped job's calls
        # are unknown on the worker (#200). The audit log holds them.
        for status in ("timeout", "failed"):
            line = {
                **self.GOOD,
                "status": status,
                "tool_calls": None,
                "tool_errors": None,
            }
            with self.subTest(status):
                self.assertIsNone(
                    dispatch.check_result(json.dumps(line), "job-1")["tool_calls"]
                )

    def test_a_completed_job_gives_its_counts(self):
        for field in ("tool_calls", "tool_errors"):
            line = json.dumps({**self.GOOD, field: None})
            with (
                self.subTest(field),
                self.assertRaisesRegex(dispatch.Failed, "no call counts"),
            ):
                dispatch.check_result(line, "job-1")

    def test_slot_erased_is_true_or_false_and_nothing_else(self):
        for value in ("true", 1, 0, None):
            line = json.dumps({**self.GOOD, "slot_erased": value})
            with (
                self.subTest(value),
                self.assertRaisesRegex(dispatch.Failed, "slot_erased has the wrong"),
            ):
                dispatch.check_result(line, "job-1")


class TheQuoting(unittest.TestCase):
    """What Argo's strconv.Quote writes as an escape that JSON does not have."""

    def test_controls_del_surrogates_and_every_astral_character(self):
        # Above U+FFFF, Go 1.26's tables (Unicode 15.0) and Python's differ,
        # so the step refuses them all. U+1FAE9 is new in Unicode 15.1.
        for c in ("\x00", "\x07", "\x0b", "\x1b", "\x1f", "\x7f", "\ud800",
                  "\U000e0001", "\U000f0000", "\U0010fffd", "\U0001f6a8",
                  "\U0001fae9", "\U00020000", "\U0001cc00"):  # fmt: skip
            with self.subTest(hex(ord(c))):
                self.assertTrue(dispatch.unquotable(c))

    def test_what_json_can_hold_passes(self):
        for c in ("\b", "\t", "\n", "\f", "\r", " ", "a", "\u00e9", "\u200b",
                  "\u2705", "\uffff"):  # fmt: skip
            with self.subTest(hex(ord(c))):
                self.assertFalse(dispatch.unquotable(c))


class TheLog(unittest.TestCase):
    def test_control_and_format_characters_do_not_reach_a_terminal(self):
        self.assertEqual(
            dispatch.printable("a\x1b[2Jb\r\u202ec\n\td"),
            "a\ufffd[2Jb\ufffd\ufffdc\n\td",
        )


if __name__ == "__main__":
    unittest.main()
