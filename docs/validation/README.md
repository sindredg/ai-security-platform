# Validation

What the platform claims, and the check that proves each claim against the running system.

The [worklogs](../worklogs/README.md) are history: what was run on which day. These pages are the present: every claim has an ID, a reason, and a check that can be run again in about two minutes.

## Run the checks

From a workstation on the mesh VPN, signed in to Azure as the operator. The `Z` checks need `python3`:

```bash
export AISEC_SSH="ssh -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o StrictHostKeyChecking=yes -i REPLACE_WITH_OPERATOR_KEY -o IdentitiesOnly=yes"
validation/platform-checks.sh
```

Expected: one `PASS` line per check, a summary, and exit `0`. A `FAIL` prints what was expected and what was found, and the script exits `1`.

| Option | Effect |
| --- | --- |
| `--no-azure` | Skips the `Z` checks. The rest need no Azure sign-in |
| `--no-workstation` | Skips the `M` checks, which test the mesh policy from the machine that runs the script |

A connection check reports `open`, `refused`, `timeout`, or `unreachable`, and each check expects exactly one of them. [Containment](containment.md#what-a-failed-connection-proves) says why.

The script changes nothing. It opens connections that should fail, reads settings, and asks Azure to validate one template that it never deploys.

## Areas

| Page | Checks | What it covers |
| --- | --- | --- |
| [Access](access.md) | `A`, `M` | Who can get in, and through what |
| [Containment](containment.md) | `C`, `E`, `R`, `Z.4` to `Z.9` | What the worker cannot reach, and what the orchestrator can |
| [Package proxy](package-proxy.md) | `P`, `U` | The worker's one path out, and whether updates arrive |
| [Cluster](cluster.md) | `K` | K3s health and the hardening benchmark findings |
| [Host hardening](host-hardening.md) | `HO`, `HW` | SSH daemon, kernel settings, file modes, on both VMs |
| [Azure policy](azure-policy.md) | `Z.1` to `Z.3`, `Z.10` to `Z.12` | Public addresses and the policy that refuses them |

## Last run

| Date | Result | Notes |
| --- | --- | --- |
| 2026-10-11 | 92 of 94 passed | After a restart of both VMs. `M.3` and `M.4` failed: the mesh access policy still allowed every port. See [Access](access.md) |
| 2026-10-11 | 94 of 94 passed | After the mesh access policy was replaced |
| 2026-10-11 | 94 of 94 passed | After the worker was rebuilt from the current template |

These three runs used the first version of the script. It had two weaknesses:

- `Z.4` and `Z.5` compared only the direction, priority, access, and name of each rule, and passed when both Azure calls failed.
- Every connection that did not open counted as closed, whether it timed out or was refused.

So the passes above for `Z.4`, `Z.5`, `C.1` to `C.8`, `E.3`, `M.3`, and `M.4` prove less than they appear to. The script now compares the whole rule and expects a timeout where a rule is the claim. That version has not been run against the system yet. Its first run goes in this table.

## What the checks do not cover

- **A rebuild of the orchestrator.** It was changed by hand to match its template, and whether the template builds the same machine is a different test. The worker has had that test: it was rebuilt from its template and passed every check.
- **The target side.** No target exists yet.
- **Anything a benchmark tool finds.** kube-bench and Lynis results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). The checks here hold the fixes in place.
- **Clean Terraform plans.** `terraform plan -detailed-exitcode` needs each root's own identity. The [runbook](../runbooks/platform-compute.md) has that step.
