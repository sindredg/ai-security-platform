"""A registration client, for the checks in the runbook until dispatch exists.

Runs inside a pod in the orchestration namespace, as the dispatch account,
with that account's token projected for the tool service. Standard library
only. It reads its arguments from the first line of standard input, so that
nothing about the job is in the pod's spec.

    register JOB TOKEN_SHA256
    revoke JOB

TOKEN_OVERRIDE on the first line, after the arguments, replaces the projected
token. The negative checks use it to present a token that should be refused.
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
    token = args[3] if len(args) > 3 else Path(TOKEN).read_text().strip()
    context = ssl.create_default_context(cafile=CERT)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if action == "register":
        body = {"job": job, "target": "synthetic", "tools": ["get_evidence"]}
        body |= {"seconds": 600, "token_sha256": args[2]}
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
