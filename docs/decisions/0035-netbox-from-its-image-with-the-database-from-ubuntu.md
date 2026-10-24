# 0035. NetBox from its image under Podman, with PostgreSQL and Valkey from Ubuntu

Status: Proposed
Date: 2026-10-24

## Context

Milestone 4 deploys NetBox on the target VM in Poland Central ([ADR 0004](0004-netbox-as-first-target.md), [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation)). Its criterion: every image on the target side is pinned by digest, and signatures are verified where upstream signs.

NetBox needs PostgreSQL 15 or later and Redis 6 or later ([installation](https://github.com/netbox-community/netbox/blob/v4.7.3/docs/installation/index.md)). Read on 2026-10-24:

| Part | Where it comes from |
| --- | --- |
| NetBox | Its release archive, or the `netbox-docker` image on `ghcr.io`, `quay.io`, and Docker Hub, for amd64 and arm64. The image is not signed: `ghcr.io` has no cosign signature or attestation for the current digest, and the release workflow has no signing or attestation step |
| PostgreSQL 18 and Valkey 9 | Ubuntu 26.04 `main`, with security updates. Upstream's compose file uses `postgres` and `valkey` images from Docker Hub |
| Podman and Docker | Ubuntu 26.04 `universe` |

Two constraints shape the choice. The targets have no way out ([architecture](../architecture.md#egress)), so the orchestrator brings everything they run. And Docker Hub left the edge's fetch list on 2026-10-23 ([0033](0033-k3s-system-images-from-the-release-archive.md)); `ghcr.io` and `quay.io` are on it.

Exercise 3 needs a pinned artifact that a real advisory affects ([ADR 0004](0004-netbox-as-first-target.md)). An image pinned by digest gives it one to work on.

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| Upstream's compose file: the NetBox, PostgreSQL, and Valkey images | Closest to upstream, three images pinned by digest | Docker Hub goes back on the fetch list for two images. The database images move only when someone moves the pin, and nothing patches them in between |
| The NetBox image, with PostgreSQL and Valkey from Ubuntu `main` | One image to pin, from a host already on the list. The archive patches the two services that hold the data | A container runtime from `universe`. The image's configuration has to point at services on the host instead of beside it |
| NetBox from its release archive, in a virtual environment with hashed requirements | No container runtime | The setup upstream's image already does, written again for this project. Exercise 3 becomes a dependency update instead of an image update |

## Decision

The NetBox image, with PostgreSQL and Valkey from Ubuntu.

1. **NetBox.** The `netbox-docker` image from `ghcr.io`, pinned by the digest of its image index. The first pin is NetBox v4.7.3 in `netbox-docker` 5.1.1, the newest on 2026-10-24. The digest and every later move go on the [version table](../components/README.md#versions), not here. The same image runs the background worker with `rqworker`, as upstream's compose file does.
2. **The runtime.** Podman, run by systemd units on the target.
3. **PostgreSQL and Valkey** from Ubuntu `main`, listening on the target's loopback only, each with a password generated on the target at provisioning.
4. **The pin is checked twice.** The orchestrator pulls the image during a fetch window and checks the digest. The target checks the image it loaded against the pin before it starts it.
5. **TLS** on the NetBox port, with a certificate made on the orchestrator, which the collector and the consumer pin, as for the tool service ([0016](0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)).
6. **Data.** Synthetic only, seeded by the orchestrator through the API.

How the target gets these packages is [0036](0036-target-packages-through-a-port-the-orchestrator-forwards.md).

Two parts of this are not yet seen to work, and the first deployment settles them:

- **The check on the target.** `podman load` does not keep the registry's manifest digest, so the target cannot compare the loaded image with the pin as it stands. It has to compare the image ID, recorded on the orchestrator at the pull, or load in a form that keeps the digest. Which one works is found on the target and recorded with the evidence.
- **TLS in the image.** The image's launch script passes `GRANIAN_EXTRA_ARGS` to Granian, its application server, which suggests Granian can serve HTTPS itself. Not tried. If it cannot, a reverse proxy from Ubuntu `main` terminates TLS on the target, in a new record.

## Trade-offs

- **The image is not signed.** The digest proves it is the image first chosen, not who built it. Upstream publishes no signature or provenance, so there is none to verify. The state goes on the [supply chain](../security/supply-chain.md) page.
- **Podman is in `universe`.** Canonical does not promise security updates for it without Ubuntu Pro, which these VMs do not use. It runs one image the operator chose, and it is not reachable from the network.
- **Not upstream's layout.** The compose file is the tested setup. Pointing the image at services on the host is configuration this project owns, and an upgrade of `netbox-docker` can change the variables it reads.
- **Two update paths.** The image moves when the pin moves. PostgreSQL and Valkey move with the archive, on the schedule [0036](0036-target-packages-through-a-port-the-orchestrator-forwards.md) sets. A database upgrade between major releases stays a procedure, which exercise 3 rehearses.
