# Tool service: operator procedure

Status: Implemented on 2026-10-15. Deployed once, on an orchestrator built before the node port setting and the pod egress rule were in its first-boot template. Every step below was run during that deployment, except that steps 5 and 6 were applied by hand there instead of read back. A deployment on an orchestrator built from the current template, and a certificate rotation, have not been run. Results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#the-deployment-on-the-orchestrator). Steps 2 and 4 ran again on 2026-10-22 for a new image, with the pull in a just-in-time (JIT) egress window that step 4 has named since then ([worklog](../worklogs/0003-toolchain-integration.md#installed-the-images-on-the-fixed-base)).

Run these steps to put the tool service in K3s on the orchestrator and prove one round trip from the worker: open the port, make the certificate, deploy, give the worker the certificate and the name, run the checks, then register a job, call a tool with its token, and revoke it. The evidence is synthetic.

## Inputs and access

| Input | Notes |
| --- | --- |
| Milestone 2, built | The [platform compute runbook](platform-compute.md). Both VMs up, K3s healthy, the feed key in place |
| The platform identity | For step 1. `CRED_DIR` holds `platform.env`, as in the platform compute runbook |
| Terraform at the pinned version, first on `PATH` | Step 1 of the platform compute runbook |
| SSH to both VMs over the mesh VPN | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| A checkout of this repository on the workstation, at a commit on `main` | The manifests and scripts are in `platform/tool-service/`, the policy in `policies/tool-service.json` |
| The image the manifest names, published | The pipeline pushes it from `main`. The package is public, so the cluster needs no registry credential |

