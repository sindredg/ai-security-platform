"""The forced command, against a fake job socket in a temporary directory.

The runner runs as a subprocess with pipes for standard input and output, as
sshd gives it the session.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
JOB_LINE = json.dumps({"job": "job-1"}).encode() + b"\n"


class FakeJob:
    """Listens on a Unix socket. On a connection, reads the job line and then
    does what `behaviour` says. Records what it saw."""

    def __init__(self, path, behaviour):
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        self.listener.listen(1)
        self.behaviour = behaviour
        self.line = None
        self.saw_end = threading.Event()
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        conn, _ = self.listener.accept()
        with conn:
            data = b""
            while b"\n" not in data:
                data += conn.recv(4096)
            self.line = data
            if self.behaviour == "answer":
                conn.sendall(b'{"status": "completed"}\n')
            elif self.behaviour == "flood":
                conn.sendall(b"x" * 70000)
            elif self.behaviour == "wait" and conn.recv(4096) == b"":
                self.saw_end.set()
            # "close": nothing, the connection closes.


class Runner(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "agent.sock"

    def start(self, request=""):
        code = (
            f"import sys; sys.path.insert(0, {str(HERE)!r}); "
            f"import aisec_job_runner as r; sys.exit(r.main({str(self.path)!r}))"
        )
        env = {"PATH": os.environ["PATH"], "SSH_ORIGINAL_COMMAND": request}
        return subprocess.Popen(
            [sys.executable, "-I", "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def run_runner(self, data, request=""):
        process = self.start(request)
        out, err = process.communicate(data, timeout=20)
        return process.returncode, out, err

    def test_another_command_is_refused(self):
        code, out, err = self.run_runner(JOB_LINE, request="cat /etc/shadow")
        self.assertEqual((code, out), (2, b""))
        self.assertIn(b"not a job request", err)

    def test_a_job_line_over_the_limit_is_refused(self):
        code, _, err = self.run_runner(b"x" * 20000 + b"\n")
        self.assertEqual(code, 2)
        self.assertIn(b"too long", err)

    def test_input_after_the_job_line_is_refused(self):
        FakeJob(self.path, "answer")
        code, _, err = self.run_runner(JOB_LINE + b"more\n")
        self.assertEqual(code, 2)
        self.assertIn(b"input after the job line", err)

    def test_no_socket_is_a_clear_failure(self):
        code, _, err = self.run_runner(JOB_LINE)
        self.assertEqual(code, 3)
        self.assertIn(b"no job socket", err)

    def test_the_job_line_goes_in_and_the_result_comes_out(self):
        job = FakeJob(self.path, "answer")
        process = self.start("run")
        process.stdin.write(JOB_LINE)
        process.stdin.flush()
        out = process.stdout.read()
        process.stdin.close()
        process.wait(timeout=20)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(job.line, JOB_LINE)
        self.assertEqual(out, b'{"status": "completed"}\n')
        process.stderr.close()
        process.stdout.close()

    def test_the_end_of_the_session_reaches_the_job(self):
        job = FakeJob(self.path, "wait")
        process = self.start()
        process.stdin.write(JOB_LINE)
        process.stdin.flush()
        process.stdin.close()
        self.assertTrue(job.saw_end.wait(10), "the job never saw the end of input")
        process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()

    def test_a_result_over_the_limit_is_cut_off(self):
        FakeJob(self.path, "flood")
        process = self.start()
        process.stdin.write(JOB_LINE)
        process.stdin.flush()
        out = process.stdout.read()
        process.wait(timeout=20)
        self.assertEqual(process.returncode, 4)
        self.assertLessEqual(len(out), 65536)
        self.assertIn(b"result too large", process.stderr.read())
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

    def test_a_job_that_ends_without_a_result_fails(self):
        FakeJob(self.path, "close")
        process = self.start()
        process.stdin.write(JOB_LINE)
        process.stdin.flush()
        process.stdout.read()
        process.wait(timeout=20)
        self.assertEqual(process.returncode, 5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


if __name__ == "__main__":
    unittest.main()
