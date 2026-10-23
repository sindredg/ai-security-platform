# 0033. K3s's system images come from the release's archive, not from Docker Hub by tag

Status: Accepted
Date: 2026-10-23

## Context

Milestone 3's criterion is that every image is pinned by digest and checked on the orchestrator before it runs ([roadmap](../roadmap.md#3-toolchain-integration)). K3s's four system images are not. First boot checks the K3s binary and its install script against pinned checksums. The binary names its system images by tag: `local-path-provisioner`, CoreDNS, `metrics-server`, and `pause`, under `docker.io/rancher/`. containerd pulls them from Docker Hub during the fetch window of first boot, and whatever the tag names that day runs ([supply chain](../security/supply-chain.md)).

On 2026-10-23 the four running images matched the release's airgap image archive by digest ([worklog](../worklogs/0003-toolchain-integration.md#k3ss-system-images)). That shows what ran that day. It holds nothing for the next rebuild.

Docker Hub is also on the edge's list of hosts for a fetch window ([0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md)), for these four images only. It accepts uploads from anyone with an account, so it is one more host a compromised orchestrator can send data to while a window is open (T40).

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| Keep pulling by tag | Nothing to change | A tag that moves upstream reaches the next rebuild unseen. Docker Hub stays on the list |
| Pin each image by digest in K3s's packaged manifests | The digests in the repository | K3s writes its packaged manifests again at each start. Overriding them means disabling each component and running a copy, and the pause image is in containerd's settings, not in a manifest |
| A registry mirror on the platform | One place for every image | Another service to run, patch, and fill, for four images |
| The release's airgap image archive, pinned by checksum | Every system image in one file, checked before K3s starts. K3s imports an archive from `agent/images` when it starts, and the packaged manifests pull only an image that is not there | About 196 MB more per rebuild and per K3s upgrade. The archive holds four images this cluster does not run |

## Decision

The archive.

1. **The pin.** `k3s_images_sha256` in `infra/platform/variables.tf` is the release's checksum of `k3s-airgap-images-amd64.tar`, from its `sha256sum-amd64.txt`. `infra/platform/k3s-images.txt` lists each image in the archive with the digest of its image index, read from the archive's `index.json`.
2. **First boot.** It downloads the archive beside the binary, checks it against the pin, and puts it in `/var/lib/rancher/k3s/agent/images/` before K3s starts.
3. **The host list.** Docker Hub's three hosts leave `edge/fetch-hosts`. A system image that is not in the archive then fails to pull, inside a window or not.
4. **The check.** `K.11` reads every `docker.io/rancher/` tag containerd holds and every image a `kube-system` pod runs, and requires each in the list with the digest containerd has for it.

## Trade-offs

- **A K3s upgrade moves three pins and the list together.** The binary, the install script, and the archive each have a checksum, and the list comes out of the archive. Forgetting the list fails `K.11` after the upgrade. Forgetting the archive's checksum stops first boot.
- **The archive is trusted as the release ships it.** K3s publishes no signature or provenance for it, as for the binary. The checksum proves it is the file the release lists.
- **Disk.** The archive stays in `agent/images`, about 196 MB on the orchestrator's disk.
- **The running orchestrator gets the archive by hand.** Its first boot is past, so the change reaches it through the operator, as in the [platform compute runbook](../runbooks/platform-compute.md).
