# 0038. NetBox's TLS key is made on the NetBox VM, and the orchestrator pins the certificate

Status: Accepted
Date: 2026-10-24

Changes point 5 of [0035](0035-netbox-from-its-image-with-the-database-from-ubuntu.md): where the certificate is made.

## Context

[0035](0035-netbox-from-its-image-with-the-database-from-ubuntu.md) puts TLS on NetBox's port, with a certificate made on the orchestrator, which the collector and the consumer pin, "as for the tool service". The tool service's key is made on the machine that serves it and never leaves it ([0016](0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)). For the tool service, that machine is the orchestrator.

For NetBox it is not. A key made on the orchestrator has to be copied to the NetBox VM. The orchestrator has no write path to a target: the update key runs one command and takes no input ([0036](0036-target-packages-through-a-port-the-orchestrator-forwards.md)). So the key would travel through the operator's session, and a copy would stay on the orchestrator, which serves nothing with it.

Granian, the application server in NetBox's image, serves TLS itself. It reads its certificate and key paths from `GRANIAN_SSL_CERTIFICATE` and `GRANIAN_SSL_KEYFILE`, and takes a PKCS#8 key (Granian 2.8.2's command line, read on 2026-10-24). No reverse proxy is needed for it.

## Options

| Option | Where the key is | What it costs |
| --- | --- | --- |
| Made on the orchestrator, as 0035 says | On the orchestrator, and copied to the NetBox VM | Two copies of a key that one machine uses. A copy path to the target for a secret |
| Made on the NetBox VM | On the NetBox VM only | The certificate, which is public, comes back to the orchestrator to be pinned |
| A certificate authority on the orchestrator signs a key made on the VM | On the NetBox VM | An authority to keep for one service. A pin does the same job for one certificate |

## Decision

Made on the NetBox VM.

1. **The key.** NetBox's install script makes a P-256 key and a self-signed certificate on the NetBox VM: not an authority, 90 days, the names `netbox.aisec.internal` and `10.50.0.4`. The key goes into Podman's secret store and from there into the container, readable by the image's `netbox` account only.
2. **The pin.** The certificate is copied to `/etc/aisec/netbox/tls.crt` on the orchestrator, and to the consumer when it is built. Each trusts that certificate and nothing else.
3. **TLS** from Granian, set by its two variables.

## Trade-offs

- **The pin is what arrived.** The certificate comes to the orchestrator through the operator's session, as the update key's public half went the other way. A check compares the file on the NetBox VM with the pin, and the orchestrator's connection fails if the served certificate is another one.
- **Rotation is two steps.** A new certificate on the NetBox VM breaks every client until each has the new pin. The install script keeps a key that exists, and no rotation procedure is written yet.
- **The key sits in Podman's secret store**, a file readable by root only, on the VM's disk. A root compromise of the NetBox VM gets it, and that compromise holds NetBox's data already.
