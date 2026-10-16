"""The audit copier against made-up pod logs in a temporary directory."""

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aisec_audit_copy as copier

LINE_1 = b'{"seq":1,"event":"call"}'
LINE_2 = b'{"seq":2,"event":"call"}'
LINE_3 = b'{"seq":3,"event":"call"}'


def runtime(stamp, content, stream=b"stdout", tag=b"F"):
    return stamp.encode() + b" " + stream + b" " + tag + b" " + content + b"\n"


class Copier(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.logs = self.root / "pods/tool-services_tool-service-abc_uid/tool-service"
        self.logs.mkdir(parents=True)
        self.out = self.root / "tool-audit.jsonl"
        self.out.touch()
        self.state = self.root / "state"
        self.state.mkdir()
        pods = str(self.root / "pods/tool-services_tool-service-*/tool-service/*.log*")
        for name, value in [("PODS", pods), ("OUT", self.out), ("STATE", self.state)]:
            patch = mock.patch.object(copier, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, name, *lines):
        (self.logs / name).write_bytes(b"".join(lines))

    def copied(self):
        return self.out.read_bytes().splitlines()

    def test_new_lines_are_copied_once_in_the_runtimes_order(self):
        rotated = runtime("2026-10-16T05:00:01.5Z", LINE_2)
        with gzip.open(self.logs / "0.log.20261016-050002.gz", "wb") as archive:
            archive.write(runtime("2026-10-16T05:00:01.000000001Z", LINE_1) + rotated)
        self.write("0.log", runtime("2026-10-16T05:00:03.25Z", LINE_3))
        self.assertEqual(copier.one_pass(), 3)
        self.assertEqual(self.copied(), [LINE_1, LINE_2, LINE_3])
        self.assertEqual(copier.one_pass(), 0)
        self.assertEqual(self.copied(), [LINE_1, LINE_2, LINE_3])

    def test_a_rotated_copy_of_a_line_is_not_copied_twice(self):
        line = runtime("2026-10-16T05:00:01Z", LINE_1)
        self.write("0.log.20261016-050002", line)
        with gzip.open(self.logs / "0.log.20261016-050002.gz", "wb") as archive:
            archive.write(line)
        self.write("0.log", b"")
        self.assertEqual(copier.one_pass(), 1)
        self.assertEqual(self.copied(), [LINE_1])

    def test_a_line_the_service_did_not_write_whole_becomes_a_marker(self):
        self.write(
            "0.log",
            runtime("2026-10-16T05:00:01Z", b'{"seq":1', tag=b"P"),
            runtime("2026-10-16T05:00:02Z", b"Traceback", stream=b"stderr"),
            runtime("2026-10-16T05:00:03Z", b"[1, 2]"),
            runtime("2026-10-16T05:00:04Z", b"[" * 100_000),
            runtime("2026-10-16T05:00:05Z", b"\xff\xfe"),
        )
        copier.one_pass()
        reasons = [json.loads(line)["reason"] for line in self.copied()]
        whole = "not a whole line on standard output"
        not_an_object = "not a JSON object"
        self.assertEqual(reasons, [whole, whole] + [not_an_object] * 3)
        self.assertNotIn(b"Traceback", self.out.read_bytes())

    def test_no_log_file_fails_the_pass_and_leaves_health_alone(self):
        with self.assertRaises(copier.Failed):
            copier.one_pass()
        self.assertFalse((self.state / "ok").exists())

    def test_a_pass_with_nothing_new_still_reports_health(self):
        self.write("0.log", b"")
        copier.one_pass()
        self.assertTrue((self.state / "ok").exists())

    def test_a_timestamp_that_does_not_parse_fails_the_pass(self):
        for stamp in ["2026-10-16T05:00:01", "2026-13-16T05:00:01Z", "x.1Z", "1.-1Z"]:
            self.write("0.log", runtime(stamp, LINE_1))
            with self.subTest(stamp=stamp), self.assertRaises(copier.Failed):
                copier.one_pass()
        self.assertEqual(self.copied(), [])

    def test_a_line_without_the_runtimes_prefix_fails_the_pass(self):
        self.write("0.log", LINE_1 + b"\n")
        with self.assertRaises(copier.Failed):
            copier.one_pass()

    def test_a_damaged_archive_fails_the_pass(self):
        self.write("0.log.20261016-050002.gz", b"\x1f\x8b not gzip")
        with self.assertRaises(copier.Failed):
            copier.one_pass()

    def test_a_missing_output_file_fails_the_pass_and_is_not_created(self):
        self.write("0.log", runtime("2026-10-16T05:00:01Z", LINE_1))
        self.out.unlink()
        with self.assertRaises(copier.Failed):
            copier.one_pass()
        self.assertFalse(self.out.exists())

    def test_the_cap_writes_a_marker_and_stops(self):
        self.write("0.log", runtime("2026-10-16T05:00:01Z", LINE_1))
        with mock.patch.object(copier, "CAP", 10), self.assertRaises(copier.Full):
            copier.one_pass()
        (only,) = self.copied()
        self.assertEqual(json.loads(only)["reason"], "the file reached its cap")
        self.assertFalse((self.state / "position").exists())

    def test_a_position_that_does_not_parse_fails_the_pass(self):
        self.write("0.log", b"")
        (self.state / "position").write_text("not a number")
        with self.assertRaises(copier.Failed):
            copier.one_pass()

    def test_the_output_is_opened_for_append_only(self):
        self.write("0.log", runtime("2026-10-16T05:00:01Z", LINE_1))
        opened = []
        real = os.open

        def record(path, flags, *rest):
            opened.append(flags)
            return real(path, flags, *rest)

        with mock.patch.object(copier.os, "open", record):
            copier.one_pass()
        self.assertEqual(opened, [os.O_WRONLY | os.O_APPEND])


class Timestamps(unittest.TestCase):
    def test_the_fraction_is_read_as_nanoseconds(self):
        base = copier.nanoseconds("2026-10-16T05:00:01Z")
        self.assertEqual(base, 1_792_126_801 * 10**9)
        self.assertEqual(copier.nanoseconds("2026-10-16T05:00:01.5Z") - base, 5 * 10**8)
        self.assertEqual(copier.nanoseconds("2026-10-16T05:00:01.000000001Z") - base, 1)

    def test_a_malformed_fraction_is_refused(self):
        for stamp in ["2026-10-16T05:00:01.Z", "2026-10-16T05:00:01.1234567890Z"]:
            with self.subTest(stamp=stamp), self.assertRaises(copier.Failed):
                copier.nanoseconds(stamp)


if __name__ == "__main__":
    unittest.main()
