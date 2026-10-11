# Lab against production

The controls are meant to hold up in production. The lab around them is not production, and each gap below is a choice made for capacity or cost.

| Lab choice | Why it is acceptable here | Production would use |
| --- | --- | --- |
| Mesh VPN with a third-party coordination service | No public address, no operator address in a rule, one agent | A self-hosted control plane, or a VPN gateway or private circuit with a bastion. Node signing at the least |
| One person writes, approves, and operates | There is one person | A separate approver, required human review, and time-limited privileged roles |
| One Azure account owns both sides | One subscription | A subscription per side, under separate administrators |
| Deployment keys on a workstation | Terraform runs there | Workload identity federation from a controlled runner, with no long-lived key |
| One K3s node, one VM per role | A quota of 4 vCPUs per region | A highly available control plane across zones |
| Orchestrator egress open on port 443 | Hostname filtering costs as much as the four VMs | A firewall or proxy with a hostname allowlist |
| Worker isolation is one VM shared by consecutive jobs | No capacity for more | A fresh sandbox per job |
| The audit log sits on the orchestrator | No second trusted machine | An append-only store outside the platform |
| Public repository, synthetic data | Nothing in it is real | A private repository, classified data, and strict control over what a pull request may contain. A5 becomes the main risk |
| Locally redundant state, local bootstrap state | The lab can be rebuilt from the runbooks | Geo-redundant remote state, with tested recovery |
