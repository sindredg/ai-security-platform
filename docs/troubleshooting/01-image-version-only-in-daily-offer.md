# 01. The pinned image version exists only in the daily offer

Date: 2026-10-11
Milestone: 2, platform compute

## Symptom

The platform apply created the network pieces and then failed on both VMs.

```text
Error: creating Linux Virtual Machine ... performing CreateOrUpdate: unexpected status 404 (404 Not Found)
with error: PlatformImageNotFound: The platform image 'Canonical:ubuntu-26_04-lts:server:26.04.202610100'
is not available.
```

The worker failed the same way for `server-arm64`. The plan had passed. Terraform does not check that an image version exists until Azure is asked to build from it.

## Cause

Confirmed. Version `26.04.202610100` is published in `ubuntu-26_04-lts-daily`, not in `ubuntu-26_04-lts`.

The lookup that produced the pin was wrong. `az vm image list --offer` and `--sku` match by substring, so a query for offer `ubuntu-26_04-lts` and SKU `server` also returns the daily offer and SKUs such as `server-gen1`. The newest version in that mixed list came from the daily offer.

```bash
az vm image list -l swedencentral -p Canonical -f ubuntu-26_04-lts --all \
  --query "[?version=='26.04.202610100'].urn" -o tsv
```

```text
Canonical:ubuntu-26_04-lts:pro-minimal:26.04.202610100
Canonical:ubuntu-26_04-lts:pro-minimal-arm64:26.04.202610100
Canonical:ubuntu-26_04-lts:pro-minimal-gen1:26.04.202610100
Canonical:ubuntu-26_04-lts-daily:server:26.04.202610100
Canonical:ubuntu-26_04-lts-daily:server-arm64:26.04.202610100
Canonical:ubuntu-26_04-lts-daily:server-gen1:26.04.202610100
```

## Fix

Filter on the exact offer and SKU, then take the newest version.

```bash
for sku in server server-arm64; do
  az vm image list -l swedencentral -p Canonical -f ubuntu-26_04-lts -s "$sku" --all \
    --query "[?offer=='ubuntu-26_04-lts' && sku=='$sku'].version | sort(@) | [-1]" -o tsv
done
```

Both returned `26.04.202610070`. That is now the default of `image_version` in `infra/platform/variables.tf`.

## Verification

The next plan showed only the two VMs, with version `26.04.202610070`. The apply reported `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.` A plan after that exited `0`.

## What it changes

The [platform compute runbook](../runbooks/platform-compute.md) checks the pin with the exact-match query before any apply. A failed VM apply leaves the NAT gateway, its address, and the network interfaces in place. They are in state, and the next apply picks up where the first stopped.
