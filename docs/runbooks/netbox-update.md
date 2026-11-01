# NetBox image update: operator procedure

Status: Ran on 2026-11-01, NetBox v4.7.3 to v4.7.4, on the live system ([worklog](../worklogs/0008-exercise-3-vulnerable-image.md)). Steps 1 and 2 by hand and in [targets #20](https://github.com/sindredg/ai-security-platform-test/pull/20). Steps 3 to 13 on the copy, 17:28 to 17:48 UTC, and steps 15 to 18 and 20 on the live NetBox, 18:16 to 18:28 UTC, each from a script with the same commands. Step 19 at 18:29 UTC, and step 21 from 18:28 to 18:52 UTC. The scripts named the directories `~/m8-new` and `~/m8-old`, and the lab VM's archive and the dumps after the version: `~/netbox-v4.7.4.tar`, `before-v4.7.4.dump`, and `seed-v4.7.3.dump`. Step 14 ran with every check: 445 passed, and `N.5` failed as expected. Steps 22 and 23 have not run.

This moves NetBox's image pin in the [targets repository](https://github.com/sindredg/ai-security-platform-test)'s `netbox/image.env` to a new release. The targets pipeline scans the new image and keeps its SBOM. The update then runs on the staging copy first, with its database migration and a recovery from a dump, and then on the live NetBox, after a dump of its own ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md), [ADR 0044](../decisions/0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md)).

NetBox and the copy must run already: the [NetBox runbook](netbox.md) and the [staging copy runbook](rehearsal-copy.md).

## Inputs and access

| Input | Notes |
| --- | --- |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-edge`, `aisec-netbox`, and `aisec-lab` |
| A checkout of this repository | Run from its root |
| `REPLACE_WITH_OLD` | A checkout of the targets repository at the pin NetBox runs |
| `REPLACE_WITH_NEW` | A worktree of the targets repository on the branch that moves the pin |
| `REPLACE_WITH_TAG` | The new tag, as `v4.7.4-5.1.1`: NetBox's newest release, then `netbox-docker`'s |
| `REPLACE_WITH_NEW_ID`, `REPLACE_WITH_OLD_ID` | The two pins' `NETBOX_IMAGE_ID`, without `sha256:` |
| `REPLACE_WITH_AMD64_MANIFEST` | The index's `amd64`/`linux` manifest digest, from step 1 |
| `REPLACE_WITH_OLD_TAG`, `REPLACE_WITH_OLD_PIN_CHECKOUT` | The running pin's tag, and a checkout of the targets repository at that pin, for a recovery |
| No workflow running | A job reads NetBox, which restarts in steps 10, 13, 15, and 21 |

## The pin and the scan

1. Read the tag's image index, its linux/amd64 manifest, and that manifest's config from the registry.

   ```bash
   R=netbox-community/netbox
   TOKEN=$(curl -fsS "https://ghcr.io/token?scope=repository:$R:pull" | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["token"])')
   ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json'
   curl -fsS -D - -o index.json -H "Authorization: Bearer $TOKEN" -H "Accept: $ACCEPT" "https://ghcr.io/v2/$R/manifests/REPLACE_WITH_TAG" | grep -i docker-content-digest
   sha256sum index.json
   python3 -I -c 'import json; [print(m["digest"], m.get("platform")) for m in json.load(open("index.json"))["manifests"]]'
   curl -fsS -o manifest.json -H "Authorization: Bearer $TOKEN" -H "Accept: $ACCEPT" "https://ghcr.io/v2/$R/manifests/REPLACE_WITH_AMD64_MANIFEST"
   sha256sum manifest.json
   python3 -I -c 'import json; print(json.load(open("manifest.json"))["config"]["digest"])'
   ```

   Expected: the header's digest equals the body's SHA-256, one manifest for `amd64`/`linux`, the manifest's SHA-256 equal to its digest, and a config digest. The other entries are attestation manifests.

2. Change the four lines of `netbox/image.env` to the tag and the three digests in a branch of the targets repository, and open a pull request.

   Expected: "NetBox image scan" passes, with the new `NETBOX_IMAGE_ID` and no critical or high finding with a fixed version. The run's artifact `netbox-image` holds the SBOM and the report. Do not merge yet.

## The image

3. Copy the fetch script and the new pin to the orchestrator.

   ```bash
   tar -cf - platform/target-images | REPLACE_WITH_SSH aisec-orchestrator \
     'rm -rf ~/feed/target-images-new && mkdir -p ~/feed/target-images-new && tar -C ~/feed/target-images-new -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'cat > ~/feed/target-images-new/image.env' < REPLACE_WITH_NEW/netbox/image.env
   REPLACE_WITH_SSH aisec-orchestrator 'sha256sum ~/feed/target-images-new/image.env'
   sha256sum REPLACE_WITH_NEW/netbox/image.env
   ```

   Expected: the same SHA-256 twice.

4. Open a JIT egress window, pull, export, and check the image into an archive beside the old one, then close the window.

   ```bash
   since=$(date +%s)
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 30'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/target-images-new/platform/target-images/fetch-netbox-image.sh \
     ~/feed/target-images-new/image.env /var/lib/aisec/target-images/netbox-REPLACE_WITH_TAG.tar'
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `open for 30 minutes`, `ok    pulled` with the new index digest, `ok    archive: 18 layers, config sha256:REPLACE_WITH_NEW_ID`, then `closed`. `netbox.tar`, the running image's archive, stays.

