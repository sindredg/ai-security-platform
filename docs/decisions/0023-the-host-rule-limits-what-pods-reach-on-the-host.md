# 0023. The host rule also limits what pods reach on the host

Status: Proposed
Date: 2026-10-16

Adds to [0018](0018-a-host-rule-keeps-pods-off-the-internet.md).

## Context

0018's rule drops forwarded traffic from the pod network to anything outside it. It binds the `forward` hook only. Traffic from a pod to one of the orchestrator's own addresses is not forwarded. It goes to the `input` hook, where the iptables `INPUT` policy is `ACCEPT` and nothing else stops a pod.

So any pod reaches every port the host listens on. Read on 2026-10-16: SSH on 22, the API server on 6443, the kubelet on 10250, and, until [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) removes it, the mesh agent's peer service on the tailnet address. The mesh agent's own input chain drops only tailnet sources arriving on the wrong interface, so a pod's `10.42.x.x` source passes it.

Network policies are the only limit, and they have the gaps 0018 found. kube-router writes a pod's chain after the pod starts, so the first seconds are open. A namespace without a policy has no limit at all, and `kube-system` has none.

What pods use on the host, read from the established connections on the orchestrator on 2026-10-16:

| Pod | Host port | What for |
| --- | --- | --- |
| `coredns` | 6443 | The API server, reached through the `kubernetes` service and rewritten to the node's address |
| `local-path-provisioner` | 6443 | The same |
| `metrics-server` | 6443 and 10250 | The API server, and the kubelet it reads metrics from |
| `tool-service` | None | |

Every other connection between a pod and the host was started by the host: the kubelet's probes and the API server's calls to `metrics-server`.

## Options

| Option | First seconds of a pod | Namespaces without a policy | Cost |
| --- | --- | --- | --- |
| Network policies for host traffic, in every namespace | No | Only where someone writes one | A policy per namespace, `kube-system` included, and the gaps of 0018 |
| Bind host services to fewer addresses | Yes, for those services | Yes | SSH and the kubelet still have to listen on the node's address for the worker and the API server |
| An `input` chain in 0018's table: pods reach the host on the ports they use, and nothing else | Yes. It is loaded before K3s | Yes | Every new need for the host from a pod is an exception in the file |

## Decision

0018's table gets a second chain, on the `input` hook at the same priority as its `forward` chain:

```text
chain input {
  type filter hook input priority filter + 10; policy accept;
  ip saddr 10.42.0.0/16 ct state established,related accept
  ip saddr 10.42.0.0/16 tcp dport { 6443, 10250 } accept
  ip saddr 10.42.0.0/16 counter drop
}
```

- Replies on connections the host started pass, so probes and the API server's calls still work.
- New connections from any pod to the host's API server and kubelet pass. Both require authentication. The API server refuses anonymous requests (`K.7`). The kubelet does too: its configuration from K3s, `/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/00-k3s-defaults.conf`, has `anonymous: enabled: false` and webhook authorization, read on 2026-10-16. No check reads it yet.
- Everything else from a pod to the host is dropped and counted: SSH, the tailnet address, and any port opened later.
- The file and the unit stay as 0018 set them. The chain loads with the table, before K3s.

The rule cannot tell one pod from another. Which pod may use 6443 or 10250 stays a network policy decision. The rule is the outer limit, as in 0018.

**Checks**

- `E.6` compares the loaded `forward` chain with the expected rules. A new check, `E.8`, does the same for the `input` chain, with the counter values taken out.
- A new check, `K.8`, reads the kubelet's anonymous setting from that file and expects `false`.
- A procedure step, like 0018's probe: a new pod in `orchestration` tries `10.40.0.4:22` and `10.42.0.1:22` and expects no `open`, and tries `10.40.0.4:6443` and expects `open`. The same probe with the table removed, run once, is the broken input: port 22 opens.

## Trade-offs

- **Every pod can still reach the API server and the kubelet.** A pod with a stolen token gets what the token allows. The rule does not narrow it, and network policies do so only where they exist.
- **A new component that needs the host is an exception in this file.** Argo's controller talks to the API server, which is already allowed. Anything that needs another host port gets a line here, in the same change.
- **A pod that runs on the host network bypasses it.** Its traffic has the host's address. The restricted pod security level refuses host networking in the workload namespaces, and #70 extends that to the rest.
- **IPv6 is not covered,** as in 0018. Pods have IPv4 addresses only.
