"""Starts the two listeners.

Everything the service reads is under one directory, /aisec in the container.
AISEC_ROOT moves it, for a run outside one.

    policy.json     policies/tool-service.json: the rules, limits, and listeners
    evidence/       one directory of evidence per target, read-only
    tls/tls.crt     the server certificate, and
    tls/tls.key     its key. Both listeners use it
    sa-signer.pub   the cluster's service account signing key, public half
"""

import asyncio
import json
import os
import ssl
from pathlib import Path

import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings

from .gate import Calls, Gate
from .jobs import Jobs
from .registration import CallerCheck, Registration
from .tools import make_tools


def build(root):
    """Returns (policy, tool app, registration app)."""
    policy = json.loads((root / "policy.json").read_text(encoding="utf-8"))
    jobs = Jobs(policy)
    calls = Calls(jobs, make_tools(root))
    handlers = {"on_list_tools": calls.list_tools, "on_call_tool": calls.call_tool}
    # Stateless, with plain JSON replies: no session to steal and no stream to
    # hold open. The SDK's own size limit and Host check stay on, behind the gate.
    name = "{tls_name}:{tool_port}".format(**policy["listeners"])
    mcp_app = Server("aisec-tools", **handlers).streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=policy["limits"]["request_bytes"],
        transport_security=TransportSecuritySettings(allowed_hosts=[name]),
    )
    signer = (root / "sa-signer.pub").read_bytes()
    check = CallerCheck(signer, **policy["registration_caller"])
    return policy, Gate(mcp_app, jobs), Registration(jobs, check)


def listener(app, root, bind, port):
    config = uvicorn.Config(
        app,
        host=bind,
        port=port,
        ssl_certfile=root / "tls" / "tls.crt",
        ssl_keyfile=root / "tls" / "tls.key",
        access_log=False,
        server_header=False,
        log_level="warning",
        limit_concurrency=16,
        timeout_keep_alive=5,
    )
    config.load()
    config.ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    return uvicorn.Server(config)


async def main():
    root = Path(os.environ.get("AISEC_ROOT", "/aisec"))
    policy, tool_app, register_app = build(root)
    where = policy["listeners"]
    tool = listener(tool_app, root, where["bind"], where["tool_port"])
    register = listener(register_app, root, where["bind"], where["register_port"])
    await asyncio.gather(tool.serve(), register.serve())


if __name__ == "__main__":
    asyncio.run(main())
