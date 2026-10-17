# 0027. How the monitoring is built: two collection endpoints, logins at info, and hosts entries through the VM agent

Status: Proposed
Date: 2026-10-17

Changes three parts of [0021](0021-monitoring-in-azure-monitor-over-private-link.md), found while building it.

## Context

[0021](0021-monitoring-in-azure-monitor-over-private-link.md) decided Azure Monitor over Private Link, with one data collection endpoint, syslog at warning and above, and hosts entries for the private endpoint's names, "from Terraform". Three of those do not hold as written.

- **One endpoint is not enough.** A data collection endpoint has three parts. The configuration part, where an agent fetches its rules, has to be in the agent's own region. The ingestion part has to be in the workspace's region ([data collection endpoints](https://learn.microsoft.com/azure/azure-monitor/data-collection/data-collection-endpoint-overview), read 2026-10-17). The orchestrator is in Sweden Central with the workspace. The edge and the router are in Denmark East.
- **Warning and above misses the logins.** 0021 has an alert for every accepted SSH login. sshd logs an accepted login at `info` on `auth`, so a rule that keeps warning and above never sees one. The fetch window logs its opens through `logger`, which writes `user.notice`, and 0021 names no `user` facility.
- **"From Terraform" needs a way onto the VMs.** Custom data runs at first boot only, and the three VMs are running. Terraform learns the endpoint's names and addresses only when it creates the endpoint. Writing them over SSH puts a manual step between the apply and the agent working, on three machines, after every change to the endpoint.

## Options

For the endpoints:

| Option | Problem |
| --- | --- |
| One endpoint in Sweden Central for all three agents | Not supported for configuration access from another region |
| One endpoint per region, both in the scope | One more resource in the scope. None |
| Move the workspace to Denmark East | Moves the record next to two of the machines it describes and away from the orchestrator, the one that matters most |

For the hosts entries:

| Option | Cost |
| --- | --- |
| A script the operator runs over SSH after each apply | A manual step that drifts. The checks would catch it, after the fact |
| Managed run command, a Terraform resource that runs a script through the VM agent | The VM agent runs a root script that Terraform sends. The platform identity can already do that, as Contributor on the VMs. One more extension handler on each VM |
| A private DNS zone after all | Rejected in 0021: the orchestrator would need Azure DNS |

## Decision

- **Two data collection endpoints**, `platform` in Sweden Central and `edge` in Denmark East, both in the Private Link Scope with public access off. Each agent fetches its rules from the one in its region. Every rule sends through the `platform` one.
- **Syslog facilities:** `auth` and `authpriv` from `info`, `user` from `notice`, and `kern` and `daemon` from `warning`, on all three VMs.
- **Hosts entries through managed run command.** Terraform builds the entry list from the private endpoint's own record of its names and addresses, and runs `platform/monitoring/aisec-monitor-hosts` on each monitored VM. The script refuses any line that is not an address in `10.40.0.64/27` and an Azure Monitor name, and replaces only the block between its two marker lines. A change to the list runs it again. Checks `O.5` to `O.7` compare each VM's block with the endpoint's record.

Two settings that 0021 did not name, and that follow from it:

- **The workspace takes no shared key** (`local_authentication_enabled = false`). Every writer and reader is an Entra identity, and the VMs' identities hold no role.
- **Each copied line is stored as it is**, in a `RawData` column, one row per line, with no parsing at ingestion. Queries parse it. A parse at ingestion would drop a line it cannot read, and the marker lines are the ones that matter most.

## Trade-offs

- **More login volume.** `auth` at `info` takes every SSH session's open and close, on three machines. Small next to Squid's log, and part of the week the cap is measured on.
- **The VM agent runs a script as root, sent by Terraform.** That was already true of anyone with Contributor on the VMs. The script is in the repository, linted in the pipeline, and refuses entries outside the monitoring subnet.
- **Whether the run command and the agent install without the internet is not known.** Both come through the VM agent and `168.63.129.16`. The first apply settles it. If either needs the internet, that is another record.
- **Queries carry the parsing.** Every alert rule parses `RawData`. A changed line format breaks a rule, not the ingestion, and the check for marker lines still finds the raw text.
- **Two endpoints in the scope instead of one.** Each is one more name in the hosts entries. Nothing else changes.
