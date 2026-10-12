#!/usr/bin/env python3
"""Measure the model server on the worker.

Runs the same three-turn exchange several times against the local server: a
question that needs a tool, the tool call, and a final answer held to a JSON
schema. Prints one line per turn with the server's own token counts and
timings, then a summary. Standard library only.

Usage: measure.py [--runs N] [--url URL]
"""
import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

SYSTEM = (
    "You investigate security findings for an infrastructure team. You have no "
    "knowledge of the systems involved beyond what tools return. Call a tool to "
    "get evidence before you conclude anything. Never guess a fact a tool can "
    "establish. Keep answers short."
)
QUESTION = (
    "Finding F-0001 says the API token 'consumer-readonly' can list more record "
    "types than its consumer needs. The evidence is stored under the reference "
    "ev-0001. Is the finding confirmed?"
)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_evidence",
            "description": "Return one stored piece of evidence by its reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Evidence reference, for example ev-0001",
                    }
                },
                "required": ["reference"],
                "additionalProperties": False,
            },
        },
    }
]
EVIDENCE = json.dumps(
    {
        "reference": "ev-0001",
        "collected": "2026-10-11T12:00:00Z",
        "token": "consumer-readonly",
        "contract_object_types": ["dcim.device", "ipam.prefix"],
        "granted_object_types": ["dcim.device", "ipam.prefix", "tenancy.contact", "circuits.circuit"],
        "write_access": False,
    }
)
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "finding": {"type": "string"},
        "confirmed": {"type": "boolean"},
        "excess": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["finding", "confirmed", "excess", "evidence"],
    "additionalProperties": False,
}


def chat(url, body):
    request = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"HTTP {error.code}: {error.read().decode(errors='replace')}")
    return reply, time.monotonic() - start


def record(rows, mode, run, turn, reply, wall, ok):
    timings = reply.get("timings", {})
    row = {
        "mode": mode,
        "run": run,
        "turn": turn,
        "ok": ok,
        "wall_s": round(wall, 2),
        "prompt_tokens": timings.get("prompt_n"),
        "cached_tokens": timings.get("cache_n"),
        "prompt_tok_s": round(timings.get("prompt_per_second") or 0, 1),
        "output_tokens": timings.get("predicted_n"),
        "output_tok_s": round(timings.get("predicted_per_second") or 0, 1),
    }
    rows.append(row)
    print(json.dumps(row), flush=True)


def exchange(url, mode, run, rows):
    thinking = mode == "thinking"
    base = {
        "model": "local",
        "temperature": 0,
        "max_tokens": 1024,
        "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": QUESTION},
    ]

    reply, wall = chat(url, {**base, "messages": messages, "tools": TOOLS})
    message = reply["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    ok = False
    if len(calls) == 1 and calls[0]["function"]["name"] == "get_evidence":
        try:
            ok = json.loads(calls[0]["function"]["arguments"]) == {"reference": "ev-0001"}
        except ValueError:
            ok = False
    record(rows, mode, run, "tool call", reply, wall, ok)
    if not ok:
        print(json.dumps({"unexpected": message}), flush=True)
        return

    messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
    messages.append({"role": "tool", "tool_call_id": calls[0].get("id", "call_0"), "content": EVIDENCE})
    # No tools on this turn: the server refuses a response schema together with
    # tool definitions ("failed to parse grammar").
    reply, wall = chat(
        url,
        {
            **base,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "verdict", "strict": True, "schema": VERDICT_SCHEMA},
            },
        },
    )
    content = reply["choices"][0]["message"].get("content") or ""
    try:
        verdict = json.loads(content)
        ok = (
            set(verdict) == set(VERDICT_SCHEMA["required"])
            and verdict["confirmed"] is True
            and sorted(verdict["excess"]) == ["circuits.circuit", "tenancy.contact"]
        )
    except ValueError:
        verdict, ok = content, False
    record(rows, mode, run, "verdict", reply, wall, ok)
    if not ok:
        print(json.dumps({"unexpected": verdict}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    rows = []
    for mode in ("no thinking", "thinking"):
        for run in range(1, args.runs + 1):
            exchange(args.url, mode, run, rows)

    print()
    print("| Mode | Turn | Correct | Prompt tokens | Output tokens | Prompt tokens/s | Output tokens/s | Seconds per turn |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for mode in ("no thinking", "thinking"):
        for turn in ("tool call", "verdict"):
            group = [r for r in rows if r["mode"] == mode and r["turn"] == turn]
            if not group:
                continue

            def median(key, group=group):
                return statistics.median(r[key] for r in group)

            print(
                f"| {mode} | {turn} | {sum(r['ok'] for r in group)} of {len(group)} "
                f"| {median('prompt_tokens'):.0f} | {median('output_tokens'):.0f} "
                f"| {median('prompt_tok_s'):.1f} | {median('output_tok_s'):.1f} | {median('wall_s'):.1f} |"
            )


if __name__ == "__main__":
    main()
