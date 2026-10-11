data "azurerm_subscription" "current" {}

data "azuread_client_config" "current" {}

locals {
  sides = {
    platform = {
      location         = var.platform_location
      certificate_path = var.platform_certificate_path
      certificate_end  = var.platform_certificate_end_date
      peer             = "targets"
    }
    targets = {
      location         = var.targets_location
      certificate_path = var.targets_certificate_path
      certificate_end  = var.targets_certificate_end_date
      peer             = "platform"
    }
  }

  tags = {
    for side in keys(local.sides) : side => {
      project    = "ai-security-platform"
      side       = side
      managed-by = "terraform-bootstrap"
    }
  }
}

# Each side gets two resource groups. The workload group is what the side's
# root manages. The state group holds that root's state and is out of the
# root's reach, so destroying a root cannot destroy its own state.
resource "azurerm_resource_group" "workload" {
  for_each = local.sides

  name     = "rg-${var.name_prefix}-${each.key}"
  location = each.value.location
  tags     = local.tags[each.key]
}

resource "azurerm_resource_group" "state" {
  for_each = local.sides

  name     = "rg-${var.name_prefix}-${each.key}-state"
  location = each.value.location
  tags     = local.tags[each.key]
}

# Storage account names are global. The suffix keeps them unique without
# putting an account-specific value in the repository.
resource "random_string" "state_suffix" {
  for_each = local.sides

  length  = 6
  lower   = true
  numeric = true
  upper   = false
  special = false
}

# Trivy findings accepted on these accounts, with the reason for each. The
# Checkov equivalents are skipped inside the resource.
#   AZU-0012  A network rule would put an operator address in configuration.
#             Access already takes a Microsoft Entra token with a data role.
#   AZU-0057  Logging waits for the audit log decision. Nothing collects it yet.
#   AZU-0058  State can be rebuilt by import. LRS survives the workstation.
#   AZU-0060  A customer-managed key needs a key vault, for no gain here.
#   AZU-0061  Infrastructure encryption can only be set at creation.
#trivy:ignore:AZU-0012
#trivy:ignore:AZU-0057
#trivy:ignore:AZU-0058
#trivy:ignore:AZU-0060
#trivy:ignore:AZU-0061
resource "azurerm_storage_account" "state" {
  #checkov:skip=CKV_AZURE_59:No network rule, so no operator address in configuration. Entra data roles only
  #checkov:skip=CKV2_AZURE_33:A private endpoint needs a network path the workstation does not have
  #checkov:skip=CKV_AZURE_33:No queues exist on these accounts
  #checkov:skip=CKV_AZURE_206:State can be rebuilt by import. LRS survives the workstation
  #checkov:skip=CKV2_AZURE_1:A customer-managed key needs a key vault and adds a component for no gain
  for_each = local.sides

  name                = "st${var.name_prefix}${each.key}${random_string.state_suffix[each.key].result}"
  resource_group_name = azurerm_resource_group.state[each.key].name
  location            = azurerm_resource_group.state[each.key].location
  tags                = local.tags[each.key]

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  # Microsoft Entra ID only. No account keys, no SAS, no anonymous access.
  shared_access_key_enabled        = false
  default_to_oauth_authentication  = true
  allow_nested_items_to_be_public  = false
  local_user_enabled               = false
  cross_tenant_replication_enabled = false

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 14
    }

    container_delete_retention_policy {
      days = 14
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "state" {
  #checkov:skip=CKV2_AZURE_21:Blob read logging waits for the audit log decision. Nothing collects it yet
  for_each = local.sides

  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state[each.key].id
  container_access_type = "private"
}

# A copy of this root's own state, off the operator machine. The root keeps
# local state, because it creates the accounts a backend would need. The copy
# is uploaded by hand after each apply. It holds identifiers and no secret, so
# sharing an account with the platform state costs nothing.
resource "azurerm_storage_container" "bootstrap_copy" {
  #checkov:skip=CKV2_AZURE_21:Blob read logging waits for the audit log decision. Nothing collects it yet
  name                  = "bootstrap"
  storage_account_id    = azurerm_storage_account.state["platform"].id
  container_access_type = "private"
}

# Owner carries no data role, and shared keys are off. The operator gets write
# access to this one container and to nothing else on the account.
resource "azurerm_role_assignment" "bootstrap_copy" {
  scope                = azurerm_storage_container.bootstrap_copy.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azuread_client_config.current.object_id
  principal_type       = "User"
}
