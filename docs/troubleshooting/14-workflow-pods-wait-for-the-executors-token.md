# 14. Workflow pods wait for the executor's token

Date: 2026-10-21
Milestone: 3, toolchain integration

## Symptom

The first workflow from the template, `investigate-2llvm`, submitted at 14:12 UTC in step 10 of the [workflows runbook](../runbooks/workflows.md#the-round-trip), never started a container. Its pod stayed in `Init`, and after the step's 780-second deadline the dispatch node failed with `Pod was active on the node longer than the specified deadline`. The exit handler's pod then waited the same way, so the workflow stayed `Running` and held the lock. The events of both pods repeated:

```text
MountVolume.SetUp failed for volume "exec-sa-token" : secret "argo-executor.service-account-token" not found
```

No job reached the worker: the dispatch container never ran.

## Cause

Confirmed from the events and Argo's source at v4.1.5. The template sets `automountServiceAccountToken: false` and names `argo-executor` as the executor's account. In that case the controller adds a secret volume for the executor's token to every workflow pod, named `<account>.service-account-token` unless the account names another (`workflow/controller/workflowpod.go`, and Argo's page on service account secrets). Kubernetes stopped making such secrets in 1.24, and nothing in `platform/argo` made one.

Nothing showed it before the first submission. The checks read the controller and the objects, not a pod built from the template, and Argo's offline linter does not build pods.

## Fix

`rbac.yaml` adds the secret, of type `kubernetes.io/service-account-token` with the account annotation `argo-executor`, which the cluster fills with a long-lived token. The token's rights are the Role's, `create` and `patch` on task results, and it does not expire ([ADR 0029](../decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md)). `W.11` checks the secret's type, account, and that it holds a token. It fails on the cluster without the secret.

## Verification

Not yet run: the install of the secret and a workflow that starts.
