# Network foundation: operator procedure

Status: Implemented and validated on 2026-10-10. Built once, from an empty subscription. A second build from scratch has not been run. Results are in the [milestone 1 worklog](../worklogs/0001-network-foundation.md).

The state upload in step 5 was added and run on 2026-10-11. Key handling in steps 3 and 12 and in the rotation changed on 2026-10-11, to keep one key file per side. Checked that day: key generation with throwaway keys, and the sign-in from a temporary PEM for both identities. The rest of step 12 was not repeated.

Run these steps to build or revalidate milestone 1: state storage, deployment identities, both virtual networks, their security groups, and the peering. Never commit local values, plans, state, keys, or raw output.

## Inputs and access

| Input | Notes |
| --- | --- |
| An Azure subscription | The operator needs Owner on it, to create resource groups, a custom role, and role assignments |
| A Microsoft Entra tenant | The operator must be allowed to create app registrations |
| `terraform` 1.16.6 | The roots refuse any other version |
| `az` 2.88 or later, `openssl` 3, `jq` | Sign-in, checks, key generation, and reading Terraform outputs |
| A private directory outside the repository, on an encrypted disk | Holds two private keys. Called `$CRED_DIR` below |

The design is in the [architecture](../architecture.md). The reasons for the identity setup are in [ADR 0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md).

What this builds costs close to nothing while idle: two storage accounts holding a few kilobytes, and a peering that bills per gigabyte carried.

Three identities appear below. Keep track of which one a shell is using.

| Identity | Used for | How it signs in |
| --- | --- | --- |
| Operator | Steps 1 to 5, and the read-only checks | `az login` |
| Platform deployment identity | `infra/platform` | Certificate, through `platform.env` |
| Target deployment identity | `infra/targets` | Certificate, through `targets.env` |

## Prepare the subscription

1. Sign in as the operator and select the subscription.

   ```bash
   az login
   az account set --subscription 'REPLACE_WITH_SUBSCRIPTION_ID'
   export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
   az account show --query "{state:state, user:user.type}"
   ```

   Expected: state `Enabled`, user type `user`.

2. Register the two resource providers this milestone uses. The provider no longer registers anything by default, and the deployment identities are not allowed to.

   ```bash
   az provider register -n Microsoft.Network --wait
   az provider register -n Microsoft.Storage --wait
   az provider list --query "[?namespace=='Microsoft.Network' || namespace=='Microsoft.Storage'].{ns:namespace, state:registrationState}" -o table
   ```

   Expected: both `Registered`. Each command blocks until it finishes, usually one to five minutes.

## Create the deployment keys

3. Generate one key pair per side. The private keys stay in `$CRED_DIR`. Only the `.crt` files go to Microsoft Entra ID.

   ```bash
   umask 077
   export CRED_DIR='REPLACE_WITH_PRIVATE_DIRECTORY'
   mkdir -p -m 700 "$CRED_DIR"
   for side in platform targets; do
     openssl req -x509 -newkey rsa:4096 -sha256 -days 91 -noenc \
       -subj "/CN=aisec-$side-deploy" \
       -keyout "$CRED_DIR/$side.key" -out "$CRED_DIR/$side.crt"
     openssl pkcs12 -export -passout pass: \
       -inkey "$CRED_DIR/$side.key" -in "$CRED_DIR/$side.crt" -out "$CRED_DIR/$side.pfx"
     rm "${CRED_DIR:?}/${side:?}.key"
   done
   ls -l "$CRED_DIR"
   ```

   Expected: four files, all mode `-rw-------`: a `.crt` and a `.pfx` per side. Terraform reads the `.pfx`, and it is the only copy of the private key.

   The `.pfx` has no password. File permissions are the only protection, so pick a directory on an encrypted disk.

## Apply the bootstrap root

4. Fill in the bootstrap variables. Each side has its own end date: when Microsoft Entra ID stops accepting that side's certificate. It has to fall inside the certificate's 91 days, so run this step on the same day as step 3.

   ```bash
   cd infra/bootstrap
   cp terraform.tfvars.example terraform.tfvars
   chmod 600 terraform.tfvars
   date -u -d '+90 days' +%Y-%m-%dT00:00:00Z
   # Edit terraform.tfvars: set both certificate paths and paste the timestamp into both end dates.
   ```

   Expected: `terraform.tfvars` names the two `.crt` files and two end dates. Git ignores it.

