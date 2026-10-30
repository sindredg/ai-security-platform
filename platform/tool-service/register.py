"""A registration client, for the checks in the runbook until dispatch exists.

Runs inside a pod in the orchestration namespace, as the dispatch account,
with that account's token projected for the tool service. Standard library
only. It reads its arguments from the first line of standard input, so that
nothing about the job is in the pod's spec.

    register JOB TOKEN_SHA256 [TOKEN_OVERRIDE|-] [SECONDS] [TARGET]
    revoke JOB [- TOKEN_OVERRIDE]

TOKEN_OVERRIDE replaces the projected token. The negative checks use it to
present a token that should be refused. "-" keeps the projected token.
SECONDS is the job's lifetime, 600 by default. The expiry check uses a short
one so that it does not wait ten minutes. TARGET is the job's target,
synthetic by default; the forbidden calls drill registers netbox jobs, whose
documents are the ones collected under the job's name.
"""

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://tool-service.tool-services.svc:8444/jobs"
TOKEN = "/var/run/secrets/aisec/token"
CERT = "/etc/aisec/tls.crt"


def main():
    args = sys.stdin.readline().split()
    action, job = args[0], args[1]
    override = args[3] if len(args) > 3 and args[3] != "-" else None
    token = override or Path(TOKEN).read_text().strip()
    context = ssl.create_default_context(cafile=CERT)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if action == "register":
        target = args[5] if len(args) > 5 else "synthetic"
        body = {"job": job, "target": target, "tools": ["get_evidence"]}
        seconds = int(args[4]) if len(args) > 4 else 600
        body |= {"seconds": seconds, "token_sha256": args[2]}
        data, method, url = json.dumps(body).encode(), "POST", URL
    else:
        data, method, url = None, "DELETE", URL + "/" + job
    request = urllib.request.Request(url, data, headers, method=method)
    try:
        with urllib.request.urlopen(request, context=context, timeout=10) as response:
            print(response.status, response.read().decode())
    except urllib.error.HTTPError as error:
        print(error.code, error.read().decode())
        sys.exit(1)


if __name__ == "__main__":
    main()
