"""The journal puller against a fake worker: a small program in place of ssh."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aisec_journal_pull as puller

CURSOR_1 = "s=" + "a" * 32 + ";i=1;b=" + "b" * 32 + ";m=1;t=1;x=1"
CURSOR_2 = "s=" + "a" * 32 + ";i=2;b=" + "b" * 32 + ";m=2;t=2;x=2"


def entry(cursor, message="m"):
    return json.dumps({"__CURSOR": cursor, "MESSAGE": message}).encode()


class Puller(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.out = self.root / "worker-journal.jsonl"
        self.out.touch()
        self.home = self.root / "home"
        self.home.mkdir()
        self.sent = self.root / "sent"
        for name, value in [("HOME", self.home), ("OUT", self.out)]:
            patch = mock.patch.object(puller, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def worker(self, stdout=b"", status=0, stderr=0, hang=0):
        """The fake worker writes what it was asked to a file, then answers."""
        answer = self.root / "answer"
        answer.write_bytes(stdout)
        program = (
            "import os, sys, time\n"
            f"open({str(self.sent)!r}, 'w').write(sys.argv[1])\n"
            f"sys.stderr.write('e' * {stderr}); sys.stderr.flush()\n"
            f"sys.stdout.buffer.write(open({str(answer)!r}, 'rb').read())\n"
            "sys.stdout.flush(); os.close(1)\n"
            f"time.sleep({hang})\n"
            f"sys.exit({status})\n"
        )
        command = [sys.executable, "-c", program]
        patch = mock.patch.object(puller, "ssh", lambda cursor: [*command, cursor])
        patch.start()
        self.addCleanup(patch.stop)

    def copied(self):
        return self.out.read_bytes().splitlines()

    def reasons(self):
        return [json.loads(line).get("reason") for line in self.copied()]

    def test_the_first_pull_asks_for_everything_and_keeps_the_last_cursor(self):
        self.worker(entry(CURSOR_1) + b"\n" + entry(CURSOR_2) + b"\n")
        self.assertEqual(puller.one_pull(), (2, False))
        self.assertEqual(self.sent.read_text(), "")
        self.assertEqual(self.copied(), [entry(CURSOR_1), entry(CURSOR_2)])
        self.assertEqual((self.home / "cursor").read_text(), CURSOR_2 + "\n")
        self.assertTrue((self.home / "ok").exists())

    def test_the_next_pull_asks_after_the_saved_cursor(self):
        (self.home / "cursor").write_text(CURSOR_1 + "\n")
        self.worker(b"")
        self.assertEqual(puller.one_pull(), (0, False))
        self.assertEqual(self.sent.read_text(), CURSOR_1)
        self.assertEqual(self.copied(), [])
        self.assertTrue((self.home / "ok").exists())

    def test_what_is_not_a_journal_entry_becomes_a_marker(self):
        lines = [
            b"not json",
            b"[1, 2]",
            b"[" * 50_000,
            json.dumps({"MESSAGE": "no cursor"}).encode(),
            json.dumps({"__CURSOR": "x; rm -rf /"}).encode(),
            json.dumps({"__CURSOR": CURSOR_1.upper()}).encode(),
            entry(CURSOR_1),
        ]
        self.worker(b"\n".join(lines) + b"\n")
        puller.one_pull()
        not_an_object = "not a JSON object"
        no_cursor = "no cursor in the journal's format"
        expected = [not_an_object] * 3 + [no_cursor] * 3 + [None]
        self.assertEqual(self.reasons(), expected)
        self.assertNotIn(b"rm -rf", self.out.read_bytes())
        self.assertEqual((self.home / "cursor").read_text(), CURSOR_1 + "\n")

    def test_a_line_over_the_limit_becomes_one_marker(self):
        long = entry(CURSOR_1, "x" * (puller.LINE_MAX * 3))
        self.worker(long + b"\n" + entry(CURSOR_2) + b"\n")
        puller.one_pull()
        self.assertEqual(self.reasons(), ["line too long", None])
        self.assertEqual((self.home / "cursor").read_text(), CURSOR_2 + "\n")

    def test_a_pull_stops_at_its_limit_and_drops_the_cut_line(self):
        line = entry(CURSOR_1) + b"\n"
        self.worker(line * 3 + entry(CURSOR_2) + b"\n")
        with mock.patch.object(puller, "PULL_MAX", len(line) * 3 + 5):
            self.assertEqual(puller.one_pull(), (3, True))
        self.assertEqual(self.copied(), [entry(CURSOR_1)] * 3)
        self.assertEqual((self.home / "cursor").read_text(), CURSOR_1 + "\n")

    def test_a_last_line_without_an_end_is_dropped(self):
        self.worker(entry(CURSOR_1) + b"\n" + entry(CURSOR_2))
        puller.one_pull()
        self.assertEqual(self.copied(), [entry(CURSOR_1)])

    def test_a_refusal_fails_the_pull_and_appends_nothing(self):
        self.worker(entry(CURSOR_1) + b"\n", status=2)
        with self.assertRaises(puller.Failed):
            puller.one_pull()
        self.assertEqual(self.copied(), [])
        self.assertFalse((self.home / "ok").exists())
        self.assertFalse((self.home / "cursor").exists())

    def test_a_flood_on_standard_error_does_not_block_the_pull(self):
        self.worker(entry(CURSOR_1) + b"\n", stderr=4 * 1024**2)
        result = []
        pull = threading.Thread(target=lambda: result.append(puller.one_pull()))
        pull.daemon = True
        pull.start()
        pull.join(timeout=20)
        self.assertFalse(pull.is_alive(), "the pull is blocked")
        self.assertEqual(result, [(1, False)])

    def test_a_worker_that_does_not_end_fails_the_pull(self):
        self.worker(entry(CURSOR_1) + b"\n", hang=30)
        with mock.patch.object(puller, "TIMEOUT", 1), self.assertRaises(puller.Failed):
            puller.one_pull()
        self.assertFalse((self.home / "ok").exists())

    def test_a_saved_cursor_out_of_format_fails_before_ssh(self):
        (self.home / "cursor").write_text("--since=yesterday\n")
        self.worker(b"")
        with self.assertRaises(puller.Failed):
            puller.one_pull()
        self.assertFalse(self.sent.exists())

    def test_the_cap_writes_a_marker_and_stops(self):
        self.worker(entry(CURSOR_1) + b"\n")
        with mock.patch.object(puller, "CAP", 10), self.assertRaises(puller.Full):
            puller.one_pull()
        self.assertEqual(self.reasons(), ["the file reached its cap"])
        self.assertFalse((self.home / "cursor").exists())

    def test_a_missing_output_file_fails_the_pull_and_is_not_created(self):
        self.out.unlink()
        self.worker(entry(CURSOR_1) + b"\n")
        with self.assertRaises(puller.Failed):
            puller.one_pull()
        self.assertFalse(self.out.exists())


class Command(unittest.TestCase):
    def test_ssh_pins_the_host_key_and_sends_only_the_cursor(self):
        command = puller.ssh(CURSOR_1)
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("UserKnownHostsFile=/etc/aisec/journal-pull-known-hosts", command)
        self.assertIn("GlobalKnownHostsFile=none", command)
        self.assertIn("BatchMode=yes", command)
        self.assertEqual(command[-2:], ["aisec-logexport@10.40.0.36", CURSOR_1])


if __name__ == "__main__":
    unittest.main()