5. Plan and apply as the operator. This root keeps its state in a local file.

   ```bash
   terraform init
   terraform plan -out=bootstrap.tfplan
   terraform apply bootstrap.tfplan
   terraform plan -detailed-exitcode
   ```

   Expected: the plan adds 23 resources: four resource groups, two storage accounts with one container each, two random suffixes, two app registrations with a service principal and a certificate each, one custom role, and six role assignments. The apply ends with `Resources: 23 added`. The last plan reports no changes and exits `0`.

   `terraform.tfstate` now exists in this directory. It holds no keys, but it is the record of what this root owns. Upload a copy after every apply of this root:

   ```bash
   az storage blob upload --auth-mode login \
     --account-name "$(terraform output -json state_storage_accounts | jq -r .platform)" \
     -c bootstrap -n terraform.tfstate -f terraform.tfstate --overwrite
   openssl md5 -binary terraform.tfstate | base64
   ```

   Expected: the `content_md5` in the answer equals the checksum printed by the last command. A permission error right after the apply means the role assignment has not spread yet. Wait a minute and repeat.

   The root has grown since the count above was taken: three policy assignments in milestone 2, and the container and role for this copy. The state holds 28 resources now, so a build from the current code plans 28, which has not been run from an empty subscription.

6. Write the local files the other two roots need. None of them is tracked.

   ```bash
   for side in platform targets; do
     cat > "$CRED_DIR/$side.env" <<EOT
   export ARM_SUBSCRIPTION_ID="$ARM_SUBSCRIPTION_ID"
   export ARM_TENANT_ID="$(terraform output -raw tenant_id)"
   export ARM_CLIENT_ID="$(terraform output -json deploy_client_ids | jq -r ".$side")"
   export ARM_CLIENT_CERTIFICATE_PATH="$CRED_DIR/$side.pfx"
   EOT
     printf 'storage_account_name = "%s"\n' \
       "$(terraform output -json state_storage_accounts | jq -r ".$side")" > "../$side/backend.hcl"
   done
   chmod 600 "$CRED_DIR"/*.env ../platform/backend.hcl ../targets/backend.hcl
   ```

   Expected: `platform.env` and `targets.env` in `$CRED_DIR`, and a `backend.hcl` in each of `infra/platform` and `infra/targets`.

## Apply the networks

The link takes three applies. Each side owns its own half of the peering, and a half cannot be created before the network it points at exists.

Use a fresh shell for each root, or source the right file again before every command. A shell that still has the other side's variables set fails with an authorization error, which is the boundary working.

A fresh shell has no `CRED_DIR`. Export it again, as in step 3, before sourcing anything.

7. Apply the platform root without the peering.

   ```bash
   cd ../platform
   source "$CRED_DIR/platform.env"
   terraform init -backend-config=backend.hcl
   terraform plan -out=platform.tfplan
   terraform apply platform.tfplan
   ```

   Expected: `Successfully configured the backend "azurerm"`, then a plan that adds 7 resources: one virtual network, two subnets, two security groups, and two associations. If the plan fails with `AuthorizationFailed` right after step 5, wait a minute for the role assignments to propagate and plan again.

8. Apply the target root, peering included.

   ```bash
   cd ../targets
   source "$CRED_DIR/targets.env"
   printf 'platform_virtual_network_id = "%s"\n' \
     "$(az network vnet show -g rg-aisec-platform -n vnet-aisec-platform --query id -o tsv)" > terraform.tfvars
   chmod 600 terraform.tfvars
   terraform init -backend-config=backend.hcl
   terraform plan -out=targets.tfplan
   terraform apply targets.tfplan
   ```

   Expected: the plan adds 14 resources: one virtual network, four subnets, four security groups, four associations, and one peering. The `az` command runs as the operator, because the target identity cannot read the platform network.