5. Read the window's tunnels in Squid's log.

   ```bash
   REPLACE_WITH_SSH aisec-edge "sudo awk -v since=$since '\$1 >= since && \$3 == \"10.40.0.4\" {print \$4, \$6, \$7}' /var/log/squid/access.log | sort | uniq -c"
   ```

   Expected: `TCP_TUNNEL/200 CONNECT` to `ghcr.io:443` and `pkg-containers.githubusercontent.com:443` only.

## The staging test on the copy

6. Reset the copy to its seed, then read its state: NetBox's version, three package versions, the containers' image and start time, and the last two migrations of `extras`.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ssh -F none -i /etc/aisec/netbox-rehearsal/reset/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
     -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/aisec/netbox/observe/known_hosts -T aisec-rehearse@10.50.0.36' </dev/null
   REPLACE_WITH_SSH aisec-lab 'sudo bash -s' <<'EOF'
   podman exec netbox grep -m1 "^version" /opt/netbox/netbox/release.yaml
   podman exec netbox /opt/netbox/venv/bin/python -I -c 'import importlib.metadata as m; print(*(p + "=" + m.version(p) for p in ("djangorestframework", "pillow", "django")))'
   podman inspect --format "{{.Name}} {{.Image}} {{.State.StartedAt}}" netbox netbox-worker
   runuser -u postgres -- psql -d netbox -Atc "select name from django_migrations where app = 'extras' order by id desc limit 2"
   EOF
   REPLACE_WITH_SSH aisec-orchestrator 'sudo env AISEC_NETBOX_URL=https://10.50.1.4:8443 AISEC_NETBOX_CERT=/etc/aisec/netbox-rehearsal/tls.crt AISEC_NETBOX_TOKENS=/etc/aisec/netbox-rehearsal/tokens \
     python3 -I /usr/local/lib/aisec/netbox_access.py configured --summary < /etc/aisec/netbox/contract.json'
   ```

   Expected: the reset's last line is the SHA-256 the orchestrator recorded. Then the old version and packages, both containers on `REPLACE_WITH_OLD_ID`, and the seed's verdicts. Call the last two commands "the state read" below. On the live NetBox it reads `aisec-netbox`, and the verdicts without the three `AISEC_NETBOX_` settings.

7. Copy both pins' NetBox directories and the new archive to the lab VM.

   ```bash
   tar -C REPLACE_WITH_NEW -cf - netbox | REPLACE_WITH_SSH aisec-lab 'rm -rf ~/netbox-new && mkdir ~/netbox-new && tar -C ~/netbox-new -xf -'
   tar -C REPLACE_WITH_OLD -cf - netbox | REPLACE_WITH_SSH aisec-lab 'rm -rf ~/netbox-old && mkdir ~/netbox-old && tar -C ~/netbox-old -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/aisec/target-images/netbox-REPLACE_WITH_TAG.tar' | REPLACE_WITH_SSH aisec-lab 'cat > ~/netbox-new.tar'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo sha256sum /var/lib/aisec/target-images/netbox-REPLACE_WITH_TAG.tar'
   REPLACE_WITH_SSH aisec-lab 'sha256sum ~/netbox-new.tar'
   ```

   Expected: the same SHA-256 on both. The copy takes several minutes.

8. Give the install script the new pin and an archive of the old image. It has to refuse.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'sudo podman save --quiet -o /root/netbox-old.tar REPLACE_WITH_OLD_ID'
   REPLACE_WITH_SSH aisec-lab 'sudo env AISEC_NETBOX_ADDRESS=10.50.1.4 AISEC_NETBOX_LISTEN=10.50.1.4 AISEC_NETBOX_CONF=/etc/aisec/netbox-rehearsal \
     ~/netbox-new/netbox/install-netbox.sh /root/netbox-old.tar'; echo "exit $?"
   ```

   Expected: an error that the loaded image is not the pin, and exit 1. The state read shows the same images and start times as step 6.

