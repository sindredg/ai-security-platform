# 0018. A host rule keeps pods off the internet

Status: Accepted
Date: 2026-10-15

## Context

[0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) puts default-deny egress on every workload namespace, so that a compromised pod cannot use the orchestrator's open ports 443 and 80. It narrows T05. K3s enforces network policies with kube-router.

kube-router writes a pod's firewall chain after the pod starts. Until then, the pod's traffic goes out like the host's. Observed on 2026-10-15: a pod with the dispatch label in `orchestration` opened a TCP connection to `1.1.1.1:443` at 0.0 seconds, and was refused at 5.0 and at 20.0 seconds. A compromised image needs no more than that first second.

The policies also leave a second path. CoreDNS forwards every name outside the cluster to Azure DNS, from its own pod address. `dispatch-egress` allows DNS to CoreDNS, so a dispatch pod can carry data out in the names it asks for. The worker already refuses Azure DNS for this reason (`deny-to-azure-dns`).

Nothing in the cluster needs the internet or a public name today. Image pulls run in containerd on the host, not in a pod. The API server, the kubelet, and the metrics are on the host's own addresses, which a pod reaches without the host forwarding anything.

## Options

| Option | Covers the first seconds | Covers DNS | Cost |
| --- | --- | --- | --- |
| Network policies alone | No | No | Nothing more |
| Make pods wait at start: an init container or a readiness gate | No. A compromised image does not wait | No | A wait in every pod |
| Another policy engine that enforces before the pod runs, such as Cilium | Yes | No | The cluster's network replaced, for one gap. A large component to run and patch |
| The Azure security group | No. Pod traffic leaves with the node's address after NAT, so the group cannot tell a pod from the host | No | Nothing |
| An nftables rule on the orchestrator: forwarded traffic from the pod network goes to the pod network, or nowhere | Yes. It holds from boot, before any pod | Yes. CoreDNS can no longer reach Azure DNS | One more host rule set. Every pod that later needs the internet is an explicit exception in it |

## Decision

A host rule on the orchestrator drops forwarded traffic from the pod network (`10.42.0.0/16`) to any address outside it. Replies on connections that came in, such as the worker's tool calls, pass. The rule is in its own table, `inet aisec_pod_egress`, loaded from `/etc/aisec/pod-egress.nft` by a oneshot unit that runs before K3s. It follows the segment size clamp: cloud-init writes both.

The chain runs after the iptables `FORWARD` chain, at `filter + 10`. A pod with a policy is still refused by kube-router first, so `T.8` keeps testing the network policy. The host rule drops what kube-router let through: the first seconds of a pod, and CoreDNS's queries to Azure DNS. Its counter shows how often that happens.

Network policies stay. They decide which pod talks to which inside the cluster. The host rule is the outer limit.

Checks:

- A new check reads the loaded table and compares it with the file.
- The proof that a new pod is blocked from its first packet is a procedure step, not part of `platform-checks.sh`, because it creates a pod and the script only reads. A pod probes `1.1.1.1:443` at 0, 5, and 20 seconds and expects no `open`. The same probe with the table removed, run once, is the broken input.

## Trade-offs

- **Pods cannot resolve public names.** CoreDNS still answers names in the cluster and the node's hosts entries. A name outside them fails after CoreDNS's upstream timeout, not at once.
- **Every future need for the internet from a pod is an exception in this file.** Argo, and anything in milestone 5 that opens pull requests, will need a look. That is the intent: a pod's way out is written down on the host, not granted by default.
- **It binds forwarded traffic only.** A process on the host keeps the host's egress, as before. A pod that breaks out to the host is T05, not this record.
- **Two layers can disagree.** If a later policy allows a pod out and this rule does not, the rule wins and the pod times out. The fix is an exception here, in the same change as the policy.
- **IPv6 is not covered by the rule.** Pods get IPv4 addresses only, and the host does not forward IPv6 (`net.ipv6.conf.all.forwarding = 0`). A cluster with IPv6 would need the same rule for it.