9. Apply the platform root again, now with its half of the peering.

   ```bash
   cd ../platform
   source "$CRED_DIR/platform.env"
   printf 'targets_virtual_network_id = "%s"\n' \
     "$(az network vnet show -g rg-aisec-targets -n vnet-aisec-targets --query id -o tsv)" > terraform.tfvars
   chmod 600 terraform.tfvars
   terraform plan -out=platform.tfplan
   terraform apply platform.tfplan
   ```

   Expected: the plan adds exactly 1 resource, the peering. Anything else in that plan is drift. Stop and read it.

## Check the milestone 1 gate

10. Confirm that every root has converged.

    ```bash
    (cd ../platform && source "$CRED_DIR/platform.env" && terraform plan -detailed-exitcode)
    (cd ../targets && source "$CRED_DIR/targets.env" && terraform plan -detailed-exitcode)
    (cd ../bootstrap && terraform plan -detailed-exitcode)
    ```

    Expected: `No changes` and exit `0` three times. Exit `2` means drift or a pending change. Exit `1` means an error.

11. Confirm the peering, the subnets, and the rules. Run as the operator.

    ```bash
    for side in platform targets; do
      az network vnet peering list -g "rg-aisec-$side" --vnet-name "vnet-aisec-$side" \
        --query "[].{name:name, state:peeringState, sync:peeringSyncLevel, forwarded:allowForwardedTraffic}" -o table
      az network vnet subnet list -g "rg-aisec-$side" --vnet-name "vnet-aisec-$side" \
        --query "[].{subnet:name, prefix:addressPrefix || addressPrefixes[0], nsg:networkSecurityGroup.id, defaultOutbound:defaultOutboundAccess}" -o table
    done
    az network nsg list --query "[].[resourceGroup,name]" -o tsv | while read -r rg nsg; do
      echo "== $nsg"
      az network nsg show -g "$rg" -n "$nsg" \
        --query "sort_by(securityRules,&priority)[].[priority,direction,access,protocol,sourceAddressPrefix,destinationAddressPrefix,destinationPortRange,name]" -o tsv
    done
    az network public-ip list --query "length(@)"
    ```

    Expected:

    - Both peerings `Connected` and `FullyInSync`, with forwarded traffic `False`.
    - Six subnets, each with its own security group and default outbound access `False`.
    - Every security group ends with `deny-all-inbound` and `deny-all-outbound` at priority 4096.
    - The only `Allow` rules are TCP 22 from `10.40.0.0/27`: outbound on the orchestrator group, inbound on the other five.
    - The worker group denies outbound to `10.50.0.0/20` and to `Internet` at priorities 100 and 110. Both platform groups deny inbound from `10.50.0.0/20` at priority 100.
    - Zero public IP addresses.

    This reads the configured rules. The effective rules on a network interface cannot be read until a VM exists, so that check belongs to milestone 2.

12. Confirm that neither identity can touch the other side. Each block signs in as one identity in a throwaway CLI profile, so the operator's sign-in is left alone. Every command marked `denied` is supposed to fail.

    ```bash
    export TENANT_ID="$(az account show --query tenantId -o tsv)"
    check() {
      side="$1"; other="$2"
      export AZURE_CONFIG_DIR="$(mktemp -d)"
      pem="$(mktemp -p /dev/shm)"
      ( source "$CRED_DIR/$side.env"
        openssl pkcs12 -in "$CRED_DIR/$side.pfx" -passin pass: -noenc -out "$pem"
        az login --service-principal -u "$ARM_CLIENT_ID" --certificate "$pem" --tenant "$TENANT_ID" -o none
        own_state="$(cut -d'"' -f2 "../$side/backend.hcl")"; other_state="$(cut -d'"' -f2 "../$other/backend.hcl")"
        az network vnet show -g "rg-aisec-$side" -n "vnet-aisec-$side" -o none                                  # allowed
        az storage blob list --account-name "$own_state" -c tfstate --auth-mode login -o none                 # allowed
        az network vnet show -g "rg-aisec-$other" -n "vnet-aisec-$other" -o none                                # denied
        az network nsg create -g "rg-aisec-$other" -n nsg-probe -l swedencentral -o none                       # denied
        az network vnet peering delete -g "rg-aisec-$other" --vnet-name "vnet-aisec-$other" -n "peer-$other-to-$side"  # denied
        az storage blob list --account-name "$other_state" -c tfstate --auth-mode login -o none               # denied
        az storage account keys list -g "rg-aisec-$side-state" -n "$own_state" -o none                         # denied
        az group create -n rg-aisec-probe -l swedencentral -o none                                             # denied
        az role assignment create --assignee "$ARM_CLIENT_ID" --role Reader \
          --scope "/subscriptions/$ARM_SUBSCRIPTION_ID/resourceGroups/rg-aisec-$side" -o none                  # denied
        az logout )
      rm -f "${pem:?}"; rm -rf "${AZURE_CONFIG_DIR:?}"; unset AZURE_CONFIG_DIR
    }
    check platform targets
    check targets platform
    ```

    The Azure CLI wants the key as a PEM file, so each block writes one to memory-backed storage and removes it after signing out. It has to exist until then: the CLI reads the file again on every command, not only at sign-in.

    Expected, for each identity: the two `allowed` commands print nothing and succeed. The management commands marked `denied` fail with `AuthorizationFailed`. The blob listing on the other side's state fails with "You do not have the required permissions needed to perform this operation."

    If a `denied` command succeeds, the boundary is broken. Stop and fix the role assignments before going further.

