# Validation

What the platform claims, and the check that proves each claim against the running system.

The [worklogs](../worklogs/README.md) are history: what was run on which day. These pages are the present: every claim has an ID, a reason, and a check that can be run again in about two minutes.

## Run the checks

From a workstation on the mesh VPN, signed in to Azure as the operator:

```bash
export AISEC_SSH="ssh -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o StrictHostKeyChecking=yes -i REPLACE_WITH_OPERATOR_KEY -o IdentitiesOnly=yes"
validation/platform-checks.sh
```

Expected: one `PASS` line per check, a summary, and exit `0`. A `FAIL` prints what was expected and what was found, and the script exits `1`.

| Option | Effect |
| --- | --- |
| `--no-azure` | Skips the `Z` checks. The rest need no Azure sign-in |
| `--no-workstation` | Skips the `M` checks, which test the mesh policy from the machine that runs the script |

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

## What the checks do not cover

- **A rebuild of the orchestrator.** It was changed by hand to match its template, and whether the template builds the same machine is a different test. The worker has had that test: it was rebuilt from its template and passed every check.
- **The target side.** No target exists yet.
- **Anything a benchmark tool finds.** kube-bench and Lynis results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). The checks here hold the fixes in place.
- **Clean Terraform plans.** `terraform plan -detailed-exitcode` needs each root's own identity. The [runbook](../runbooks/platform-compute.md) has that step.
