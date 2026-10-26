"""The comparison step (ADR 0041).

    compare.py JOB ANSWER

Runs in a workflow pod in `orchestration`, from the dispatch image, after the
dispatch step of a NetBox job. It holds no credential and reaches no service.

It reads the deterministic checks' verdicts for the job from the one file the
workflow mounts: the job's own key in the config map `netbox-verdicts`, which
the collect command on the orchestrator writes and no workload account can
change. ANSWER is the model's answer, which the dispatch step hands on. It is
untrusted. The step reads it for verdict lines only, one per account:

    Verdict: ACCOUNT VALUE REFERENCES

A match is every account the checks name, with the configured and the observed
check in agreement, neither unknown, and the model's value the same as
theirs. Anything else stops the workflow for the operator: a mismatch, an
inconclusive verdict, an account with no line or with lines that disagree, a
line for an account the checks do not name, a verdict line that cannot be
read, checks that disagree or cannot settle an account, and no checks for the
job.

After the verdict lines the answer may end with one proposal line for each
account the model calls excess (ADR 0043):

    Proposal: ACCOUNT remove PERMISSION_ID REFERENCES

The step reads them as strictly as verdict lines and keeps them in its output,
with the number of proposal lines it could not read. They never change the
outcome. Whether a proposal goes on is decided after the workflow, on the
orchestrator host.

It prints a row per account and the outcome last, writes the comparison as
the step's output, and writes the outcome as the container's termination
message, which Argo shows as the step's message. Of the answer, only what
matched a pattern is printed or kept: account names, values, references, and
counts. Exits 0 for a match, 1 for a stop, and 2 for a call without a job ID
and an answer. Standard library only.
"""

import contextlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

# Fixed for the pod. The tests point them into a temporary directory.
VERDICTS = Path(os.environ.get("AISEC_VERDICTS", "/etc/aisec/verdicts/verdicts.json"))
COMPARISON = Path(os.environ.get("AISEC_COMPARISON", "/tmp/comparison.json"))  # noqa: S108 - the pod's own emptyDir
TERMINATION = Path(os.environ.get("AISEC_TERMINATION", "/dev/termination-log"))

# The model's values, and the checks' (collectors/netbox/netbox_access.py). A
# model that cannot settle an account says inconclusive. The checks say
# unknown.
VALUES = ("excess", "missing", "within", "inconclusive")
CHECKS = ("excess", "missing", "unknown", "within")
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
ACCOUNT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
COLLECTED = re.compile(
    r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z"
)
MAX_ACCOUNTS = 20
# A line whose first word is the label is a verdict line. The word is found
# after Unicode compatibility forms are folded (a full-width colon, a
# no-break space), format characters such as a zero-width space are taken
# out, and so are emphasis and code marks, as check_answer.py reads the
# fixture's lines, and anything before the first letter: headings, quotes,
# list and task marks, ordered-list numbers, table bars, symbols. So a line in
# another form cannot contradict the others unseen. A label spelled with
# letters of another script is not seen. A verdict line is the label, a
# colon, the account, a separator, one value, and nothing after it but
# references. A dash separates only between spaces, because names have
# dashes. Any other verdict line, such as excess/within after the account or
# a label with more words, is a line that cannot be read. Each line is matched
# once, anchored, and the runs are possessive, so none backtracks.
FIRST = re.compile(r"[^\W_]")
ORDERED = re.compile(r"[0-9]{1,9}[.)]|[xX]\]")
WORD = re.compile(r"[^\W\d_]+")
REF = r"(?<![0-9a-z])ev-[0-9]{4}(?![0-9a-z])"
REST = re.compile(
    r"\s*+([a-z0-9][a-z0-9._-]{0,63})"
    r"(?:\s*+[:,=]\s*+|\s++[–—-]++\s++|\s++)"
    r"([a-z]++)"
    rf"((?:[\s,;.()\[\]|]++(?:and\s++)?{REF})*+)"
    r"[\s,;.()\[\]_|]*+",
    re.IGNORECASE,
)
REFERENCE = re.compile(REF, re.IGNORECASE)
# A proposal line after its label: the account, a separator as in REST, the
# action, which is remove alone, a permission's ID, and nothing after it but
# references. Anchored and possessive, as REST.
PROPOSAL = re.compile(
    r"\s*+([a-z0-9][a-z0-9._-]{0,63})"
    r"(?:\s*+[:,=]\s*+|\s++[–—-]++\s++|\s++)"
    r"(remove)\s++([1-9][0-9]{0,8}+)"
    rf"((?:[\s,;.()\[\]|]++(?:and\s++)?{REF})*+)"
    r"[\s,;.()\[\]_|]*+",
    re.IGNORECASE,
)
# Argo shows the termination message as the step's message. The kubelet keeps
# up to 4 KiB of it.
MESSAGE_BYTES = 1024
SHAPE = "the checks' verdicts are not in their shape"
KEYS = {"job", "collected", "accounts"}


