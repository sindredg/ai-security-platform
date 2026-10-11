# Troubleshooting

Failures that taught something about the system or a procedure. Each entry records the symptom, the confirmed cause, the fix, and how the fix was verified. A cause that was not confirmed is labeled a hypothesis.

| Entry | Milestone | What it taught |
| --- | --- | --- |
| [01](01-image-version-only-in-daily-offer.md) | 2 | Image lookups match by substring. A pin has to be checked against the exact offer and SKU |
| [02](02-ssh-through-subnet-router-stalls.md) | 2 | A deny-all security group also drops path MTU discovery. The subnet router has to clamp the segment size |
| [03](03-proxy-cannot-fetch-upstream-over-tls.md) | After 2 | The `main` Squid build cannot fetch from a peer over TLS, so closing outbound port 80 costs more than leaving it open |
