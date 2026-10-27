# Workflows and dispatch: operator procedure

Status: Written on 2026-10-20 for [ADR 0029](../decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md) and [ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md). Implemented on 2026-10-21, from scripts with the same commands. Steps 1 to 8 ran between 04:16 and 04:24 UTC, step 1 without the signature check, which ran on 2026-10-19. Steps 9 to 16 ran between 15:11 and 15:26 UTC, and steps 13, 14, and 7's name lookups again between 15:37 and 15:44 UTC. The first round trip, at 14:12 UTC, never started: the executor's token secret was missing ([troubleshooting 14](../troubleshooting/14-workflow-pods-wait-for-the-executors-token.md)). The UI exited without its config map ([troubleshooting 15](../troubleshooting/15-argo-server-exits-without-its-config-map.md)). Both are in the manifests now. Results are in the [worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows). [A new dispatch image](#a-new-dispatch-image) ran on 2026-10-22: steps 3, 4, 9, and 10 again ([worklog](../worklogs/0003-toolchain-integration.md#installed-the-images-on-the-fixed-base)), and again on 2026-10-23, for the image that reads `slot_erased`, with a job refused while the model server was stopped and a controller restart during a job ([worklog](../worklogs/0003-toolchain-integration.md#installed-the-erase-before-each-job-and-the-answer-lines)). Steps 3, 4, 9, and 10 ran on 2026-10-24 for v4.1.6, after the signature check of step 1 on the workstation ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#argo)). Steps 3, 4, 6, 9, and 10 ran on 2026-10-25 for the comparison step and the image that carries it, with the first read of [A new dispatch image](#a-new-dispatch-image), from a script with the same commands ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-comparison)). Steps 3 and 4, with the first read of [A new dispatch image](#a-new-dispatch-image), ran again at 21:48 UTC for the image from #202 ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-rollout)).

Run these steps to install Argo Workflows' controller, make the dispatch key, and send a job from a workflow to the worker and back: a round trip, a cancel, and the controller's refusal of anything but the template. No cloud resource changes. The worker's side is the [agent runtime runbook](agent-runtime.md#jobs-over-the-socket), steps 8 to 12, which come first.

## Inputs and access

| Input | Notes |
| --- | --- |
| The model server and the agent runtime, with the job socket | The [model server runbook](model-server.md) and the [agent runtime runbook](agent-runtime.md), through step 8. `S`, `G.6` to `G.9` pass |
| The tool service (an MCP server), deployed | The [tool service runbook](tool-service.md). The `T` checks pass |
| SSH to the orchestrator, the worker, and the edge | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| The tunnel to the API server | `REPLACE_WITH_SSH -N -L 6443:127.0.0.1:6443 aisec-orchestrator` in its own terminal ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md)) |
| Argo's command line v4.1.6 on the workstation | `argo-linux-<arch>.gz` from the release, checked against the digest the release lists for it |
| cosign on the workstation, for step 1 | The newest release, checked against its listed digest. v3.1.3 on 2026-10-19 |
| A checkout of this repository on the workstation | `platform/argo/`, `platform/dispatch/`, `worker/agent-runtime/` |

## Check the pins

1. Confirm the release and the image signatures. Run on the workstation.

   ```bash
   gh api repos/argoproj/argo-workflows/releases/latest -q .tag_name
   gh api repos/argoproj/argo-workflows/releases/tags/v4.1.6 \
     -q '.assets[] | select(.name == "namespace-install.yaml" or .name == "argo-workflows-cosign.pub") | "\(.name) \(.digest)"'
   grep ARGO_INSTALL_SHA256 platform/argo/pins.env
   curl -sSLO https://github.com/argoproj/argo-workflows/releases/download/v4.1.6/argo-workflows-cosign.pub
   for image in $(grep -ohE 'quay.io/argoproj/[a-z-]+@sha256:[0-9a-f]{64}' platform/argo/argo.yaml); do
     cosign verify --key argo-workflows-cosign.pub "$image" > /dev/null && echo "verified $image"
   done
   ```

   Expected: `v4.1.6`, the install file's digest equal to `ARGO_INSTALL_SHA256`, and `verified` for `workflow-controller` and `argoexec`. A newer release is a decision, not a step: change the pins in a pull request first.

## The way out

