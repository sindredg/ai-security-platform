# 0048. The workflow's steps are inline, so no workflow runs one alone

Status: Accepted
Date: 2026-10-27

## Context

A NetBox job runs two steps: dispatch, then the comparison ([0041](0041-the-workflow-compares-the-models-verdict-with-the-checks.md)). Milestone 5 acts on a match: `propose-netbox-fix` proposes the fix of a job whose comparison matched ([0043](0043-proposals-are-remove-only-and-a-policy-check-decides.md)).

What is fixed already:

- **A workflow from the template can set its own entrypoint and arguments.** Argo Workflows v4.1.6 allows both next to `workflowTemplateRef`, also under `templateReferencing: Secure` ([0029](0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md)). Its setting for overrides can only add fields to that list, not take one away.
- **Both steps were templates of their own.** A workflow that named `dispatch` ran the model and ended Succeeded with no comparison. One that named `compare` matched an answer the submitter wrote, with no model run, as seen on the live system ([#203](https://github.com/sindredg/ai-security-platform/issues/203)).
- **Only the holder of the operator's Argo token submits a workflow** (T45 in the [threat model](../security/threat-model.md)).

## Options

| Option | What stops a skipped comparison | What it costs |
| --- | --- | --- |
| Refuse at the proposal only | `propose-netbox-fix` checks the entrypoint | A workflow still ends Succeeded with no comparison. Each later reader of an outcome has to check too |
| A parameter that only `investigate` passes to its steps | Nothing: the submitter sets the arguments | None, and no protection |
| Inline steps | Argo's validation at submission: there is no template by that name | A node no longer carries a template name |

## Decision

**`dispatch` and `compare` are inline steps of `investigate`.** A workflow can name only `investigate` and the exit handler as its entrypoint. Argo refuses any other name at submission, as a template it cannot find.

**The proposal command keeps its own check.** It refuses a workflow from another entrypoint, and reads the comparison only from the node whose display name is `compare`. The display name is the step's name in the template.

**A pipeline check lints one workflow per entrypoint** against the template with Argo's own linter, offline. `investigate` has to pass, and `dispatch` and `compare` have to fail as templates Argo cannot find.

## Trade-offs

- **The exit handler can still be named.** Run alone, it revokes the token of the job with the workflow's own name. While a workflow by that name exists, no second one can be made, so it reaches only a job whose workflow is gone.
- **`target` stays an argument.** A workflow under a NetBox job's name can set it to `synthetic`, which has no comparison by design. It then investigates the synthetic target, and the proposal command finds no comparison.
- **Nodes have no template name.** Anything that read it reads the display name.
- **Not seen when this was written:** the controller refusing such a workflow on the live system. The linter runs the validation the controller runs at submission.
