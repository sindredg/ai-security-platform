# 0044. The rehearsal copy is a second NetBox on the lab VM, with its own interface in the rehearsal subnet

Status: Accepted
Date: 2026-10-26

## Context

Milestone 5 rehearses a proposed fix on a copy of the target before a pull request, and the threat model asks for a rehearsal against the consumer contract (T27). The target network has a rehearsal subnet, `10.50.1.0/27`, with nothing in it. `C.3` probes it, so its timeout proves nothing about the deny rule ([#23](https://github.com/sindredg/ai-security-platform/issues/23)).

What is fixed already:

- **Two VMs fill the region.** The NetBox VM and the lab VM use Poland Central's 4 vCPUs, and the quota cannot be raised.
- **The lab VM is the consumer's viewpoint.** It holds the consumer's and the control account's tokens, and the observer account runs the collector's observed half there ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)).
- **A token is limited to the address NetBox sees** ([0039](0039-netbox-takes-a-clients-address-from-the-connection.md)).

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| A third VM in the rehearsal subnet | A copy apart from both targets | Does not fit the quota |
| A second NetBox on the lab VM, with its own interface in the rehearsal subnet | Fits. The copy listens in its own subnet, so `C.3` gets a target | The lab VM holds the consumer's viewpoint and the copy. Two interfaces need policy routing |
| A second NetBox on the NetBox VM | Fits, beside the image it copies | The copy shares the live target's machine and secret store |
| Rehearse on the live NetBox, then restore | No copy | The target changes before anyone approves |
| A copy on the lab VM's loopback, driven over the observer's SSH | No second interface | The copy is off the subnet, and [#23](https://github.com/sindredg/ai-security-platform/issues/23) stays open |

## Decision

**The rehearsal copy is a second NetBox on the lab VM.** It runs from the same pinned image, with its own TLS key, secrets, tokens, and synthetic data from the seed.

- **Its own interface** in the rehearsal subnet, at `10.50.1.4`. Traffic from that address leaves through that interface, by policy routing. Without it, the copy's replies would leave through the lab VM's first interface with the wrong source, and Azure would drop them.
- **Port 8443 from the orchestrator only.** The rehearsal subnet's rules allow nothing else in, as for the other target subnets.
- **Reset before each rehearsal.** A dump taken right after the seed is restored, the cache is flushed, and the units restart. A forced-command account on the lab VM runs the reset, with a key root keeps on the orchestrator.
- **The copy is target side.** A passed rehearsal is evidence that the fix keeps the contract. The proof is the check after delivery on the live target ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)).
- **The fallback, with the operator's consent:** the copy on the lab VM's loopback, driven over the observer's SSH, if the second interface cannot work.

## Trade-offs

- **The lab VM carries more.** NetBox, its worker, PostgreSQL, and Valkey run beside the consumer's viewpoint, and the VM has 8 GB.
- **A compromised lab VM controls the copy and its verdicts.** That is why a rehearsal is evidence and not proof.
- **The copy is the seed, not the live target's state.** A drift on the live NetBox is not in the copy, so delivery checks for drift itself ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)).
- **Not seen when this was written:** the lab VM with a second interface, the provider updating the VM in place to add it, and the address the copy sees from the lab VM's own observer.
