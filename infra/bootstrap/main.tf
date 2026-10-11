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

resource "azurerm_storage_account" "state" {
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
  for_each = local.sides

  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state[each.key].id
  container_access_type = "private"
}
