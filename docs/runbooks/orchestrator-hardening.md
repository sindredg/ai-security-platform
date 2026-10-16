# Orchestrator hardening: operator procedure

Status: Implemented on 2026-10-16. The procedure was run that day on the live orchestrator, with the same file contents, probes, and order, from scripts kept outside the repository. The results are in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#rollout). The commands as written here were checked for quoting with a stubbed `ssh`, not run against the orchestrator. A first boot from the current template, which writes the same files, has not been run.

Run these steps on an orchestrator built before this change, to add two things first boot now does by itself: the `input` chain of the host rule ([ADR 0023](../decisions/0023-the-host-rule-limits-what-pods-reach-on-the-host.md)), and a pod security level for every namespace without a label ([#70](https://github.com/sindredg/ai-security-platform/issues/70)). Custom data does not reach a running VM, so a rebuilt orchestrator needs none of this, only step 9.

## Inputs and access

| Input | Notes |
| --- | --- |
| SSH to the orchestrator over the mesh VPN | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| The tool service, deployed | The probe pod runs its image, which is already on the node. The [tool service runbook](tool-service.md) |
| A checkout of this repository on the workstation, at the commit to apply | The template is `infra/platform/cloud-init/orchestrator.yaml.tftpl`. The commands below carry the same file contents |
| No job active | Step 6 restarts K3s and the system deployments |

## The host rule for traffic to the host

1. Probe the host from a new pod in `default`, before the change. `default` has no network policy, so only the host rule decides.

   ```bash
   IMAGE=$(sed -n 's/^ *image: \(ghcr.io[^ ]*\)$/\1/p' platform/tool-service/tool-service.yaml)
   PROBE='import socket
   for host, port in (("10.40.0.4", 22), ("10.42.0.1", 22), ("10.40.0.4", 6443), ("10.40.0.4", 10250)):
       try:
           socket.create_connection((host, port), 5).close(); end = "open"
       except ConnectionRefusedError: end = "refused"
       except TimeoutError: end = "timeout"
       except OSError as error: end = "other " + str(error)
       print(f"{host}:{port} {end}", end="  ")'
   OVERRIDES=$(python3 -c 'import json, sys; print(json.dumps({"spec": {
     "automountServiceAccountToken": False,
     "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "seccompProfile": {"type": "RuntimeDefault"}},
     "containers": [{"name": "probe", "image": sys.argv[1], "command": ["python", "-c", sys.argv[2]],
       "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                           "capabilities": {"drop": ["ALL"]}}}]}}))' "$IMAGE" "$PROBE")
   probe() {
     REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl run host-probe -n default --restart=Never \
       --image='$IMAGE' --overrides='$OVERRIDES' >/dev/null &&
       sudo k3s kubectl wait -n default --for=jsonpath='{.status.phase}'=Succeeded pod/host-probe --timeout=90s >/dev/null &&
       sudo k3s kubectl logs -n default host-probe; echo; sudo k3s kubectl delete pod -n default host-probe >/dev/null"
   }
   probe
   ```

   Expected: `10.40.0.4:22 open  10.42.0.1:22 open  10.40.0.4:6443 open  10.40.0.4:10250 open`. This is the broken input for step 3: any pod reaches SSH.

2. Replace the rule file with the template's and load it. The file deletes and recreates the table in one transaction.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo tee /etc/aisec/pod-egress.nft >/dev/null <<"NFT"
   table inet aisec_pod_egress
   delete table inet aisec_pod_egress
   table inet aisec_pod_egress {
     chain forward {
       type filter hook forward priority filter + 10; policy accept;
       ip saddr 10.42.0.0/16 ct state established,related accept
       ip saddr 10.42.0.0/16 ip daddr 10.42.0.0/16 accept
       ip saddr 10.42.0.0/16 counter drop
     }
     chain input {
       type filter hook input priority filter + 10; policy accept;
       ip saddr 10.42.0.0/16 ct state established,related accept
       ip saddr 10.42.0.0/16 tcp dport { 6443, 10250 } accept
       ip saddr 10.42.0.0/16 counter drop
     }
   }
   NFT
   sudo nft -c -f /etc/aisec/pod-egress.nft && sudo nft -f /etc/aisec/pod-egress.nft &&
   sudo nft list table inet aisec_pod_egress'
   ```

   Expected: the table with a `forward` chain and an `input` chain, each with three rules. The `input` chain lists `tcp dport { 6443, 10250 } accept`.

3. Probe again, and read the drop counter.

   ```bash
   probe
   REPLACE_WITH_SSH aisec-orchestrator 'sudo nft list chain inet aisec_pod_egress input | grep drop'
   ```

   Expected: `10.40.0.4:22 timeout  10.42.0.1:22 timeout  10.40.0.4:6443 open  10.40.0.4:10250 open`, and a counter above zero.

## Pod security for every namespace

4. Send a privileged pod to `default` as a server-side dry run. Admission runs and nothing is stored.

   ```bash
   PRIV='{"spec":{"containers":[{"name":"priv","image":"registry.k8s.io/pause:3.10","securityContext":{"privileged":true}}]}}'
   dry() {
     REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl run priv -n default --image=registry.k8s.io/pause:3.10 \
       --dry-run=server --overrides='$PRIV' 2>&1"
   }
   dry
   ```

   Expected: `pod/priv created (server dry run)`. This is the broken input for step 7.

5. Write the admission file, add the API server argument, and label `kube-system`.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo install -m 600 /dev/stdin /var/lib/rancher/k3s/server/psa.yaml <<"YAML"
   apiVersion: apiserver.config.k8s.io/v1
   kind: AdmissionConfiguration
   plugins:
     - name: PodSecurity
       configuration:
         apiVersion: pod-security.admission.config.k8s.io/v1
         kind: PodSecurityConfiguration
         defaults:
           enforce: restricted
           enforce-version: latest
           audit: restricted
           audit-version: latest
           warn: restricted
           warn-version: latest
         exemptions:
           usernames: []
           runtimeClasses: []
           namespaces: []
   YAML
   grep -q admission-control-config-file /etc/rancher/k3s/config.yaml ||
     sudo sed -i "s|^  - audit-log-maxsize=100\$|&\n  - admission-control-config-file=/var/lib/rancher/k3s/server/psa.yaml|" /etc/rancher/k3s/config.yaml
   sudo grep -A6 "^kube-apiserver-arg" /etc/rancher/k3s/config.yaml
   sudo k3s kubectl label --overwrite namespace kube-system \
     pod-security.kubernetes.io/enforce=baseline pod-security.kubernetes.io/enforce-version=latest'
   ```

   Expected: the `kube-apiserver-arg` list ends with `admission-control-config-file=/var/lib/rancher/k3s/server/psa.yaml`, then `namespace/kube-system labeled`.

6. Restart K3s, then restart the system deployments, so that their new pods go through admission at `baseline`.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo systemctl restart k3s
     until sudo k3s kubectl get --raw /readyz >/dev/null 2>&1; do sleep 5; done
     sudo k3s kubectl wait --for=condition=Ready node --all --timeout=180s
     sudo k3s kubectl rollout restart -n kube-system deployment; sleep 10
     sudo k3s kubectl wait -n kube-system --for=condition=Available deployment --all --timeout=180s
     sudo journalctl -u k3s --no-pager | grep "Running kube-apiserver" | tail -n 1 |
       grep -o -- "--admission-control-config-file=[^ ]*"'
   ```

   Expected: the node `condition met`, three `restarted` lines, each with a `would violate PodSecurity "restricted:latest"` warning, three deployments `condition met`, and `--admission-control-config-file=/var/lib/rancher/k3s/server/psa.yaml`. The warnings come from the cluster's default warn level, which the `kube-system` label leaves at `restricted`. They do not refuse anything.

7. Send the privileged pod again.

   ```bash
   dry
   ```

   Expected: `Error from server (Forbidden): pods "priv" is forbidden: violates PodSecurity "restricted:latest": privileged ...`.

8. Confirm that a pod at the restricted level still runs in `default`.

   ```bash
   probe
   ```

   Expected: the same line as step 3.

## Check

9. Run every check, as in the [validation page](../validation/README.md#run-the-checks).

   ```bash
   validation/platform-checks.sh
   ```

   Expected: `PASS` for `E.6` to `E.8` and `K.1` to `K.10`. `K.9` lists any namespace that admits the privileged pod. [Containment](../validation/containment.md) and [cluster](../validation/cluster.md) say what each check proves.
