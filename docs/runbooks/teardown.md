# Teardown: operator procedure

Status: Ran on 2026-11-02 ([worklog](../worklogs/0009-exercise-2-excess-network-access.md#the-teardown)). Steps 1 and 2 on 2026-11-01. Steps 3 to 8 and 10 from 06:58 to 07:23 UTC, from scripts with the same commands, each apply from a plan read first. Step 9 by hand in the console, not read back by a command.

This removes everything the three Terraform roots made, in the order their dependencies allow: the targets, then the platform, then the bootstrap root that holds the resource groups, the state accounts, and both deployment identities. The repositories, their records, and the evidence stay. Run it only when nothing more needs the live system.

Three things in the subscription stay on purpose. `NetworkWatcherRG` is Azure's own, made per region and shared. The resource providers `Microsoft.Insights` and `Microsoft.OperationalInsights` stay registered, because other workloads in the subscription can use them. `Microsoft.PolicyInsights` was registered outside Terraform ([#133](https://github.com/sindredg/ai-security-platform/issues/133)).

## Inputs and access

| Input | Notes |
| --- | --- |
| The operator's Azure session | `az login`, as the account that applied the bootstrap root |
| `REPLACE_WITH_CRED_DIR` | `platform.env` and `targets.env`, the two deployment identities |
| A checkout of this repository and of the targets repository | `REPLACE_WITH_PLATFORM_CHECKOUT` and `REPLACE_WITH_TARGETS_CHECKOUT`, each on `main`. Steps 2 and 3 run from the platform checkout's root |
| `REPLACE_WITH_KEEP` | A directory outside both repositories, for the state copies |
| A certificate signed today | For step 1 only |
| Mesh VPN admin console | To remove the router's node in step 9 |

## Before the destroy

1. Make sure no workflow runs, and that every job of the last 24 hours has its record ([test evidence runbook](test-evidence.md)).

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration get workflows --no-headers'
   ```

   Expected: no line with `Running`, and a record under `docs/evidence/records/` for each workflow listed.

2. Keep a copy of each state.

   ```bash
   (source REPLACE_WITH_CRED_DIR/platform.env && terraform -chdir=infra/platform state pull > REPLACE_WITH_KEEP/platform.tfstate)
   (source REPLACE_WITH_CRED_DIR/targets.env && terraform -chdir=REPLACE_WITH_TARGETS_CHECKOUT/infra/targets state pull > REPLACE_WITH_KEEP/targets.tfstate)
   cp infra/bootstrap/terraform.tfstate REPLACE_WITH_KEEP/bootstrap.tfstate
   ls -l REPLACE_WITH_KEEP
   ```

   Expected: three files, none empty. They hold identifiers and no key.

## The destroy

3. Destroy the flow logs first, from the bootstrap root, while the networks they watch and the workspace they write to still exist.

   ```bash
   cd infra/bootstrap
   terraform plan -destroy -target='azurerm_network_watcher_flow_log.this' -out=REPLACE_WITH_KEEP/flow-logs-destroy.tfplan
   terraform apply REPLACE_WITH_KEEP/flow-logs-destroy.tfplan
   ```

   Expected: `2 to destroy`, both flow logs, and a warning that the plan is targeted. The apply ends with `Apply complete! Resources: 0 added, 0 changed, 2 destroyed.`

4. Destroy the targets root. It owns its own side of each peering: from the targets network to the platform and edge networks. The platform root owns the other sides.

   ```bash
   cd REPLACE_WITH_TARGETS_CHECKOUT/infra/targets
   source REPLACE_WITH_CRED_DIR/targets.env
   terraform plan -destroy -out=REPLACE_WITH_KEEP/targets-destroy.tfplan
   terraform apply REPLACE_WITH_KEEP/targets-destroy.tfplan
   ```

   Expected: `20 to destroy`, every resource in `rg-aisec-targets` and its two peerings. The plan names `rg-aisec-platform` only as the peerings' remote networks. Read the plan before the apply.

5. Destroy the platform root.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform
   source REPLACE_WITH_CRED_DIR/platform.env
   terraform plan -destroy -out=REPLACE_WITH_KEEP/platform-destroy.tfplan
   terraform apply REPLACE_WITH_KEEP/platform-destroy.tfplan
   ```

   Expected: `79 to destroy`, every resource in `rg-aisec-platform`, the four VMs (orchestrator, worker, edge, router), the workspace, and the platform and edge networks' four peerings among them. The two target VMs went with step 4. The workspace stays recoverable for 14 days after its delete, as Azure keeps it.

6. Prepare the bootstrap root's destroy on the working tree, without a commit. Step 8 puts the files back. Remove the `lifecycle { prevent_destroy = true }` block from the state accounts in `infra/bootstrap/main.tf`. Remove the two `data` blocks and the `azurerm_network_watcher_flow_log` block from `infra/bootstrap/monitoring.tf`: step 3 destroyed the flow logs, and the data sources would read a workspace and networks that no longer exist. Then take the provider registrations out of the state, so the destroy leaves them registered.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/bootstrap
   terraform state rm 'azurerm_resource_provider_registration.this'
   ```

   Expected: `Removed 2 resource instances`.

7. Delete what traffic analytics made, then destroy the bootstrap root as the operator. Traffic analytics makes a data collection rule and endpoint per flow log in the workspace's group, named `NWTA-...`, and Terraform does not manage them. The provider refuses by default to delete a group that still holds resources; that refusal was not seen, because the four were deleted first.

   ```bash
   for type in dataCollectionRules dataCollectionEndpoints; do
     ids=$(az resource list -g rg-aisec-platform --resource-type "Microsoft.Insights/$type" \
       --query "[?starts_with(name, 'NWTA-')].id" -o tsv)
     for id in $ids; do az resource delete --ids "$id"; done
   done
   az resource list -g rg-aisec-platform --query "[].name" -o tsv
   unset ARM_CLIENT_ID ARM_CLIENT_CERTIFICATE_PATH ARM_CLIENT_CERTIFICATE_PASSWORD ARM_TENANT_ID
   terraform plan -destroy -out=REPLACE_WITH_KEEP/bootstrap-destroy.tfplan
   terraform apply REPLACE_WITH_KEEP/bootstrap-destroy.tfplan
   ```

   Expected: no name from `az resource list`, then `34 to destroy`: the four resource groups, the state and flow log accounts, both deployment identities with their certificates, the policy assignments, the custom peering role, the role assignments, and the Activity Log alerts, and no provider registration. Read the plan first: an identity running it would fail on the Entra objects. The custom role's delete alone took more than seven minutes.

## After the destroy

8. Read what is left.

   ```bash
   az group list --query "[?starts_with(name, 'rg-aisec')].name" -o tsv
   az ad app list --display-name aisec --query "[].displayName" -o tsv
   az role definition list --custom-role-only true --query "[?contains(roleName, 'aisec')].roleName" -o tsv
   git -C REPLACE_WITH_PLATFORM_CHECKOUT checkout -- infra/bootstrap
   ```

   Expected: three empty answers, and no change under `infra/bootstrap`.

9. Remove `aisec-router` in the mesh VPN admin console, and the router's tag and grants from the access policy.

   Expected: no `aisec` node in the console.

10. Delete the two deployment identities' certificate files and env files from `REPLACE_WITH_CRED_DIR`, and the bootstrap root's local `terraform.tfstate`, which step 2 copied.

    Expected: the credential directory holds no key of a deleted identity.

11. Say on the living pages that the system no longer runs, and link this runbook's result: the README's status table, the roadmap, and the [project close](../close.md).

    Expected: no page says the system runs.
