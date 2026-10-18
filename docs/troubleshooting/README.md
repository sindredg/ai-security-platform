# Troubleshooting

Failures that taught something about the system or a procedure. Each entry records the symptom, the confirmed cause, the fix, and how the fix was verified. A cause that was not confirmed is labeled a hypothesis.

| Entry | Milestone | What it taught |
| --- | --- | --- |
| [01](01-image-version-only-in-daily-offer.md) | 2 | Image lookups match by substring. A pin has to be checked against the exact offer and SKU |
| [02](02-ssh-through-subnet-router-stalls.md) | 2 | A deny-all security group also drops path MTU discovery. The subnet router has to clamp the segment size |
| [03](03-proxy-cannot-fetch-upstream-over-tls.md) | After 2 | The `main` Squid build cannot fetch from a peer over TLS, so closing outbound port 80 costs more than leaving it open |
| [04](04-default-service-account-already-exists.md) | 3 | Kubernetes creates each namespace's default service account on its own. A manifest that sets it has to wait for it |
| [05](05-failed-logins-block-every-routed-session.md) | 3a | sshd penalises a source address after failed logins, and every routed session reaches the worker from one address. A few refused logins block the feed and the journal pull too |
| [06](06-rebuilt-network-leaves-peering-disconnected.md) | 3a | A network rebuilt under the same name keeps its ID, so Terraform sees no change on the other side, while Azure keeps that half of the peering disconnected until it is re-created |
| [07](07-image-pull-refused-in-a-fetch-window.md) | 3a | A pull answered from the node's cache never reaches the layer host. A proxy's host list is tested with a pull that downloads |
| [08](08-monitoring-providers-not-registered.md) | 3a | A resource provider has to be registered before its first resource, and neither deployment identity may register one. The bootstrap root does it |
| [09](09-traffic-analytics-refuses-the-platform-identity.md) | 3a | Traffic analytics checks its rights on the workspace's whole subscription, so an identity scoped to one group cannot turn it on |
