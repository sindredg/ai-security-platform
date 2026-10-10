# Decision records

One record per consequential architecture choice. A record states the context, the options considered, the decision, and its trade-offs. Records are not edited after acceptance except to mark them superseded. A changed decision gets a new record.

| Record | Decision | Status |
| --- | --- | --- |
| [0001](0001-k3s-for-initial-orchestration.md) | K3s on one VM for initial orchestration | Accepted |
| [0002](0002-separate-platform-and-target-infrastructure.md) | Separate platform and target infrastructure | Accepted |
| [0003](0003-region-pair.md) | Sweden Central for the platform, Denmark East for targets | Accepted |
| [0004](0004-netbox-as-first-target.md) | NetBox as the first target, three ordered exercises | Accepted |
| [0005](0005-ai-workers-on-a-separate-vm.md) | AI workers on a separate VM outside the cluster | Accepted |

## Format

```text
# NNNN. Title

Status: Proposed | Accepted | Superseded by NNNN
Date: YYYY-MM-DD

## Context
## Options
## Decision
## Trade-offs
```
