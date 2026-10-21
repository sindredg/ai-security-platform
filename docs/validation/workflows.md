# Workflows

Argo Workflows' controller in its own namespace, managing `orchestration` only, and the template that dispatches a job to the worker ([ADR 0029](../decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md), [ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)). The procedure is the [workflows runbook](../runbooks/workflows.md).

Status: **tested** on the live system on 2026-10-21. `W.1` to `W.10` failed on absence before the install, on 2026-10-20, and passed at 04:24 UTC after it. `W.11` failed on absence before its secret existed and passed at 15:26 UTC, and its parser gives another value for a secret with no token, another type, or another account ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)).

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `W.1` | The Argo controller is ready | No workflow runs without it | The deployment's ready replicas are `1` |
| `W.2` | The Argo controller runs the image `argo.yaml` names | The controller creates pods in `orchestration` and can mount the dispatch key (T50). It has to be the signed release | The running pod's image ID, the digest containerd pulled, equals the digest in `platform/argo/argo.yaml` |
| `W.3` | The Argo controller manages `orchestration` only, with the pinned executor | Without `--managed-namespace` the controller watches its own namespace. The executor image runs in every workflow pod | The deployment's arguments, as JSON, equal `--namespaced --managed-namespace orchestration --executor-image` and the executor digest from `argo.yaml` |
| `W.4` | The Argo controller runs only workflows that reference a template | Without it, the right to create a workflow is the right to run any pod in `orchestration` (T45, T51) | `workflowRestrictions` in the controller's configuration is `templateReferencing: Secure` |
| `W.5` | The controller's Role in `orchestration` is a copy of its own | The copy is maintained by hand. A copy with more than upstream's Role is a widening nobody reviewed | The rules of `argo-role` in `argo` and in `orchestration` are one distinct line |
| `W.6` | The executor may only record task results | The executor's token is mounted in every workflow pod, the dispatch pod included | The rules of the `argo-executor` Role equal `create` and `patch` on `workflowtaskresults` |
| `W.7` | No Argo server runs in the cluster | The server is a web application with access to secrets in its namespace. The UI runs on the workstation instead | No deployment in any namespace has `argo-server` in its name |
| `W.8` | The `argo` namespace is restricted and denies by default | The controller's pod has a token for the API server | The namespace's pod security label is `restricted`, and `default-deny` exists |
| `W.9` | The workflow template is the one in this checkout | The template decides the image, the account, the volumes, and the deadline of every job (T51) | One SHA-256 over the live template's spec as `kubectl` prints it, JSON with sorted keys, equal to the same over `workflow-template.yaml`'s spec. Needs Python's `yaml` module on the workstation |
| `W.10` | The dispatch secret pins this worker's host key | A wrong or missing host key makes every dispatch fail, or trust a machine that is not the worker | The secret has exactly `id_ed25519` and `known_hosts`, and `known_hosts` is `10.40.0.36` with the host key the worker's own file holds. Read in the orchestrator's section and the worker's |
| `W.11` | The executor's token secret is for `argo-executor` and holds a token | Without it, every workflow pod waits on the mount and no step starts ([troubleshooting](../troubleshooting/14-workflow-pods-wait-for-the-executors-token.md)) | The secret `argo-executor.service-account-token` in `orchestration`: its type `kubernetes.io/service-account-token`, its account annotation `argo-executor`, and a token that is not empty. The token itself is not printed |

## Limits

- **`W.9` compares what the API server gives back.** If the server adds defaults to the stored spec, `W.9` fails on a correct template. It passed on its first run on the cluster, on 2026-10-21, so the server added none to this template. A change to Argo's defaults can still break it.
- **`W.2` reads the digest containerd used.** The images are pulled by the digest of their multi-platform index, and the pod's image ID showed that digest on the cluster on 2026-10-21.
- **Argo's offline linter does not check parameter references.** In the pipeline it fails on an unknown field and on a template that names a missing one, both seen on 2026-10-20. A misspelled `{{workflow.parameters...}}` passes it.
- **`W.11` reads that the secret holds a token, not that the token works.** A workflow that starts shows that.
- **No check reads what a workflow did.** The round trip, the cancel, and the refused submissions are procedure steps in the [runbook](../runbooks/workflows.md), because they start jobs.
