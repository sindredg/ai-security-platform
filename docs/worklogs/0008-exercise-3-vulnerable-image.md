# 0008. Exercise 3: vulnerable image or dependency

Date: 2026-11-01
Milestone: 8, exercise 3: vulnerable image or dependency

## Summary

NetBox's image moved from v4.7.3 to v4.7.4, which clears 42 critical and high findings with a fixed version, among them a djangorestframework advisory that any client reaching NetBox could trigger without a token. The targets pipeline now scans the pinned image and keeps its SBOM. The update ran on the staging copy with its migration and a recovery, then on the live NetBox, and exercise 1 still matched. The model took no part: the scan and the pin decided.

| Criterion | Result |
| --- | --- |
| An applicability record for the specific artifact, backed by its SBOM | **Tested**: the pinned image's SBOM from the targets pipeline, its 42 critical and high findings with a fixed version, and a reachability reading for the two packages NetBox pins itself ([the record](#the-applicability-record)) |
| The update gets a staging test, with database migration and a tested recovery procedure | **Tested** on the copy: the migration `extras.0145` applied, then a restore of the dump and the old pin brought 4.7.3 back without it ([staging](#the-staging-test-on-the-copy)) |
| The specific finding is reassessed after delivery | **Tested** by reading the running NetBox: the default negotiation class, the fix's limits in its code, and the fixed versions ([after delivery](#the-finding-after-delivery)). Not reproduced before or after |
| Results from exercises 1 and 2 still hold | **Tested** for exercise 1: a job on the live seed matched, and every check passed ([exercise 1](#exercise-1-after-the-update)). Exercise 2: **accepted gap**, never run ([roadmap](../roadmap.md#status)) |
| The threat model is rechecked for the new change surface | **Tested** by reading: T63 new, T06 and the supply chain row moved ([threat model](#the-threat-model)) |

## The start pass

The open issues that fit the milestone: [#247](https://github.com/sindredg/ai-security-platform/issues/247), the image never scanned; [#188](https://github.com/sindredg/ai-security-platform/issues/188), the install script's refusal of another image, never tried; and [#187](https://github.com/sindredg/ai-security-platform/issues/187), an update run with NetBox running. [#191](https://github.com/sindredg/ai-security-platform/issues/191), the containers' stop signal, does not change with the image.

NetBox v4.7.4 is NetBox's newest release, and 5.1.1 is `netbox-docker`'s, both read from their release pages on 2026-11-01. Trivy 0.76.1, the targets pipeline's pin, is still Trivy's newest.

The `v4.7.3-5.1.1` tag now names another image index, `22cf3c61...`, than the pin, `1d6e0b5f...`: the image was built again upstream after the pin was taken. The registry still serves the pinned index, and the targets ran it unchanged, since the pin is by digest.

## The applicability record

The targets pipeline gained a job that scans the image `netbox/image.env` pins, by its index digest, for linux/amd64 ([targets #20](https://github.com/sindredg/ai-security-platform-test/pull/20)). Trivy pulls it from the registry, writes a software bill of materials (SBOM) in the CycloneDX format and a JSON report, and both are kept as the run's artifact. A script fails the job when the scanned image is not the pinned one, when the scan lists none of NetBox's own Python packages, and when a critical or high finding has a fixed version.

Written before the first run: the job fails on the old pin, with the pinned image ID and the Pillow and djangorestframework findings in its list. The script's own fail sides ran first on stub reports: another image, no NetBox packages, a fixed critical, and an empty report each exit 1, and a clean report exits 0.

| Pin | Image | Packages | Critical, fixed | High, fixed | Job |
| --- | --- | --- | --- | --- | --- |
| `v4.7.3-5.1.1` | `6942b6b0...`, the pinned ID | 798 | 6 | 36 | Failed, as written down |
| `v4.7.4-5.1.1` | `9f5bc18e...`, the pinned ID | 793 | 0 | 0 | Passed |

Both images are Ubuntu 26.04 with 139 system packages, NetBox's Python packages, and two binaries with their own dependencies, `pebble` in Go and `uv` in Rust. The SBOMs list the packages that matter:

| Package | v4.7.3-5.1.1 | v4.7.4-5.1.1 | Fixed in |
| --- | --- | --- | --- |
| Pillow | 12.3.0 | 13.0.0 | 13.0.0, five critical and 23 high |
| djangorestframework | 3.18.0 | 3.18.3 | 3.18.2, three high |
| certifi | 2026.7.22 | 2026.10.23 | 2026.10.18, one critical |
| `libbrotli1` | `1.2.0-3build1` | `1.2.0-3ubuntu0.1` | The second, one high |
| Django | 6.1.2 | 6.1.2 | No advisory covers 6.1.2 |

The others with a fix on the old pin: pyasn1 (four high), graphql-core (one high), and Go's standard library in `/usr/bin/pebble` (four high). Each is fixed in the new image.

Reachability was read for the two packages NetBox pins itself, from NetBox v4.7.3's and djangorestframework 3.18.0's source. It decided the order of the work, not whether to move: every finding with a fix is avoided by the move.

| Finding | Reachable in this deployment | Read from |
| --- | --- | --- |
| djangorestframework CVE-2026-114138, CPU spent on a crafted `Accept` header | Yes, without a token, by any client that reaches port 8443: the orchestrator and the lab subnet. Availability only | `rest_framework/views.py`: content negotiation runs before authentication |
| djangorestframework CVE-2026-114136, a JSON body decoded with a codec the client names | Only with a token that may write, and every such token is the orchestrator's | The parser runs in the handler, after authentication. Reasoned from the order, not traced per view |
| djangorestframework CVE-2026-114137, a token proxy that revokes nothing | No: NetBox does not install `rest_framework.authtoken` | NetBox's `settings.py` |
| Pillow, five critical and 23 high | Only through an image upload, which needs a token that may write | NetBox's image fields and thumbnails. Not traced per decoder |

The two that remain on the new pin have a fix and are medium: `social-auth-core` 5.2.0, an OpenID Connect nonce not bound to the session, and `rustls` 0.23.45 inside `uv`, with three low. `netbox-docker` 5.1.1's configuration keeps remote login off unless `REMOTE_AUTH_ENABLED` is set, and the targets' `netbox/netbox.env` does not set it. Neither unit nor the image's entrypoint runs `uv`. 50 medium and 4 low have no fix and were not judged one by one.

## The staging test on the copy

The update ran on the staging copy first, from a script with the [runbook](../runbooks/netbox-update.md)'s commands, steps 3 to 13. The new image came through a 30-minute just-in-time (JIT) egress window, into an archive beside the running image's. The expected results are the runbook's, written before the run.

Result, 2026-11-01 17:28 to 17:48 UTC, on the live staging copy:

| Step | Expected | Result |
| --- | --- | --- |
| The pull and the archive | The new index digest, 18 layers, config `9f5bc18e...` | As expected. Squid's log holds tunnels to `ghcr.io` and `pkg-containers.githubusercontent.com` only |
| The new pin with the old image ([#188](https://github.com/sindredg/ai-security-platform/issues/188)) | Refused, nothing started | `the archive does not hold image sha256:9f5bc18e.... Nothing is started.`, exit 1. Both containers kept their image and start time |
| The update | `ok    image`, every secret and the key kept, the login page | As expected. `Applying extras.0145_taggeditem_object_id_bigint... OK` |
| The state after it | 4.7.4, djangorestframework 3.18.3, Pillow 13.0.0, 0145 applied | As expected, and both checks' verdicts `within` for both accounts |
| Recovery: the dump from before, then the old pin | 4.7.3, the old packages, no 0145 | As expected, with the same verdicts. The old image was still in Podman's store |
| The update again, and a new seed dump | 0145 again. A reset prints the new dump's SHA-256 | As expected. The old dump is kept beside it |
| A staging test on v4.7.4 | The staging copy runbook's result | `"passed": false`, `inventory-reader` `missing` by both methods, the reset's SHA-256 before and after |

The copy's seed dump had to be taken again. Its reset restores the dump and starts NetBox, and the dump from before the update holds the schema without 0145. A reset after the update would have brought back the old schema under the new image.

NetBox logs `LOGIN_REQUIRED is deprecated and will be removed in NetBox v5.0` at each start, under both pins. `netbox-docker` 5.1.1's own configuration sets it, defaulting to `True`, so a move to NetBox v5.0 needs a look at how login stays required.

## The live update

After the staging test, [targets #20](https://github.com/sindredg/ai-security-platform-test/pull/20) merged as `35a3e0f`, and the live NetBox took the new pin from `main`, from a script with the runbook's steps 15 to 19.

Result, 2026-11-01 18:16 to 18:28 UTC, on the live system:

| Step | Expected | Result |
| --- | --- | --- |
| Before | 4.7.3, the old packages, `within` for both accounts by both checks | As expected. Both containers had run since 2026-10-25 |
| The archive on the NetBox VM | The SHA-256 of the orchestrator's | As expected, `2ccf28e4...` |
| The dump | Root 600, in a root 700 directory | As expected, 2.5 MB |
| The install | `ok    image`, every secret and the key kept, 0145 applied | As expected, with no unit restart after the start |
| The certificate and the ports | The pinned fingerprint, `200` on TLS, `000` in plain HTTP | As expected |
| After | 4.7.4, djangorestframework 3.18.3, Pillow 13.0.0, `within` for both accounts by both checks | As expected |
| The archives on the orchestrator | The new one as `netbox.tar`, the old one kept beside it | As expected |

## The finding after delivery

The specific finding was read again in the running NetBox, at 18:29 UTC. NetBox resolves `rest_framework.negotiation.DefaultContentNegotiation`, and the installed `negotiation.py` holds the fix's three limits: 8,192 characters for the `Accept` header, 64 media types, and 256 characters for one. The installed versions are djangorestframework 3.18.3 and Pillow 13.0.0, at or past each advisory's fixed version.

The scan of the image that runs, by its digest, lists no critical or high finding. That alone would not show the fix is in what NetBox runs, which is why the code was read in the container. The finding itself was not reproduced, before or after the update: its reachability is read from the source, and its absence from the code that runs.

## Exercise 1 after the update

Written before the run: the collection `within/within` for both accounts, then `Succeeded` with the comparison's `match`, and every check passing, `N.5` now on the new pin.

Result, 2026-11-01 18:28 to 18:52 UTC, on the live system ([record](../evidence/2026-11-01-1828-after-the-netbox-update.md)): as expected. `nb-11011828-close` matched both accounts in 710 seconds, with three calls and the structured output, the slot erased before and after. Every check from `69aa526`, with the targets at `35a3e0f`, passed, 446 of 446, `N.12` among them: NetBox v4.7.4 still takes a token's client address from the connection only ([ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)).

## The threat model

The change surface is an update of the target's image. T06, a malicious artifact, already covered the pull and the archive, and its checks ran again for the new pin. Nothing covered a known vulnerability in that image going unnoticed, so it is new, as T63, rated High: a reachable flaw in the target can change it without approval.

| Page | Change |
| --- | --- |
| [Threat model](../security/threat-model.md) | T63, Verified by the scan's two runs and the update. Its residual: no scheduled scan |
| [Supply chain](../security/supply-chain.md) | The NetBox row names the scan, the refusal of another image, and the new pin |
| [Lab against production](../security/lab-vs-production.md) | Pins updated by hand: the scan runs on a change, not on a schedule |

The dump on the NetBox VM holds what the database holds, the token and password hashes among them. It sits on the same VM, readable by root only, like the database itself, so it adds no credential to the [inventory](../security/credentials.md).

## Not verified

- The recovery on the live NetBox. It ran on the copy, with the same commands ([runbook](../runbooks/netbox-update.md), step 21).
- The finding itself, before or after the update. Its reachability is read from the source.
- 50 medium and 4 low findings without a fix, listed and not judged one by one.
- An update run with NetBox running ([#187](https://github.com/sindredg/ai-security-platform/issues/187)): not run. The NetBox VM's package lists, from its last update run on 2026-10-26, hold no pending upgrade, so a run would first read newer ones.
