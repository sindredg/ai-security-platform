# 05. Failed logins to the worker block every routed session for a while

Date: 2026-10-16
Milestone: 3a, edge network and monitoring

## Symptom

During the [SSH certificate rollout](../runbooks/ssh-certificates.md), four test logins to the worker were refused as intended. The next connection to the worker, a few seconds later, closed before authentication:

```text
Connection closed by 10.40.0.36 port 22
```

A login 40 seconds later worked.

## Cause

Confirmed from the worker's sshd log. OpenSSH 10.2 penalises a source address after failed authentication (`PerSourcePenalties`, on by default). While the penalty lasts, sshd drops every new connection from that address before authentication:

```text
srclimit_penalise: <addr>/32: activating ipv4 penalty of 17 seconds for penalty: failed authentication
drop connection #0 from [<addr>]:54414 on [<addr>]:22 penalty: failed authentication
```

`sshd -T` on the worker shows the defaults: `authfail:5`, five seconds per failed authentication, `min:15`, and `max:600`.

Every routed session reaches the worker from one address. The mesh node translates the operator's sessions to `10.40.0.4`, the orchestrator's address. The orchestrator's own feed and journal pull come from the same address. A penalty earned by any of them blocks all of them.

The orchestrator has the same setting. Its logins come from each device's tailnet address, so a penalty there blocks only the device that failed.

## Fix

The rollout script waits for a login to work again after the refused logins, up to two minutes, before the next step. It took about 25 seconds on the orchestrator.

The setting on the worker is unchanged. Exempting `10.40.0.4` would stop the operator's own test logins from blocking the feed and the journal pull. It would also stop sshd from slowing down a guessing attack from the orchestrator. Key and certificate logins make guessing hopeless, so the exemption costs little, but it is a change to the worker's SSH daemon and is tracked in [#87](https://github.com/sindredg/ai-security-platform/issues/87). The router slice changes the address that routed sessions come from, so the question comes back there.

## Verification

The resumed run passed on the worker after the wait, and on the orchestrator, where the script waited about 25 seconds for the penalty to end. The worklog has the [run](../worklogs/0004-edge-network-and-monitoring.md#rollout-1).