class Stop(Exception):
    pass


def in_shape(document):
    if not isinstance(document, dict) or set(document) != KEYS:
        return False
    job, collected = document["job"], document["collected"]
    accounts = document["accounts"]
    if not (isinstance(job, str) and JOB_ID.fullmatch(job)):
        return False
    if not (isinstance(collected, str) and COLLECTED.fullmatch(collected)):
        return False
    if not isinstance(accounts, dict) or not 0 < len(accounts) <= MAX_ACCOUNTS:
        return False
    return all(
        ACCOUNT.fullmatch(name)
        and isinstance(verdicts, dict)
        and set(verdicts) == {"configured", "observed"}
        and all(value in CHECKS for value in verdicts.values())
        for name, verdicts in accounts.items()
    )


def load_checks(path, job):
    """The checks' verdicts for the job, by account. Raises Stop."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Stop("no checks' verdicts for this job") from None
    try:
        document = json.loads(text)
    except ValueError:
        raise Stop(SHAPE) from None
    if not in_shape(document):
        raise Stop(SHAPE)
    if document["job"] != job:
        raise Stop("the checks' verdicts are for another job")
    return document["accounts"]


def after_label(line, label="verdict"):
    """What follows a line's label, "" for a line with the label in another
    form, or None for any other line."""
    text = unicodedata.normalize("NFKC", line)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = text.replace("*", "").replace("`", "")
    while True:
        first = FIRST.search(text)
        text = text[first.start() :] if first else ""
        mark = ORDERED.match(text)
        if not mark:
            break
        text = text[mark.end() :]
    word = WORD.match(text)
    if not word or word[0].casefold() != label:
        return None
    head, colon, rest = text.partition(":")
    if not colon or head.rstrip(" \t_").casefold() != label:
        return ""
    return rest.lstrip("_")


def verdict_lines(answer):
    """Each account's verdict lines as (value, references), and the number of
    verdict lines that could not be read."""
    lines, unread = {}, 0
    for line in answer.splitlines():
        text = after_label(line)
        if text is None:
            continue
        rest = REST.fullmatch(text)
        value = rest[2].lower() if rest else None
        if value not in VALUES:
            unread += 1
            continue
        found = (reference.lower() for reference in REFERENCE.findall(rest[3]))
        references = list(dict.fromkeys(found))
        lines.setdefault(rest[1].lower(), []).append((value, references))
    return lines, unread


def proposal_lines(answer):
    """Each account's proposals as (action, permission ID, references), and
    the number of proposal lines that could not be read."""
    lines, unread = {}, 0
    for line in answer.splitlines():
        text = after_label(line, "proposal")
        if text is None:
            continue
        found = PROPOSAL.fullmatch(text)
        if not found:
            unread += 1
            continue
        references = REFERENCE.findall(found[4])
        lines.setdefault(found[1].lower(), []).append(
            (
                found[2].lower(),
                int(found[3]),
                list(dict.fromkeys(r.lower() for r in references)),
            )
        )
    return lines, unread


def proposal_rows(answer):
    """The proposals in the comparison's form, sorted by account, and the
    number of lines that could not be read."""
    lines, unread = proposal_lines(answer)
    rows = [
        {
            "account": name,
            "action": action,
            "permission": permission,
            "references": references,
        }
        for name in sorted(lines)
        for action, permission, references in lines[name]
    ]
    return rows, unread


def judge(configured, observed, found):
    """One account's model value, outcome, and reason, or None for a match."""
    values = {value for value, _ in found}
    model = next(iter(values)) if len(values) == 1 else None
    if configured != observed:
        reason = f"the checks disagree, configured {configured}, observed {observed}"
        return model, "checks-disagree", reason
    if configured == "unknown":
        return model, "checks-unknown", "the checks cannot settle it"
    if not found:
        return None, "no-verdict", "the answer has no verdict line for it"
    if model is None:
        return None, "lines-disagree", "the answer's verdict lines disagree"
    if model == "inconclusive":
        reason = f"the model's verdict is inconclusive, the checks say {configured}"
        return model, "inconclusive", reason
    if model != configured:
        return model, "mismatch", f"the model says {model}, the checks say {configured}"
    return model, "match", None