2. Install the fetch list with `.quay.io` on the edge, as in step 13 of the [edge runbook](edge-vm.md).

   ```bash
   REPLACE_WITH_SSH aisec-edge 't=$(mktemp) && cat > "$t" && sudo install -o root -g root -m 0644 "$t" /etc/squid/aisec-fetch-hosts && rm -f "$t"' \
     < edge/fetch-hosts
   REPLACE_WITH_SSH aisec-edge 'sudo systemctl reload squid && systemctl is-active squid'
   ```

   Expected: `active`. `P.18` passes on the next check run, and failed since the list changed in the repository.

## Argo

3. Copy the manifests and scripts to the orchestrator, open a just-in-time (JIT) egress window, download the release file and pull the images, and close the window.

   ```bash
   tar -C platform/argo -cf - . |
     REPLACE_WITH_SSH aisec-orchestrator 'rm -rf feed/argo/scripts && mkdir -p feed/argo/scripts feed/argo/stage && tar -C feed/argo/scripts -xf -'
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 20'
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/argo && scripts/fetch.sh stage'
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `open for 20 minutes`, then `ok    namespace-install.yaml (v4.1.6)` and one `ok` line for each of the three images: the controller, the executor, and the dispatch image. Then `closed`. A `TCP_DENIED` in Squid's log during the window names a host the list lacks.

4. Install.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/argo && sudo scripts/install.sh stage'
   ```

   Expected: the eight custom resource definition names, `condition met` three times, the namespace and its default account patched, the policies, the controller, the accounts, the executor's token secret, the comparison step's config map `netbox-verdicts` ([ADR 0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md)), and the template `created`, `successfully rolled out`, and one line with the controller pod, `Running`, and the image digest from `argo.yaml`. On the next check run, `W.1` to `W.9` and `W.11` pass.

## The host rule

5. Replace the host rule file with the template's, check it, and load it. The file deletes and recreates the table in one transaction.

   ```bash
   .github/scripts/render-cloud-init-file.sh orchestrator /etc/aisec/pod-egress.nft |
     REPLACE_WITH_SSH aisec-orchestrator 'sudo tee /etc/aisec/pod-egress.nft > /dev/null &&
       sudo nft -c -f /etc/aisec/pod-egress.nft && sudo nft -f /etc/aisec/pod-egress.nft &&
       sudo nft list chain inet aisec_pod_egress forward'
   ```

   Expected: the `forward` chain with four rules, the third `ip saddr 10.42.0.0/16 ip daddr 10.40.0.36 tcp dport 22 accept`. `E.6` passes on the next check run.

6. Probe the worker's SSH port and the tool service's registration port from two new pods in `orchestration`, each labelled as a workflow's pod: one with the dispatch label, one with the comparison step's. Each tries both ports at 0, 5, and 20 seconds, from the dispatch image.

   ```bash
   IMAGE=$(grep -oE 'ghcr\.io/[^ ]+/dispatch@sha256:[0-9a-f]{64}' platform/argo/workflow-template.yaml | head -n 1)
   REGISTRATION=$(REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n tool-services get service tool-service -o jsonpath='{.spec.clusterIP}'")
   PROBE='import socket, sys, time
   start = time.monotonic()
   for at in (0, 5, 20):
       time.sleep(max(0, start + at - time.monotonic()))
       ends = []
       for host, port in (("10.40.0.36", 22), (sys.argv[1], 8444)):
           try:
               socket.create_connection((host, port), 4).close(); ends.append("open")
           except ConnectionRefusedError: ends.append("refused")
           except TimeoutError: ends.append("timeout")
           except OSError as error: ends.append("other " + str(error))
       print(f"{at}s worker:{ends[0]} registration:{ends[1]}", end="  ")'
   probe() {
     OVERRIDES=$(python3 -I -c 'import json, sys; print(json.dumps({"metadata": {"labels": json.loads(sys.argv[3])}, "spec": {
       "automountServiceAccountToken": False,
       "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "seccompProfile": {"type": "RuntimeDefault"}},
       "containers": [{"name": "probe", "image": sys.argv[1], "command": ["python", "-c", sys.argv[2], sys.argv[4]],
         "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                             "capabilities": {"drop": ["ALL"]}}}]}}))' "$IMAGE" "$PROBE" "$1" "$REGISTRATION")
     echo "-- $1"
     REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl run label-probe -n orchestration --restart=Never \
       --image='$IMAGE' --overrides='$OVERRIDES' >/dev/null &&
       sudo k3s kubectl wait -n orchestration --for=jsonpath='{.status.phase}'=Succeeded pod/label-probe --timeout=90s >/dev/null &&
       sudo k3s kubectl logs -n orchestration label-probe; echo; sudo k3s kubectl delete pod -n orchestration label-probe >/dev/null"
   }
   probe '{"app.kubernetes.io/name": "compare", "workflows.argoproj.io/workflow": "label-probe"}'
   probe '{"app.kubernetes.io/name": "dispatch", "workflows.argoproj.io/workflow": "label-probe"}'
   ```

   Expected: for the comparison step's pod, `refused` on both ports at 5 and 20 seconds, where its policy holds. For the dispatch pod, `open` on both at 5 and 20 seconds. At 0 seconds either may read otherwise: kube-router writes a pod's policies after the pod starts, and the host rule cannot tell pods apart. That is the residual ADR 0030 names (T47). Record what each reads. On 2026-10-25 the comparison step's pod read `worker:open registration:refused` at 0 seconds, and the dispatch pod the same.

