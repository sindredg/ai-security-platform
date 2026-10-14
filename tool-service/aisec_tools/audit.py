"""The audit line. One JSON object per decision, on standard output.

Standard output carries nothing else. The host captures it and appends it to
a file the service cannot open. No payloads: arguments go in as a digest and
results as a size. A token is never an argument to this function.
"""

import json
import sys
import time

FIELDS = ("job", "caller", "tool", "args_sha256", "reason", "result_bytes")


def audit(event, decision, **fields):
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    line |= {"event": event, "decision": decision}
    line |= {name: fields.get(name) for name in FIELDS}
    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
    sys.stdout.flush()
