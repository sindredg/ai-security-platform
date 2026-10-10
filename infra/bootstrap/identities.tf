# One deployment identity per side. Each authenticates with a certificate whose
# private key is generated on the operator machine and never enters Terraform.
resource "azuread_application" "deploy" {
  for_each = local.sides

  display_name = "${var.name_prefix}-${each.key}-deploy"
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "deploy" {
  for_each = local.sides

  client_id = azuread_application.deploy[each.key].client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_certificate" "deploy" {
  for_each = local.sides

  application_id = azuread_application.deploy[each.key].id
  type           = "AsymmetricX509Cert"
  encoding       = "pem"
  value          = file(each.value.certificate_path)
  end_date       = var.certificate_end_date
}

# Contributor on the side's own workload group and nothing wider. It cannot
# create resource groups or role assignments. Those stay in this root.
resource "azurerm_role_assignment" "workload" {
  for_each = local.sides

  scope                = azurerm_resource_group.workload[each.key].id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.deploy[each.key].object_id
  principal_type       = "ServicePrincipal"
}

# Read and write the side's own state, through the data plane only.
resource "azurerm_role_assignment" "state" {
  for_each = local.sides

  scope                = azurerm_storage_account.state[each.key].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.deploy[each.key].object_id
  principal_type       = "ServicePrincipal"
}

# Azure checks both ends of a peering: write on the local network, and the peer
# action on the remote one. This role carries that one action so neither side
# needs a broader role on the other.
resource "azurerm_role_definition" "peering" {
  name        = "${var.name_prefix}-virtual-network-peer"
  scope       = data.azurerm_subscription.current.id
  description = "Reference a virtual network as the remote end of a peering. Grants no read or write on the network itself."

  permissions {
    actions = ["Microsoft.Network/virtualNetworks/peer/action"]
  }

  assignable_scopes = [data.azurerm_subscription.current.id]
}

resource "azurerm_role_assignment" "peering" {
  for_each = local.sides

  scope              = azurerm_resource_group.workload[each.value.peer].id
  role_definition_id = azurerm_role_definition.peering.role_definition_resource_id
  principal_id       = azuread_service_principal.deploy[each.key].object_id
  principal_type     = "ServicePrincipal"
}