The design is in ADRs [0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md), [0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md), [0017](../decisions/0017-no-udp-from-the-orchestrator.md), and [0018](../decisions/0018-a-host-rule-keeps-pods-off-the-internet.md). The controls are on the [tool service page](../security/tool-service.md#deployment-controls).

The dispatch step registers and revokes each workflow's job since 2026-10-21 ([workflows runbook](workflows.md)). The round trip below uses `register.sh` instead, so the service can be tested without Argo: it starts one short-lived pod in `orchestration`, as the dispatch account, that registers or revokes one job.

## Open the port

1. Apply the platform root. Run in `infra/platform` as the platform identity. Read the plan before applying it.

   ```bash
   source "$CRED_DIR/platform.env"
   terraform plan -out=platform.tfplan
   terraform apply platform.tfplan
   rm -f platform.tfplan
   ```

   Expected on a platform built before 2026-10-14: 0 to add, 2 to change, 0 to destroy. The orchestrator's security group loses `allow-mesh-stun` and `allow-mesh-direct` and gains `allow-tool-service-from-worker`. The worker's gains `allow-tool-service-to-orchestrator`. Both have description changes. No VM changes, because custom data is ignored after creation.

   Expected on a platform built from the current root: `No changes`.

## Deploy

2. Copy the manifests, scripts, and policy to the orchestrator.

   ```bash
   tar -cf - platform/tool-service policies/tool-service.json |
     REPLACE_WITH_SSH aisec-orchestrator \
     'rm -rf ~/feed/tool-service && mkdir -p ~/feed/tool-service && tar -C ~/feed/tool-service -xf -'
   ```

   Expected: no output.

3. Make the certificate. The key stays on the orchestrator.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/tool-service/make-cert.sh'
   ```

   Expected: the subject `CN=tool-service.aisec.internal`, an end date 90 days out, the three DNS names, `CA:FALSE`, and a SHA-256 fingerprint. Record the fingerprint for step 8. The script refuses to replace a certificate that exists. See [Rotate the certificate](#rotate-the-certificate).

4. Pull the image in a JIT egress window, then deploy. The orchestrator reaches the registry only while a window is open ([edge runbook](edge-vm.md#open-a-jit-egress-window)). Run this when no workflow is running: jobs live in the service's memory, and the restart ends them.

   ```bash
   IMAGE=$(grep -oE 'ghcr\.io/[^ ]+@sha256:[0-9a-f]{64}' platform/tool-service/tool-service.yaml)
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 20'
   REPLACE_WITH_SSH aisec-orchestrator "sudo k3s crictl pull $IMAGE"
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/tool-service/deploy.sh ~/feed/tool-service'
   ```

   Expected: `open for 20 minutes`, then `Image is up to date for sha256:REPLACE_WITH_CONFIG_DIGEST`, the image's config digest, which is not the digest in the manifest. `crictl` prints this line for a fresh pull too. Then `closed`. Without the pull, the new pod cannot fetch its image and the rollout stops after 180 seconds. That is reasoned from `deploy.sh`, not observed.

   Then, among the apply lines:

   ```text
   token: alg RS256 kid REPLACE_WITH_KEY_ID
   token issuer: https://kubernetes.default.svc.cluster.local
   token audience: aisec-tool-service
   token subject: system:serviceaccount:orchestration:dispatch
   audit copier pass 1 after the last line: done
   audit copier pass 2 after the last line: done
   deployment "tool-service" successfully rolled out
   tool-service-REPLACE_WITH_POD_SUFFIX ghcr.io/sindredg/ai-security-platform/tool-service@sha256:REPLACE_WITH_DIGEST
   ```

   The digest on the last line is the one in `platform/tool-service/tool-service.yaml`. A fresh deployment also prints one `last-applied-configuration` warning for each namespace's default service account. That is expected: Kubernetes created those accounts, and the script then applies its own settings on top.

   If the script stops with `the policy file does not match the cluster`, the cluster's issuer, audience, or account name differs from `policies/tool-service.json`. Every registration would be refused. Change the policy file in a pull request, not on the orchestrator.

5. Confirm that the tool port answers on the orchestrator's private address only.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo grep -A1 "^kube-proxy-arg" /etc/rancher/k3s/config.yaml'
   ```

   Expected: `- nodeport-addresses=10.40.0.4/32`. First boot writes it. Without it, the node port also answers on other local addresses. On 2026-10-15 it answered on the mesh address, which check `T.6` caught. The orchestrator left the mesh on 2026-10-17, and `T.6` is retired.

6. Confirm that the pod egress rule is loaded and starts at boot.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator \
     'systemctl is-enabled aisec-pod-egress; sudo nft list table inet aisec_pod_egress'
   ```

   Expected: `enabled`, then a `forward` chain at `priority filter + 10` with three rules for `10.42.0.0/16`: accept established, accept to pods, count and drop the rest. Then an `input` chain with three rules: accept established, accept TCP 6443 and 10250, count and drop the rest. First boot writes both. Checks `E.6` to `E.8` compare them with the template. An orchestrator without the `input` chain gets it from the [orchestrator hardening runbook](orchestrator-hardening.md).

   An orchestrator built before 2026-10-15 has neither the setting in step 5 nor this rule. Rebuild it from the current template, or apply both by hand as the [worklog](../worklogs/0003-toolchain-integration.md#the-deployment-on-the-orchestrator) records. Custom data does not reach a running VM.

## Give the worker the certificate

7. Copy the certificate to the worker, and confirm the name. The name is in the worker's first-boot template. The certificate is not, because it is made on the orchestrator after the worker exists.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /etc/aisec/tool-service/tls.crt' |
     REPLACE_WITH_SSH aisec-worker 'sudo install -D -m 644 /dev/stdin /etc/aisec/tool-service.crt'
   REPLACE_WITH_SSH aisec-worker 'grep tool-service.aisec.internal /etc/hosts'
   ```

   Expected: `10.40.0.4 aisec-orchestrator tool-service.aisec.internal`. A worker built before 2026-10-14 has the line without the second name. Add the name to that line.

8. Confirm that the worker holds the same certificate.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'openssl x509 -in /etc/aisec/tool-service.crt -noout -enddate -fingerprint -sha256'
   ```

   Expected: the fingerprint from step 3.

## Check

9. Run every check. Run on the workstation, as in the [validation page](../validation/README.md#run-the-checks).

   ```bash
   validation/platform-checks.sh
   ```

   Expected: `PASS` for every `T` check, `E.6` to `E.8`, `M.5`, and `Z.13`. A `U` check can fail on the day a security update is published and before the next unattended run. That is not a deployment fault. [Tool service checks](../validation/tool-service.md) say what each one proves.

## Round trip

The job token is made on the workstation, as the dispatch step will make it. Only its SHA-256 digest goes to the orchestrator.

10. Make a job token and register a job for it.

    ```bash
    TOKEN=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
    DIGEST=$(printf %s "$TOKEN" | sha256sum | cut -d' ' -f1)
    REG='sudo ~/feed/tool-service/platform/tool-service/register.sh'
    REPLACE_WITH_SSH aisec-orchestrator "$REG register check-1 $DIGEST"
    ```

    Expected: `201 {"job": "check-1"}`. The job lives 600 seconds unless a fourth and fifth argument say otherwise.

11. Call the job's tool from the worker, then a tool the job does not have.

    ```bash
    call() {
      REPLACE_WITH_SSH aisec-worker "curl -s -w '\nHTTP %{http_code}\n' --max-time 10 \
        --cacert /etc/aisec/tool-service.crt \
        -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":{\"reference\":\"ev-0001\"}}}' \
        https://tool-service.aisec.internal:30443/mcp"
    }
    call get_evidence
    call run_shell
    ```

    Expected: the synthetic evidence `ev-0001` with `"isError":false` and `HTTP 200`, then `refused: tool not in the job's scope` with `"isError":true` and `HTTP 200`. A refused tool is an error result in a normal response, as MCP defines it, not an HTTP error.

12. Try to register with tokens the service must refuse: the job token, and a dispatch token for another audience.

    ```bash
    WRONG=$(REPLACE_WITH_SSH aisec-orchestrator \
      'sudo k3s kubectl create token dispatch -n orchestration --audience some-other-audience --duration 10m')
    REPLACE_WITH_SSH aisec-orchestrator "$REG register check-2 $DIGEST $TOKEN"
    REPLACE_WITH_SSH aisec-orchestrator "$REG register check-2 $DIGEST $WRONG"
    unset WRONG
    ```

    Expected: `401 {"error": "refused"}` twice, each followed by `pod orchestration/register-... terminated (Error)`. The client exits 1 on a refusal, and `kubectl` reports that.

13. Revoke the job, and call again with its token.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "$REG revoke check-1"
    call get_evidence
    ```

    Expected: `200 {"job": "check-1"}`, then `{"error": "refused"}` and `HTTP 401`.

14. A job whose lifetime ends is refused without a revocation. Register one for 30 seconds, call at once, and call again after 40.

    ```bash
    TOKEN=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
    DIGEST=$(printf %s "$TOKEN" | sha256sum | cut -d' ' -f1)
    REPLACE_WITH_SSH aisec-orchestrator "$REG register expiry-1 $DIGEST - 30"
    call get_evidence | tail -n 1
    sleep 40
    call get_evidence | tail -n 1
    unset TOKEN DIGEST
    ```

    Expected: `201 {"job": "expiry-1"}`, `HTTP 200`, then `HTTP 401`. The `-` keeps the dispatch account's own token.

15. Read the audit lines.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator \
      'sudo k3s kubectl logs -n tool-services deploy/tool-service --since=15m' | tail -n 12
    ```

    Expected: one JSON line per decision. `register` allowed for `check-1`. `call` allowed for `get_evidence` with `result_bytes`, and refused for `run_shell` with the reason `tool not in the job's scope`. Two `request` lines refused with `caller not accepted`. `revoke` allowed. A `request` refused with `revoked token`. For `expiry-1`, the last line has the reason `expired token`. No line holds a token. The [audit line](../security/tool-service.md#the-audit-line) lists the fields.

    These lines are the pod's standard output, gone when the pod is replaced. Since 2026-10-16 the audit copier keeps each one in an append-only file on the orchestrator, out of the worker's reach ([audit log runbook](audit-log.md)).

## Rotate the certificate

Not run. The certificate is valid for 90 days, and check `T.7` fails when 14 days are left.

```bash
REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/tool-service/make-cert.sh --rotate'
REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/tool-service/deploy.sh ~/feed/tool-service'
```

Then steps 7 to 9. Between the restart and the copy, the worker does not trust the new certificate, so its calls fail. That is reasoned, not observed. Do this when no job is running.

## After a rebuild

| Rebuilt | Run again |
| --- | --- |
| The orchestrator | Steps 2 to 15. The cluster is empty and the certificate is gone, so the worker needs the new one |
| The worker | Steps 7 to 9. Its first boot writes the name, not the certificate |

## Not covered yet

- A deployment on an orchestrator built from the current template. Steps 5 and 6 there read back what first boot wrote. On 2026-10-15 both were applied by hand.