9. Dump the copy's database before the update.

   ```bash
   REPLACE_WITH_SSH aisec-lab "sudo sh -c 'umask 077; runuser -u postgres -- pg_dump -Fc netbox > /var/lib/aisec/rehearsal/before-update.dump' && sudo sha256sum /var/lib/aisec/rehearsal/before-update.dump"
   ```

   Expected: a SHA-256. The dump is root 600.

10. Update the copy: the install with the new pin and the new archive.

    ```bash
    REPLACE_WITH_SSH aisec-lab 'sudo env AISEC_NETBOX_ADDRESS=10.50.1.4 AISEC_NETBOX_LISTEN=10.50.1.4 AISEC_NETBOX_CONF=/etc/aisec/netbox-rehearsal \
      ~/netbox-new/netbox/install-netbox.sh ~/netbox-new.tar'
    ```

    Expected: `ok    image` with `REPLACE_WITH_NEW_ID`, `have` for each secret and the key, `units started`, then `login_page=200`. The state read shows the new version and packages, both containers on the new ID, and the release's new migrations applied.

11. Recover: stop both units, restore the dump from step 9, flush Valkey, and install the old pin, whose image the copy still holds.

    ```bash
    REPLACE_WITH_SSH aisec-lab 'sudo bash -s' <<'EOF'
    set -euo pipefail
    systemctl stop netbox-worker.service netbox.service
    runuser -u postgres -- dropdb --if-exists --force netbox
    runuser -u postgres -- createdb -O netbox netbox
    runuser -u postgres -- pg_restore --exit-on-error --single-transaction --no-owner --role=netbox -d netbox < /var/lib/aisec/rehearsal/before-update.dump
    VALKEYCLI_AUTH=$(podman secret inspect --showsecret --format '{{.SecretData}}' netbox_valkey_password) valkey-cli FLUSHALL > /dev/null
    echo restored
    EOF
    REPLACE_WITH_SSH aisec-lab 'sudo env AISEC_NETBOX_ADDRESS=10.50.1.4 AISEC_NETBOX_LISTEN=10.50.1.4 AISEC_NETBOX_CONF=/etc/aisec/netbox-rehearsal \
      ~/netbox-old/netbox/install-netbox.sh /root/netbox-old.tar'
    ```

    Expected: `restored`, then `have  image` with `REPLACE_WITH_OLD_ID` and `login_page=200`. The state read shows the old version and packages, and none of the new migrations.

12. Update the copy again, as in step 10. Then take its seed dump again, keep the old one, and record the new SHA-256 on the orchestrator.

    ```bash
    REPLACE_WITH_SSH aisec-lab "sudo sh -c 'umask 077; cp -p /var/lib/aisec/rehearsal/seed.dump /var/lib/aisec/rehearsal/seed-before-update.dump; runuser -u postgres -- pg_dump -Fc netbox > /var/lib/aisec/rehearsal/seed.dump'"
    SHA=$(REPLACE_WITH_SSH aisec-lab 'sudo sha256sum /var/lib/aisec/rehearsal/seed.dump' | cut -d " " -f 1)
    echo "$SHA" | REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'umask 022; cat > /etc/aisec/netbox-rehearsal/reset/seed.sha256'"
    ```

    Expected: no output. A reset would otherwise bring back the old schema under the new image.

13. Reset the copy through its account as in step 6, then run a staging test once, as in step 21 of the [staging copy runbook](rehearsal-copy.md).

    Expected: the reset prints the new SHA-256. The staging test prints that runbook's expected result.

14. Run every check with the new worktree as the targets checkout.

    ```bash
    AISEC_TARGETS=REPLACE_WITH_NEW validation/platform-checks.sh
    ```

    Expected: `Q.2` and `Q.5` pass. `N.5` fails until step 17, since the live NetBox still runs the old image.

## The live NetBox

15. Merge the pull request, and update the old checkout to `main`. Then copy its NetBox directory and the new archive to the NetBox VM.

    ```bash
    tar -C REPLACE_WITH_OLD -cf - netbox | REPLACE_WITH_SSH aisec-netbox 'rm -rf ~/netbox-install && mkdir ~/netbox-install && tar -C ~/netbox-install -xf -'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/aisec/target-images/netbox-REPLACE_WITH_TAG.tar' | REPLACE_WITH_SSH aisec-netbox 'cat > ~/netbox.tar'
    REPLACE_WITH_SSH aisec-netbox 'sha256sum ~/netbox.tar'
    ```

    Expected: the archive's SHA-256 from step 7.

