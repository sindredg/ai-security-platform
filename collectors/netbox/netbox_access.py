"""What each account in NetBox's consumer contract may see, by two methods.

ADR 0037. Exercise 1's finding needs both to agree, and a disagreement is the
result, not a tie for one side to win.

  configured  On the orchestrator, with the collector's token. Reads every
              enabled permission that applies to each account, directly or
              through a group, adds them up per object type and action, and
              compares the sum with the contract's grants.
  observed    On the lab VM, the consumer viewpoint, with each account's own
              token. Reads the contract's endpoints, compares the records that
              come back with the contract's, and tries each expected denial.

Each account gets a verdict: excess (it sees more than the contract allows),
missing (a read the contract needs fails, so the contract is broken), unknown
(a constraint the configured check cannot compare, or a denial with another
answer than the contract's), or within. The reasons and the answers they rest
on come with it.

The contract arrives on standard input, so the script can be sent to a host as
an argument and read nothing but the token from that host's disk. NetBox's
answers are the target's, and a compromised target shapes them: this script
follows no link and no redirect from them, builds every URL itself, and holds
no answer and no list longer than the limits below.

Usage: netbox_access.py configured|observed [--summary] < contract.json
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

# The live NetBox's, unless the environment names the rehearsal copy's on the
# lab VM (platform ADR 0044).
URL = os.environ.get("AISEC_NETBOX_URL", "https://10.50.0.4:8443")
CERT = os.environ.get("AISEC_NETBOX_CERT", "/etc/aisec/netbox/tls.crt")
TOKEN_DIR = os.environ.get("AISEC_NETBOX_TOKENS", "/etc/aisec/netbox/tokens")
COLLECTOR = "aisec-collector"
PAGE = 1000
# NetBox is target side, so neither the size of an answer nor the length of
# a list is its to choose. Both are far beyond the lab's inventory.
ANSWER_BYTES = 8 << 20
RECORDS = 10000
VERDICTS = ("excess", "missing", "unknown")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses redirects, which would carry the token to another address."""

    def redirect_request(self, *args):
        return None


class NetBox:
    def __init__(self, token):
        context = ssl.create_default_context(cafile=CERT)
        # The orchestrator's proxy settings name Squid on the edge. NetBox is
        # reached directly, so the proxy handler has no proxies.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
            NoRedirect(),
        )
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def call(self, method, path, body=None):
        """Returns NetBox's status code and its answer, parsed if JSON."""
        data = None if body is None else json.dumps(body).encode()
        # The URL is NetBox's fixed address and a path from this script or the
        # contract, never one from an answer.
        request = urllib.request.Request(  # noqa: S310
            URL + path, data=data, method=method, headers=self.headers
        )
        try:
            with self.opener.open(request, timeout=30) as answer:
                status, text = answer.status, answer.read(ANSWER_BYTES + 1)
        except urllib.error.HTTPError as error:
            status, text = error.code, error.read(ANSWER_BYTES + 1)
        if len(text) > ANSWER_BYTES:
            return 0, f"an answer larger than {ANSWER_BYTES} bytes"
        try:
            return status, json.loads(text) if text else None
        except ValueError:
            return status, text[:200].decode(errors="replace")

    def list(self, path, **query):
        """Every record of a list endpoint, or the status that refused it.

        0 stands for an answer that is not a list of records.
        """
        results, offset = [], 0
        while True:
            query.update(limit=PAGE, offset=offset)
            status, answer = self.call("GET", f"{path}?{urllib.parse.urlencode(query)}")
            if status != 200:
                return status, answer
            if not isinstance(answer, dict):
                return 0, "an answer that is not an object"
            page, count = answer.get("results"), answer.get("count")
            if not isinstance(page, list) or not isinstance(count, int):
                return 0, "an answer without a list of results and a count"
            if not all(isinstance(r, dict) for r in page):
                return 0, "a result that is not an object"
            results.extend(page)
            if len(results) > RECORDS:
                return 0, f"more than {RECORDS} records"
            offset += len(page)
            if not page or offset >= count:
                return 200, results


def read_token(account):
    with open(os.path.join(TOKEN_DIR, account)) as file:
        return file.read().strip()


def verdict(reasons):
    for kind in VERDICTS:
        if any(r["kind"] == kind for r in reasons):
            return kind
    return "within"


def scope(constraints):
    """A permission's constraints as a list of filters, or None for every object.

    NetBox takes one filter or a list of them, any of which may match. An
    empty one matches every object.
    """
    if not constraints:
        return None
    filters = constraints if isinstance(constraints, list) else [constraints]
    return None if any(not f for f in filters) else filters


