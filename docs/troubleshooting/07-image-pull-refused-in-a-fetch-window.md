# 07. An image pull fails inside a fetch window: Squid refuses the layer host

Date: 2026-10-17
Milestone: 3a, edge network and monitoring

## Symptom

With a fetch window open on the edge, a pull of an image that was not on the orchestrator failed ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fetch-window)):

```text
$ sudo k3s crictl pull docker.io/rancher/mirrored-pause:3.10
level=fatal msg="pulling image: failed to pull and unpack image \"docker.io/rancher/mirrored-pause:3.10\":
failed to copy: httpReadSeeker: failed open: failed to do request:
Get \"https://production.cloudfront.docker.com/registry-v2/docker/registry/v2/blobs/sha256/87/873e.../data?...\": Forbidden"
```

A pull of an image already on the node, in the same window, had worked.

## Cause

Confirmed from Squid's log on the edge. The manifest came from `registry-1.docker.io`, which was on the list. The layer is a redirect to `production.cloudfront.docker.com`, which was not:

```text
TCP_TUNNEL/200 CONNECT registry-1.docker.io:443
TCP_DENIED/403 CONNECT production.cloudfront.docker.com:443
```

The list named `production.cloudflare.docker.com`, the layer host written down for Docker Hub before the build. A pull of an image already on the node asks for the manifest only, so the first window never reached the layer host and could not show the wrong name.

## Fix

`edge/fetch-hosts` names `production.cloudfront.docker.com` in place of the old name, and the list was installed on the edge ([edge runbook](../runbooks/edge-vm.md#change-the-command-or-the-list)).

The lesson for the list: test a window with a pull that downloads layers, not one the node can answer from its cache. A host name that a vendor documents is a candidate until the proxy log shows it.

## Verification

In the next window, the same pull downloaded the image. Squid logged `TCP_TUNNEL/200 CONNECT production.cloudfront.docker.com:443` and refused nothing. A pull of a tool service image that was not on the node logged `pkg-containers.githubusercontent.com` the same way. `P.18` passes with the new list on the edge.
