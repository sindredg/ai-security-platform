# 04. The first deployment fails on a default service account that already exists

Date: 2026-10-15
Milestone: 3, toolchain integration

## Symptom

The first run of `platform/tool-service/deploy.sh` on the cluster stopped after four lines:

```text
namespace/tool-services created
namespace/orchestration created
serviceaccount/default created
serviceaccount/dispatch created
Error from server (AlreadyExists): error when creating ".../namespaces.yaml": serviceaccounts "default" already exists
```

The account in `tool-services` was created, the one in `orchestration` was not. A second run went through, with a warning that `orchestration/default` had no `last-applied-configuration` annotation.

## Cause

Confirmed. Kubernetes creates a `default` service account in every new namespace on its own, moments after the namespace. `namespaces.yaml` held both namespaces and their `default` accounts, each with `automountServiceAccountToken: false`, in one `kubectl apply`. Client-side apply asks whether an object exists and then creates it. In `orchestration`, the namespace controller created the account between the two steps.

The account's managed fields after the failed run showed it: `tool-services/default` and `orchestration/dispatch` were managed by `kubectl-client-side-apply`, `orchestration/default` by nothing of ours, with `automountServiceAccountToken` unset. Until the second run, a pod in `orchestration` without its own setting would have mounted a token. No pod ran there.

The race is timing. Which namespace loses, or whether one does, changes from run to run.

## Fix

The accounts moved to `platform/tool-service/service-accounts.yaml`. `deploy.sh` applies the namespaces, waits for each `default` account, and then applies the accounts on top:

```bash
k apply -f "$here/namespaces.yaml"
for ns in tool-services orchestration; do
  k wait --for=create serviceaccount/default -n "$ns" --timeout=60s
done
k apply -f "$here/service-accounts.yaml"
```

The `last-applied-configuration` warning now shows on every fresh deployment. It is expected: the apply always lands on an account Kubernetes created.

## Verification

On the live system, 2026-10-15. Three rounds of deleting both namespaces and running the fixed `deploy.sh`:

| Round | `default` accounts waited for | `AlreadyExists` | `automountServiceAccountToken` on both `default` accounts | Rollout |
| --- | --- | --- | --- | --- |
| 1 | 2 of 2 | None | `false`, `false` | Pinned digest |
| 2 | 2 of 2 | None | `false`, `false` | Pinned digest |
| 3 | 2 of 2 | None | `false`, `false` | Pinned digest |

## Limits

Three clean runs do not prove the race is gone, because the old order also succeeded some of the time. The order does: the apply runs only after the account exists, so it updates and never creates.