def judge_configured(permissions, contract):
    """The configured check's reasons for one account's enabled permissions,
    each with the IDs of the permissions it rests on. The configured check
    reports the reasons without the IDs. The policy on a proposed fix reads
    them (platform ADR 0043)."""
    wanted = {
        (g["object_type"], g["action"]): g["constraints"] for g in contract["grants"]
    }
    granted, reasons = {}, []
    for p in permissions:
        for object_type in p["object_types"]:
            for action in p["actions"]:
                granted.setdefault((object_type, action), []).append(p)
    for (object_type, action), grants in sorted(granted.items()):
        names = ", ".join(p["name"] for p in grants)
        if (object_type, action) not in wanted:
            why = f"{action} on {object_type}, which the contract does not grant"
            ids = [p["id"] for p in grants]
            reasons.append(
                {"kind": "excess", "why": f"{why} ({names})", "permissions": ids}
            )
            continue
        want = scope(wanted[(object_type, action)])
        for p in grants:
            have = scope(p["constraints"])
            if have is None:
                why = f"{action} on {object_type} without a constraint ({p['name']})"
                reasons.append({"kind": "excess", "why": why, "permissions": [p["id"]]})
            elif have != want:
                why = f"{action} on {object_type} with {have}, not the contract's"
                reasons.append(
                    {
                        "kind": "unknown",
                        "why": f"{why} ({p['name']})",
                        "permissions": [p["id"]],
                    }
                )
    for object_type, action in wanted:
        if (object_type, action) not in granted:
            why = f"no permission grants {action} on {object_type}"
            reasons.append({"kind": "missing", "why": why, "permissions": []})
    return reasons


def configured(contract):
    netbox = NetBox(read_token(COLLECTOR))
    accounts = {}
    for account in contract["accounts"]:
        reasons, permissions = [], {}
        status, users = netbox.list("/api/users/users/", username=account)
        if status != 200:
            reasons.append({"kind": "missing", "why": f"users: {status} {users}"})
        elif len(users) != 1 or not users[0].get("is_active"):
            reasons.append({"kind": "missing", "why": "no active account by that name"})
        else:
            user = users[0]
            sources = [("user", {"user_id": user["id"]})] + [
                (f"group {g['name']}", {"group_id": g["id"]})
                for g in user.get("groups", [])
            ]
            for via, query in sources:
                status, found = netbox.list("/api/users/permissions/", **query)
                if status != 200:
                    reasons.append({"kind": "missing", "why": f"permissions: {status}"})
                    continue
                for p in found:
                    if p.get("enabled"):
                        permissions.setdefault(p["id"], dict(p, via=via))
        reasons += [
            {"kind": r["kind"], "why": r["why"]}
            for r in judge_configured(list(permissions.values()), contract)
        ]
        evidence = [
            {
                k: p.get(k)
                for k in ("id", "name", "object_types", "actions", "constraints", "via")
            }
            for p in permissions.values()
        ]
        accounts[account] = {
            "verdict": verdict(reasons),
            "reasons": reasons,
            "permissions": evidence,
        }
    return accounts


def observed(contract):
    accounts = {}
    for account in contract["accounts"]:
        netbox = NetBox(read_token(account))
        reasons, reads, denials = [], {}, []
        for read in contract["reads"]:
            path, key = read["path"], read["key"]
            status, records = netbox.list(path)
            if status != 200:
                reasons.append(
                    {"kind": "missing", "why": f"{path}: {status} {records}"}
                )
                continue
            got = sorted(str(r.get(key)) for r in records)
            reads[path] = got
            for extra in sorted(set(got) - set(read["records"])):
                reasons.append({"kind": "excess", "why": f"{path}: {extra}"})
            for lost in sorted(set(read["records"]) - set(got)):
                reasons.append({"kind": "missing", "why": f"{path}: no {lost}"})
            for r in records:
                lacking = [f for f in read["fields"] if f not in r]
                if lacking:
                    why = f"{path}: {r.get(key)} lacks {', '.join(lacking)}"
                    reasons.append({"kind": "missing", "why": why})
        for denial in contract["denials"]:
            method, path = denial["method"], denial["path"]
            body = {} if method != "GET" else None
            status, _ = netbox.call(method, path, body)
            denials.append({"method": method, "path": path, "status": status})
            if status == denial["status"]:
                continue
            kind = "excess" if 200 <= status < 300 else "unknown"
            why = f"{method} {path}: {status}, the contract says {denial['status']}"
            reasons.append({"kind": kind, "why": why})
        accounts[account] = {
            "verdict": verdict(reasons),
            "reasons": reasons,
            "reads": reads,
            "denials": denials,
        }
    return accounts


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("configured", "observed") or sys.argv[2:] not in (
        [],
        ["--summary"],
    ):
        sys.exit(
            "usage: netbox_access.py configured|observed [--summary] < contract.json"
        )
    contract = json.load(sys.stdin)
    accounts = configured(contract) if mode == "configured" else observed(contract)
    if sys.argv[2:]:
        print(" ".join(f"{a}:{v['verdict']}" for a, v in accounts.items()))
    else:
        print(json.dumps({"check": mode, "accounts": accounts}, indent=2))


if __name__ == "__main__":
    main()
