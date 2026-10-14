"""The tool on its own, without the schema in front of it. The schema refuses
all of these first. The tool refuses them again, because it opens the file."""

import pytest

from aisec_tools.jobs import Job
from aisec_tools.tools.evidence import make_get_evidence


@pytest.fixture
def store(tmp_path):
    (tmp_path / "evidence" / "a").mkdir(parents=True)
    (tmp_path / "evidence" / "b").mkdir()
    (tmp_path / "evidence" / "a" / "ev-0001.json").write_text("A")
    (tmp_path / "evidence" / "b" / "ev-0002.json").write_text("B")
    (tmp_path / "secret.json").write_text("S")
    (tmp_path / "evidence" / "a" / "link.json").symlink_to(tmp_path / "secret.json")
    return make_get_evidence(tmp_path / "evidence")


def job(target):
    return Job("job", target, frozenset(), 0.0, "digest")


def test_it_reads_the_jobs_own_target(store):
    assert store(job("a"), {"reference": "ev-0001"}) == "A"
    assert store(job("b"), {"reference": "ev-0002"}) == "B"


@pytest.mark.parametrize(
    ("target", "reference"),
    [
        ("a", "ev-0002"),
        ("a", "../b/ev-0002"),
        ("a", "../../secret"),
        ("a", "link"),
        ("..", "secret"),
        ("a/..", "a/ev-0001"),
        ("", "a/ev-0001"),
        ("no-such-target", "ev-0001"),
    ],
)
def test_it_reads_nothing_else(store, target, reference):
    assert store(job(target), {"reference": reference}) is None
