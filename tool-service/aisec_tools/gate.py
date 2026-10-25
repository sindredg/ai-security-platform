"""The wall. Every request from the worker passes here before the MCP SDK.

Two stages. Gate, in front of the SDK, decides who is calling: the path, the
token, the size, and the shape of the message. Calls, behind the SDK, decides
what that job may do: the tool, the arguments, the limits. Calls is the
authority, because it works on what the SDK parsed and will act on.

Every refusal ends the same way: nothing of a result goes back, and one audit
line records the decision and the reason. Refusals before a token is accepted
are limited per minute. Past the limit, one line says so and the rest get 429
and no line, so a flood cannot fill the audit file.
"""

import hashlib
import json

import anyio
import jsonschema
import mcp_types as types

from .audit import audit
from .http import bearer, caller, read_body, reply

SCOPE_KEY = "aisec.job"


def refused(scope, job, reason):
    audit("request", "refused", caller=caller(scope), job=job and job.id, reason=reason)


class Gate:
    def __init__(self, app, jobs):
        self.app, self.jobs, self.policy = app, jobs, jobs.policy
        self.limit = self.policy["limits"]["untrusted_per_minute"]
        self.minute, self.untrusted = None, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        job, status, reason, body = await self._admit(scope, receive)
        if status in (401, 404) and self._over_limit(scope):
            return await reply(send, 429, {"error": "refused"})
        if reason:
            refused(scope, job, reason)
            return await reply(send, status, {"error": "refused"})
        scope[SCOPE_KEY] = job
        unread = [{"type": "http.request", "body": body, "more_body": False}]

        async def replay():
            return unread.pop() if unread else await receive()

        async def watch(message):
            # The SDK can still refuse what the gate let through. That is a
            # refusal like any other, and it gets its line.
            if message["type"] == "http.response.start" and message["status"] >= 400:
                status = message["status"]
                refused(scope, job, f"refused by the MCP layer, status {status}")
            await send(message)

        await self.app(scope, replay, watch)

    def _over_limit(self, scope):
        """Counts a request without a valid token. True past the limit."""
        minute = int(self.jobs.clock() // 60)
        self.untrusted = self.untrusted + 1 if minute == self.minute else 1
        self.minute = minute
        if self.untrusted == self.limit + 1:
            refused(scope, None, "rate limit reached, no line until the next minute")
        return self.untrusted > self.limit

    async def _admit(self, scope, receive):
        """Returns (job, status, reason, body). A reason means refused."""
        if scope["method"] != "POST" or scope["path"] != "/mcp":
            return None, 404, "not the tool endpoint", None
        token = bearer(scope)
        if token is None:
            return None, 401, "no token, or a malformed one", None
        job, reason = self.jobs.by_token(token)
        if reason:
            return job, 401, reason, None
        body = await read_body(scope, receive, self.policy["limits"]["request_bytes"])
        if body is None:
            return job, 413, "request too large", None
        try:
            jsonschema.validate(json.loads(body), self.policy["message_schema"])
        except (ValueError, jsonschema.ValidationError):
            return job, 400, "not JSON, or not an allowed message", None
        return job, 200, None, body


class Calls:
    """The MCP handlers. `tools` maps a tool name to its function."""

    def __init__(self, jobs, tools):
        self.jobs, self.tools, self.policy = jobs, tools, jobs.policy

    async def list_tools(self, ctx, params):
        job = ctx.request.scope[SCOPE_KEY]
        offered = [
            types.Tool(
                name=name,
                input_schema=spec["input_schema"],
                description=spec["description"],
            )
            for name, spec in self.policy["tools"].items()
            if name in job.tools
        ]
        return types.ListToolsResult(tools=offered)

    async def call_tool(self, ctx, params):
        scope = ctx.request.scope
        job = scope[SCOPE_KEY]
        arguments = params.arguments or {}
        canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        record = {"caller": caller(scope), "job": job.id, "tool": params.name}
        record["args_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        reason, result = await self._decide(job, params.name, arguments)
        if reason:
            audit("call", "refused", reason=reason, **record)
            text = types.TextContent(type="text", text="refused: " + reason)
            return types.CallToolResult(content=[text], is_error=True)
        audit("call", "allowed", result_bytes=len(result.encode()), **record)
        text = types.TextContent(type="text", text=result)
        return types.CallToolResult(content=[text])

    async def _decide(self, job, name, arguments):
        """Returns (reason, None) for a refusal or (None, result text)."""
        reason = self.jobs.count_call(job)
        if reason:
            return reason, None
        if name not in job.tools or name not in self.tools:
            return "tool not in the job's scope", None
        try:
            jsonschema.validate(arguments, self.policy["tools"][name]["input_schema"])
        except jsonschema.ValidationError:
            return "arguments do not match the schema", None
        reason, text = await anyio.to_thread.run_sync(self.tools[name], job, arguments)
        if reason:
            return reason, None
        if len(text.encode()) > self.policy["limits"]["result_bytes"]:
            return "result too large", None
        # The job can end while the tool runs. A late result is dropped.
        reason = self.jobs.ended(job)
        return (reason, None) if reason else (None, text)