13. Confirm the probes left nothing behind. Run as the operator.

    ```bash
    az network nsg list --query "[?name=='nsg-probe'] | length(@)"
    az group exists -n rg-aisec-probe
    az network vnet peering list -g rg-aisec-platform --vnet-name vnet-aisec-platform --query "[].peeringState" -o tsv
    ```

    Expected: `0`, `false`, `Connected`.

## Rotate a certificate

Rotate one side at a time, before that side's end date from step 4. Do not rerun the step 3 loop: it regenerates both sides and overwrites the keys that Microsoft Entra ID still trusts.

1. Keep the current files, then generate a new key pair for the one side.

   ```bash
   umask 077
   side='REPLACE_WITH_SIDE'   # platform or targets
   mkdir -p -m 700 "$CRED_DIR/previous"
   cp -p "$CRED_DIR/$side.crt" "$CRED_DIR/$side.pfx" "$CRED_DIR/previous/"
   openssl req -x509 -newkey rsa:4096 -sha256 -days 91 -noenc \
     -subj "/CN=aisec-$side-deploy" \
     -keyout "$CRED_DIR/$side.key" -out "$CRED_DIR/$side.crt"
   openssl pkcs12 -export -passout pass: \
     -inkey "$CRED_DIR/$side.key" -in "$CRED_DIR/$side.crt" -out "$CRED_DIR/$side.pfx"
   rm "${CRED_DIR:?}/${side:?}.key"
   ```

   Expected: a new `.crt` and `.pfx` for that side, and the old two in `$CRED_DIR/previous`.

2. In `infra/bootstrap/terraform.tfvars`, set that side's `<side>_certificate_end_date` to a new timestamp from the `date` command in step 4. Leave the other side's date alone.

3. Plan and apply the bootstrap root as the operator.

   ```bash
   cd infra/bootstrap
   terraform plan -out=bootstrap.tfplan
   terraform apply bootstrap.tfplan
   ```

   Expected: the plan replaces one `azuread_application_certificate`, the rotated side's, and touches nothing else. If the other side's certificate is in the plan, stop: its end date was changed too.

   The old key works until this apply removes its certificate. If the plan fails, copy the files back from `previous` and nothing has changed. If the apply fails partway, run it again. The operator does not depend on either certificate.

4. Confirm the new key works, then delete the old one.

   ```bash
   (cd ../$side && source "$CRED_DIR/$side.env" && terraform plan -detailed-exitcode)
   rm -r "$CRED_DIR/previous"
   ```

   Expected: `No changes` and exit `0`.

This procedure has not been run yet.

## Remove it

Removal has not been run. This is the intended order.

1. Destroy `infra/platform`, then `infra/targets`, each as its own identity. Destroying either side breaks the peering.
2. In `infra/bootstrap/main.tf`, remove `prevent_destroy` from the storage accounts. Then destroy the bootstrap root as the operator. This deletes both state accounts, both identities, the custom role, and all four resource groups.
3. Delete `$CRED_DIR`.

The two resource provider registrations stay. They cost nothing.
