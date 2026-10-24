# 16. The targets' apt sources fall back to hosts the target port refuses

Date: 2026-10-24
Milestone: 4, NetBox target and exercise 1 investigation

## Symptom

`VN.20` and `VL.20`, run for the first time at 17:30 UTC, failed on both targets. Their apt sources named `http://archive.ubuntu.com/ubuntu` and `http://security.ubuntu.com/ubuntu`. Squid's target port serves `azure.archive.ubuntu.com` and refuses every other host (`P.24`), so the first update run would have ended in `403` for every package list. The orchestrator, built from a template with no mirror in it either, names `azure.archive.ubuntu.com`.

## Cause

Confirmed from each VM's `/var/log/cloud-init.log`. With no mirror in its configuration, cloud-init on Azure searches a list of candidates, `http://azure.archive.ubuntu.com/ubuntu/`, and keeps the first whose name resolves. The targets have no DNS ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)), so the search failed twice, 20 seconds each, and cloud-init fell back to the distribution's defaults:

```text
search for mirror in candidates: '['http://azure.archive.ubuntu.com/ubuntu/']'
filtered distro mirror info: {'primary': 'http://archive.ubuntu.com/ubuntu', 'security': 'http://security.ubuntu.com/ubuntu'}
```

The orchestrator's log from its first boot on 2026-10-13 has `found working mirror: 'http://azure.archive.ubuntu.com/ubuntu/'` instead. It could resolve names then.

## Fix

The target template names the mirror for both the primary and the security archive under `apt:`, so cloud-init does not search. Both targets were rebuilt from it, the apply ending about 17:45 UTC.

## Verification

After the rebuild, each VM's cloud-init log reads `Apt Mirror info: {'PRIMARY': 'http://azure.archive.ubuntu.com/ubuntu/', 'SECURITY': 'http://azure.archive.ubuntu.com/ubuntu/', ...}` with no search, and `VN.20` and `VL.20` pass. The first update runs read every list and package through the target port, with no refusal in Squid's log ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-update-run)).
