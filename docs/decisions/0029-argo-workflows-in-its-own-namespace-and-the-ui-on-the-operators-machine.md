# 0029. Argo Workflows in its own namespace, and its UI on the operator's machine

Status: Proposed
Date: 2026-10-19

## Context

The roadmap names Argo Workflows for milestone 3, and the [component index](../components/README.md#planned) lists what it has to prove: dispatch to the worker VM, restart recovery, and footprint. The newest stable release is v4.1.5, published on 2026-10-09 and read from the project's release page on 2026-10-19.

Three facts from that release shape how it goes on the orchestrator:

- **The upstream namespace install puts the controller, the server, and the workflows in one namespace.** Both of its Roles may read secrets and open a shell in any pod of that namespace (`secrets: get`, `pods/exec`). The dispatch key will be a secret in `orchestration` ([0012](0012-dispatch-over-ssh-with-a-forced-command.md)). The server is a web application that parses what a browser sends it.
- **The images are on quay.io**, which is not on the [fetch list](../components/package-proxy.md). They are signed with cosign, and the release publishes the public key.
- **The manifests set no seccomp profile.** Pod Security Admission runs every namespace at `restricted`, which refuses a pod without one (`K.9`).

The orchestrator has 2 vCPUs and 8 GiB, with K3s, the tool service, and the log agent on it. Argo's documentation describes a local mode for its server: `argo server` on a workstation, with the user's own kubeconfig, serves the same UI on `localhost:2746`.

## Options

| Option | Where the controller and the UI run | What the UI process can read | Footprint on the orchestrator |
| --- | --- | --- | --- |
| Upstream namespace install in `orchestration` | Both beside the dispatch pods | The dispatch key, and a shell in any dispatch pod | Two pods |
| Controller in `argo`, managing `orchestration`, server in the cluster | Both in `argo`. The UI behind a port-forward | Secrets in `argo` only. The server's own account still reaches what upstream gives it there | Two pods |
| Controller in `argo`, managing `orchestration`, UI on the operator's machine | Controller in the cluster, the UI where the operator runs it | Whatever the operator's token allows | One pod |
| Cluster install | Anywhere | Every namespace | Two pods. Rejected: more reach than one namespace needs |

## Decision

**The controller.** Argo Workflows v4.1.5, the namespace install, in a namespace of its own, `argo`. The controller runs with `--namespaced --managed-namespace=orchestration`, so it watches `orchestration` and nothing else. Its upstream Role, without `secrets: get`, stays in `argo` for its lease and configuration, and a copy of that Role is bound to it in `orchestration`. In v4.1.5 the controller reads a secret only for the agent of HTTP and plugin templates, which these workflows do not use. No other Argo component runs in the cluster: no server, no workflow archive, no artifact repository.

**The UI.** The operator runs `argo server` in local mode, or the `argo` command line, on the workstation. Both reach the API server through the tunnel that [0022](0022-short-lived-ssh-certificates-for-the-operator.md) already allows, with a kubeconfig whose token belongs to `argo-operator`: a service account in `orchestration` that may create, read, stop, and delete workflows, read workflow templates, and read pod logs. It may also read one config map, `argo-ui`: the server reads its settings from a map in its namespace when it starts, and exits if it cannot. The map is empty. The token is made on the orchestrator with `kubectl create token` for 12 hours, the life of an SSH certificate.

**Only templates run.** The controller's configuration sets `templateReferencing: Secure`. It processes a workflow only when the workflow references a template, rejects a submission that sets a field outside Argo's short allow-list (arguments, the entry point, deadlines, and clean-up settings among them), and fails a running workflow whose template changed. Without it, the operator's right to create workflows would be the right to run any pod in `orchestration`, including one that mounts the dispatch key.

**The workflow pods.** The main container runs as `dispatch` with no API token mounted. The executor's containers run as `argo-executor`, whose Role allows `create` and `patch` on `workflowtaskresults` in `orchestration` and nothing else, which is the minimum Argo's documentation names. With no token mounted in the pod, the controller mounts the executor's from a secret named `argo-executor.service-account-token`, into the executor's containers only. Kubernetes no longer makes that secret, so `rbac.yaml` asks for it. A network policy lets workflow pods reach the API server. The dispatch pods get their own egress, set in [0030](0030-how-a-job-reaches-the-worker.md).

**The images.** `workflow-controller` and `argoexec` from quay.io, pinned by digest in the manifest and in the controller's `--executor-image`. Before a digest is pinned, its cosign signature is checked on the workstation against the public key from the release. quay.io and the hosts its downloads redirect to go on the fetch list, read from Squid's log during a window, as the list's comment says. The orchestrator pulls them during a fetch window.

**The manifests.** Upstream's file, kept as released, plus a patch that adds `seccompProfile: RuntimeDefault` to each pod, the two flags, and the digests. A check compares the controller's running image and arguments with the repository, as `T.2` does for the tool service. Workflow templates are applied from the repository. A check compares the live template with the file.

## Trade-offs

- **The controller can still reach the dispatch key.** It creates pods in `orchestration`, so it can create one that mounts the key. A compromised controller image is a compromised dispatch. The digest and the signature check are the control, and the controller holds nothing the orchestrator's root does not.
- **No UI unless the operator runs it.** Nobody else can look at a run, and a run that nobody watches leaves only its workflow object and the logs. That suits one operator. A team would want the server in the cluster.
- **The copied Role has to be read again at each version.** Upstream changes its Role in `argo`, not the copy in `orchestration`.
- **A 12-hour token on the workstation can start jobs on the worker.** Only through the templates, with their arguments. That is less than the SSH certificate beside it, which is root on the orchestrator.
- **The executor's token does not expire.** Argo mounts it from a secret, and a token Kubernetes writes into a secret is long-lived. Argo v4.1.5 has no setting for a projected one. The token holds the Role above and nothing more, no Role in the cluster reads secrets, and deleting the secret ends it.
- **The executor's token can patch any task result in `orchestration`.** A compromised dispatch pod could change another workflow's recorded output. The result is untrusted input either way ([0012](0012-dispatch-over-ssh-with-a-forced-command.md)), and one job runs at a time.
- **quay.io's download hosts are open during a fetch window.** They are object stores, which [T40](../security/threat-model.md) already treats as an upload path while a window is open.