def compare(job, checks, answer):
    lines, unread = verdict_lines(answer)
    reasons, rows = [], []
    if not checks:
        reasons.append("no checks' verdicts for this job")
    for name in sorted(checks):
        configured, observed = checks[name]["configured"], checks[name]["observed"]
        found = lines.get(name, [])
        model, outcome, reason = judge(configured, observed, found)
        if reason:
            reasons.append(f"{name}: {reason}")
        rows.append(
            {
                "account": name,
                "model": model,
                "references": list(dict.fromkeys(r for _, refs in found for r in refs)),
                "configured": configured,
                "observed": observed,
                "outcome": outcome,
            }
        )
    reasons += [
        f"{name}: not an account the checks name"
        for name in sorted(set(lines) - set(checks))
    ]
    if unread:
        reasons.append(f"verdict lines that could not be read: {unread}")
    proposals, unread_proposals = proposal_rows(answer)
    return {
        "job": job,
        "outcome": "stop" if reasons else "match",
        "reasons": reasons,
        "accounts": rows,
        "proposals": proposals,
        "unread_proposals": unread_proposals,
    }


def table(comparison):
    header = ("ACCOUNT", "MODEL", "REFERENCES", "CONFIGURED", "OBSERVED", "OUTCOME")
    rows = [header] + [
        (
            row["account"],
            row["model"] or "-",
            ",".join(row["references"]) or "-",
            row["configured"],
            row["observed"],
            row["outcome"],
        )
        for row in comparison["accounts"]
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    return "\n".join(
        "  ".join(
            cell.ljust(width) for cell, width in zip(row, widths, strict=True)
        ).rstrip()
        for row in rows
    )


def outcome_line(comparison):
    if comparison["outcome"] == "match":
        return "match"
    return "stop: " + "; ".join(comparison["reasons"])


def main(argv):
    if len(argv) != 3 or not JOB_ID.fullmatch(argv[1]):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    job, answer = argv[1], argv[2]
    try:
        checks = load_checks(VERDICTS, job)
    except Stop as stop:
        proposals, unread_proposals = proposal_rows(answer)
        comparison = {
            "job": job,
            "outcome": "stop",
            "reasons": [str(stop)],
            "accounts": [],
            "proposals": proposals,
            "unread_proposals": unread_proposals,
        }
    else:
        comparison = compare(job, checks, answer)
    COMPARISON.write_text(json.dumps(comparison, indent=2) + "\n")
    line = outcome_line(comparison)
    if comparison["accounts"]:
        print(table(comparison))
    print(line)
    # Without it Argo shows the exit code alone. The log and the output still
    # hold every reason.
    with contextlib.suppress(OSError):
        TERMINATION.write_text(line.encode()[:MESSAGE_BYTES].decode(errors="ignore"))
    return 0 if comparison["outcome"] == "match" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