7. The same start-of-pod probe in `tool-services`, which has never had one ([#65](https://github.com/sindredg/ai-security-platform/issues/65)): a new pod tries `1.1.1.1:443` at 0, 5, and 20 seconds.

   ```bash
   PROBE2='import socket, time
   start = time.monotonic()
   for at in (0, 5, 20):
       time.sleep(max(0, start + at - time.monotonic()))
       try:
           socket.create_connection(("1.1.1.1", 443), 4).close(); end = "open"
       except ConnectionRefusedError: end = "refused"
       except TimeoutError: end = "timeout"
       except OSError as error: end = "other " + str(error)
       print(f"{at}s {end}", end="  ")'
   probe2() {
     OVERRIDES=$(python3 -c 'import json, sys; print(json.dumps({"spec": {
       "automountServiceAccountToken": False,
       "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "seccompProfile": {"type": "RuntimeDefault"}},
       "containers": [{"name": "probe", "image": sys.argv[1], "command": ["python", "-c", sys.argv[2]],
         "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                             "capabilities": {"drop": ["ALL"]}}}]}}))' "$IMAGE" "$PROBE2")
     REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl run egress-probe -n tool-services --restart=Never \
       --image='$IMAGE' --overrides='$OVERRIDES' >/dev/null &&
       sudo k3s kubectl wait -n tool-services --for=jsonpath='{.status.phase}'=Succeeded pod/egress-probe --timeout=90s >/dev/null &&
       sudo k3s kubectl logs -n tool-services egress-probe; echo; sudo k3s kubectl delete pod -n tool-services egress-probe >/dev/null"
   }
   probe2
   ```

   Expected: no `open` at any time. `timeout` where the host rule drops, `refused` where kube-router does.

   Then name lookups from a new pod, at 0 and 20 seconds: the cluster's own name, and a public one. In `tool-services`, and in a dispatch pod as the comparison step, since that pod may use DNS.

   ```bash
   LOOKUP='import socket, time
   start = time.monotonic()
   for at in (0, 20):
       time.sleep(max(0, start + at - time.monotonic()))
       for name in ("kubernetes.default.svc.cluster.local.", "example.com."):
           try:
               socket.getaddrinfo(name, 443); end = "resolves"
           except OSError: end = "fails"
           print(f"{at}s {name} {end}", end="  ")'
   PROBE2=$LOOKUP probe2
   PROBE=$LOOKUP probe '{"app.kubernetes.io/name": "dispatch"}'
   ```

   Expected: `example.com.` fails four times. The orchestrator gets no answer from Azure DNS (`E.13`, `E.14`), so no pod resolves a public name. The cluster's name resolves both times in the dispatch pod, which shows the probe can report a resolved name. In `tool-services` it fails at 20 seconds, where the namespace denies DNS, and may resolve at 0 seconds, before kube-router writes the policy.

## The dispatch key

8. Read the worker's host key over the operator's own session, make the key pair and the secret on the orchestrator with it, and install the public half on the worker.

   ```bash
   HOST_KEY=$(REPLACE_WITH_SSH aisec-worker 'cut -d " " -f 1,2 /etc/ssh/ssh_host_ed25519_key.pub')
   PUB=$(REPLACE_WITH_SSH aisec-orchestrator "cd feed/argo && sudo scripts/make-dispatch-key.sh '$HOST_KEY'")
   echo "$PUB"
   REPLACE_WITH_SSH aisec-worker "cd feed/agent-runtime && sudo scripts/install-job.sh '$PUB'"
   ```

   Expected: one `ssh-ed25519 ... aisec-dispatch` line, then `root aisec-job 660 /run/aisec-job/agent.sock` and `active`. The private half was never outside the orchestrator's memory and the secret. On the next check run, `G.5` and `W.10` pass.

## The operator's token

9. Make a token for `argo-operator`, valid 12 hours, and a kubeconfig on the workstation that uses it through the tunnel.

   ```bash
   CFG=REPLACE_WITH_LOCAL_DIR/argo.kubeconfig
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/rancher/k3s/server/tls/server-ca.crt' > REPLACE_WITH_LOCAL_DIR/k3s-ca.crt
   TOKEN=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration create token argo-operator --duration 12h')
   ( umask 077
     KUBECONFIG=$CFG kubectl config set-cluster aisec --server https://127.0.0.1:6443 \
       --certificate-authority REPLACE_WITH_LOCAL_DIR/k3s-ca.crt --embed-certs
     KUBECONFIG=$CFG kubectl config set-credentials argo-operator --token "$TOKEN"
     KUBECONFIG=$CFG kubectl config set-context aisec --cluster aisec --user argo-operator --namespace orchestration
     KUBECONFIG=$CFG kubectl config use-context aisec ) > /dev/null
   unset TOKEN
   export KUBECONFIG=$CFG
   argo template list
   argo list
   ```

   Expected: `investigate`, then `No workflows found.` The file is `600`. Without the tunnel, both commands fail to connect.

## The round trip

10. Submit the fixture question from the template, and watch it.

    ```bash
    argo submit --from workflowtemplate/investigate -p task="$(cat worker/agent-runtime/fixture/question.txt)" --watch
    argo get @latest -o json | python3 -c 'import json, sys
    wf = json.load(sys.stdin)
    for node in wf["status"]["nodes"].values():
        for p in (node.get("outputs") or {}).get("parameters", []):
            if p["name"] == "result":
                print(node["displayName"], json.dumps(json.loads(p["value"]), indent=1))'
    argo logs @latest
    ```

    Expected, after one to three minutes: `Succeeded`, with the dispatch step and the exit handler both green, and the compare step `Skipped`: it runs for NetBox jobs only ([evidence collection runbook](evidence-collection.md), step 12). The result has `"status": "completed"`, `"tool_calls": 1`, `"tool_errors": 0`, `"slot_erased": true`, an `answer` that ends with `Status: confirmed` and `Excess: tenancy.contact, circuits.circuit`, and a `transcript`. The two lines are the model's: on 2026-10-25 one of three synthetic outputs ended without them, and one with `Excess: none`. The dispatch step's log shows each part of the transcript under a `-- role type` line, from `-- system instructions` to the `get_evidence` call, the evidence, and `-- answer`. The audit file on the orchestrator has `register`, `call allowed` for `get_evidence`, and `revoke`, each with the workflow's name as the job.

    This is the first gate criterion of milestone 3: a workflow starts a worker job, the agent calls one authorized tool, and a schema-checked result comes back.

11. Stop a run while the agent works, and see what it left.

    ```bash
    argo submit --from workflowtemplate/investigate -p task="$(cat worker/agent-runtime/fixture/question.txt)"
    sleep 25; argo stop @latest; sleep 15; argo get @latest
    REPLACE_WITH_SSH aisec-worker '
      for _ in $(seq 1 60); do
        [ "$(systemctl list-units --all --no-legend "aisec-agent-job@*" | wc -l)" = 0 ] && break
        sleep 2
      done
      systemctl list-units --all --no-legend "aisec-agent-job@*" | wc -l
      sudo find /tmp /var/tmp -maxdepth 1 -name "systemd-private-*aisec-agent-job@*" | wc -l
      journalctl --no-pager -o cat -u "aisec-agent-job@*" --since -5min | grep outcome'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo tail -n 5 /var/log/aisec/tool-audit.jsonl'
    ```

    Expected: the dispatch step `Failed` with exit code 143, the exit handler `Succeeded`. On the worker, within two minutes, `0`, `0`, and a line with `"outcome": "cancelled"` and `"slot_erased": true`. The audit file has the job's `revoke`. This is the second gate criterion: cancelling a workflow stops the worker job and cleans up its session.

12. Submit two runs at once. The second waits for the first.

    ```bash
    for i in 1 2; do argo submit --from workflowtemplate/investigate -p task="$(cat worker/agent-runtime/fixture/question.txt)"; done
    sleep 10; argo list
    ```

    Expected: one `Running`, one `Pending` with a message that it waits for the lock `orchestration/Mutex/worker`. Both end `Succeeded`.

## The restriction to templates

13. Try what the restriction refuses: a workflow of its own, and the template with a field the submission may not set.

    ```bash
    argo submit - <<'EOF'
    apiVersion: argoproj.io/v1alpha1
    kind: Workflow
    metadata: {generateName: own-}
    spec:
      entrypoint: main
      templates:
        - name: main
          container: {image: busybox, command: ["true"]}
    EOF
    argo submit - <<'EOF'
    apiVersion: argoproj.io/v1alpha1
    kind: Workflow
    metadata: {generateName: override-}
    spec:
      workflowTemplateRef: {name: investigate}
      arguments: {parameters: [{name: task, value: x}]}
      podSpecPatch: '{"containers": [{"name": "main", "image": "busybox"}]}'
    EOF
    sleep 10; argo list
    ```

    Expected: both `Error`, and no pod starts for either. The messages: `workflows must use workflowTemplateRef to be executed when the controller is in reference mode` for the first, and `fields [PodSpecPatch] are not permitted when using workflowTemplateRef with templateReferencing restriction` for the second.

## The UI

14. Run Argo's server on the workstation in local mode, with the same kubeconfig, and open it.

    ```bash
    argo server --auth-mode server --namespaced --managed-namespace orchestration --configmap argo-ui
    ```

    Expected: `https://localhost:2746` shows the workflows from the steps above, with each step's logs. Stop it with Ctrl-C. Nothing in the cluster changes.

## Measure and check

15. Read the controller's footprint.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl top pod -n argo; free -m | sed -n 2p'
    ```

    Expected: one line for the controller, with its CPU and memory. Record them. They are the orchestrator footprint gate.

16. Run every check.

    ```bash
    validation/platform-checks.sh
    ```

    Expected: `PASS` for `E.6`, `G.5` to `G.10`, `K.3`, `W.1` to `W.12`, and every check that passed before.

## A new dispatch image

After a change to `workflow-template.yaml` merges, such as a new dispatch digest, run steps 3 and 4 again, then 9 and 10, then 16. Start when no workflow is running:

```bash
REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration get workflows --no-headers'
```

Expected: no line with `Running`.

Expected in step 3: an `ok` line with the new dispatch digest. In step 4: the template `configured`, and the other objects `unchanged`. The UI's config map read `configured` on 2026-10-22 without a change ([worklog](../worklogs/0003-toolchain-integration.md#the-deploy)). Then read the template's images:

```bash
REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n orchestration get workflowtemplate investigate \
  -o jsonpath='{range .spec.templates[*]}{.name} {.container.image}{\"\\n\"}{end}'"
```

Expected: `investigate` with no image, then `dispatch`, `compare`, and `revoke`, each with the new digest. After step 10, read the images the workflow's pods ran:

```bash
REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n orchestration get pods -l workflows.argoproj.io/workflow=REPLACE_WITH_WORKFLOW \
  -o jsonpath='{range .items[*]}{.metadata.name}{range .status.containerStatuses[*]} {.name}={.imageID}{end}{\"\\n\"}{end}'"
```

Expected: two pods, each with `main=` on the new dispatch digest and `wait=` on the executor's digest from `argo.yaml`. A NetBox job has a third, the comparison step's. In step 16, `W.9` passes. It fails from the merge until step 4, because the template in the cluster differs from the checkout's.

## Remove

To take Argo off the cluster: delete the template, the accounts, Roles, and the executor's token secret in `rbac.yaml`, the policies in `network-policies.yaml`, the `argo` namespace, and the eight custom resource definitions. Delete the `dispatch-ssh` secret, and empty the key line on the worker by running `install-job.sh` with no argument after removing `/home/aisec-job/.ssh/authorized_keys`. Load the host rule from the template of the commit before this change, as in step 5.