16. Dump the live database.

    ```bash
    REPLACE_WITH_SSH aisec-netbox "sudo install -d -m 700 /var/lib/aisec/netbox-dumps && sudo sh -c 'umask 077; runuser -u postgres -- pg_dump -Fc netbox > /var/lib/aisec/netbox-dumps/before-update.dump' && sudo sha256sum /var/lib/aisec/netbox-dumps/before-update.dump"
    ```

    Expected: a SHA-256.

17. Install the new pin.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-install/netbox/install-netbox.sh ~/netbox.tar'
    ```

    Expected: as step 10, on the live NetBox. The state read on `aisec-netbox` shows the new version, packages, image, and migrations.

18. Check the certificate the orchestrator pins and both ports, as in steps 9 and 10 of the [NetBox runbook](netbox.md).

    Expected: the same fingerprint as before, `200`, then `000`.

19. Read the specific finding in the running code: the fixed versions, and the code the advisory's fix changed. For djangorestframework's CVE-2026-114138, the negotiation class NetBox resolves and the limits the fix added:

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'sudo bash -s' <<'EOF'
    podman exec netbox sh -c 'grep -n "max_accept_header_length\|max_accept_tokens\|max_media_type_length" /opt/netbox/venv/lib/python3*/site-packages/rest_framework/negotiation.py'
    podman exec -w /opt/netbox/netbox netbox /opt/netbox/venv/bin/python -c 'import os, django; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings"); django.setup(); from rest_framework.settings import api_settings; import rest_framework, PIL; print(api_settings.DEFAULT_CONTENT_NEGOTIATION_CLASS, rest_framework.VERSION, PIL.__version__)'
    EOF
    ```

    Expected: the three limits at the top of `DefaultContentNegotiation`, then `<class 'rest_framework.negotiation.DefaultContentNegotiation'> 3.18.3 13.0.0` after NetBox's configuration lines.

20. Remove the archive's copy from the NetBox VM, and make the new archive the one a rebuild uses.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'rm -f ~/netbox.tar'
    REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'cd /var/lib/aisec/target-images && mv netbox.tar netbox-REPLACE_WITH_OLD_TAG.tar && mv netbox-REPLACE_WITH_TAG.tar netbox.tar && sha256sum netbox.tar netbox-REPLACE_WITH_OLD_TAG.tar'"
    ```

    Expected: `netbox.tar` with the new archive's SHA-256.

21. Run one exercise 1 job and every check, and record the job ([test evidence runbook](test-evidence.md)).

    Expected: the job's comparison matches the deterministic checks, and every check passes.

## Recovery of the live NetBox

22. Not run on the live NetBox: step 11 ran the same on the copy. Copy the old pin's NetBox directory and the old archive, which only the orchestrator keeps, to the NetBox VM. Then stop both units, restore the dump from step 16, flush Valkey, and install the old pin.

    ```bash
    tar -C REPLACE_WITH_OLD_PIN_CHECKOUT -cf - netbox | REPLACE_WITH_SSH aisec-netbox 'rm -rf ~/netbox-old && mkdir ~/netbox-old && tar -C ~/netbox-old -xf -'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/aisec/target-images/netbox-REPLACE_WITH_OLD_TAG.tar' | REPLACE_WITH_SSH aisec-netbox 'cat > ~/netbox-old.tar'
    REPLACE_WITH_SSH aisec-netbox 'sudo bash -s' <<'EOF'
    set -euo pipefail
    systemctl stop netbox-worker.service netbox.service
    runuser -u postgres -- dropdb --if-exists --force netbox
    runuser -u postgres -- createdb -O netbox netbox
    runuser -u postgres -- pg_restore --exit-on-error --single-transaction --no-owner --role=netbox -d netbox < /var/lib/aisec/netbox-dumps/before-update.dump
    VALKEYCLI_AUTH=$(podman secret inspect --showsecret --format '{{.SecretData}}' netbox_valkey_password) valkey-cli FLUSHALL > /dev/null
    echo restored
    EOF
    REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-old/netbox/install-netbox.sh ~/netbox-old.tar'
    ```

    Expected: `restored`, then `have  image` with `REPLACE_WITH_OLD_ID` and `login_page=200`. The state read on `aisec-netbox` shows the old version, packages, and image, and none of the new migrations. Then revert the pin in the targets repository, and rename the archives back.

## Cleanup

23. Remove the working copies: `~/netbox-new`, `~/netbox-old`, and `~/netbox-new.tar` on the lab VM, and `~/feed/target-images-new` on the orchestrator.

    Expected: no output. Not run on 2026-11-01: the teardown removes both VMs.
