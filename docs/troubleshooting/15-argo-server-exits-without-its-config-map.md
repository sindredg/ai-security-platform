# 15. Argo's server exits without its config map

Date: 2026-10-21
Milestone: 3, toolchain integration

## Symptom

Step 14 of the [workflows runbook](../runbooks/workflows.md#the-ui) started `argo server` on the workstation in local mode, with the operator's kubeconfig. Nothing answered on port 2746, and the server logged:

```text
level=ERROR msg="configmaps \"workflow-controller-configmap\" is forbidden: User \"system:serviceaccount:orchestration:argo-operator\" cannot get resource \"configmaps\" in API group \"\" in the namespace \"orchestration\""
```

## Cause

Confirmed from Argo's source at v4.1.5. When the server runs, it reads a config map in its namespace, named by `--configmap` and `workflow-controller-configmap` by default, and exits on any error, not found included (`Run` in `server/apiserver/argoserver.go`). In local mode the server's namespace is the kubeconfig's, `orchestration`, and its rights are the operator's. The operator's Role reads no config map, and no such map exists there: the controller's is in `argo`.

## Fix

An empty config map `argo-ui` in `orchestration`, a rule in the operator's Role that allows `get` on that one map by name, and `--configmap argo-ui` on the server's command line. Empty means Argo's defaults.

## Verification

Not yet run.
