#!/usr/bin/env python3
"""A fixture tool for the agent runtime: one MCP tool over stdio.

Serves one fixed piece of synthetic evidence, the same one measure.py uses, so
the agent's numbers can be set beside the model server's. It reads no file and
opens no connection. Standard library only.
"""
import json
import sys

EVIDENCE = {
    "ev-0001": {
        "reference": "ev-0001",
        "collected": "2026-10-11T12:00:00Z",
        "token": "consumer-readonly",
        "contract_object_types": ["dcim.device", "ipam.prefix"],
        "granted_object_types": ["dcim.device", "ipam.prefix", "tenancy.contact", "circuits.circuit"],
        "write_access": False,
    }
}
TOOL = {
    "name": "get_evidence",
    "description": "Return one stored piece of evidence by its reference.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "reference": {"type": "string", "description": "Evidence reference, for example ev-0001"}
        },
        "required": ["reference"],
        "additionalProperties": False,
    },
}


def call(params):
    arguments = params.get("arguments")
    if params.get("name") != TOOL["name"] or not isinstance(arguments, dict) or set(arguments) != {"reference"}:
        return "refused: unknown tool or arguments", True
    if not isinstance(arguments["reference"], str):
        return "refused: unknown tool or arguments", True
    found = EVIDENCE.get(arguments["reference"])
    if found is None:
        return "refused: no such evidence", True
    return json.dumps(found), False


def answer(request):
    method = request.get("method")
    params = request.get("params")
    if not isinstance(params, dict):
        params = {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "evidence", "version": "1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        text, failed = call(params)
        return {"content": [{"type": "text", "text": text}], "isError": failed}
    return None


def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError:
            continue
        if not isinstance(request, dict) or "id" not in request:
            continue  # a notification, or nothing this server answers
        result = answer(request)
        reply = {"jsonrpc": "2.0", "id": request["id"]}
        if result is None:
            reply["error"] = {"code": -32601, "message": "method not found"}
        else:
            reply["result"] = result
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
