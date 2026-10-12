#!/usr/bin/env python3
"""Check one agent run on the fixture question.

Reads the transcript Goose prints with --output-format json on standard input.
Prints one JSON line and exits 0 only if all of this holds:

- the run completed
- the agent asked the fixture tool for ev-0001, and for nothing else
- the tool answered without an error
- the agent's last message names both record types the evidence shows in
  excess

Only the agent's last message is searched. The tool's answer holds the same
two names, so a search of the whole transcript would pass an agent that said
nothing. Standard library only.
"""
import json
import sys

EXCESS = ("tenancy.contact", "circuits.circuit")
WANTED_CALL = ("evidence__get_evidence", {"reference": "ev-0001"})


def main():
    try:
        run = json.load(sys.stdin)
        messages = run["messages"]
        metadata = run["metadata"]
    except (ValueError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "reason": f"not a transcript: {error!r}"}))
        return 1

    calls, tool_errors, answer = [], 0, ""
    for message in messages:
        texts = []
        for part in message.get("content", []):
            kind = part.get("type")
            if kind == "toolRequest":
                value = (part.get("toolCall") or {}).get("value") or {}
                calls.append((value.get("name"), value.get("arguments")))
            elif kind == "toolResponse":
                result = part.get("toolResult") or {}
                if result.get("status") != "success" or (result.get("value") or {}).get("isError"):
                    tool_errors += 1
            elif kind == "text":
                texts.append(part.get("text") or "")
        if message.get("role") == "assistant":
            answer = "\n".join(texts)

    reasons = []
    if metadata.get("status") != "completed":
        reasons.append(f"status is {metadata.get('status')!r}")
    if calls != [WANTED_CALL]:
        reasons.append(f"tool calls were {calls!r}")
    if tool_errors:
        reasons.append(f"{tool_errors} tool errors")
    missing = [name for name in EXCESS if name not in answer]
    if missing:
        reasons.append(f"the last message does not name {missing!r}")

    print(
        json.dumps(
            {
                "ok": not reasons,
                "reason": "; ".join(reasons),
                "tool_calls": len(calls),
                "input_tokens": metadata.get("input_tokens"),
                "output_tokens": metadata.get("output_tokens"),
                "answer": answer,
            }
        )
    )
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
