locals {
  # Azure's built-in rules allow everything inside the "VirtualNetwork" tag,
  # and that tag includes a peered network. These two rules sit just above the
  # built-ins and turn every subnet into deny-by-default, peering or not.
  baseline_rules = [
    {
      name                       = "deny-all-inbound"
      priority                   = 4096
      direction                  = "Inbound"
      access                     = "Deny"
      protocol                   = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "*"
      destination_port_range     = "*"
      description                = "Baseline. Nothing enters unless a rule above allows it."
    },
    {
      name                       = "deny-all-outbound"
      priority                   = 4096
      direction                  = "Outbound"
      access                     = "Deny"
      protocol                   = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "*"
      destination_port_range     = "*"
      description                = "Baseline. Nothing leaves unless a rule above allows it."
    },
  ]
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = [var.address_space]
  tags                = var.tags
}

# Rules are inline on purpose. That makes Terraform authoritative for the whole
# rule set, so a rule added by hand shows up as drift and is removed on apply.
#
# AZU-0051 (egress to any address) is ignored for two groups. The
# orchestrator's HTTPS and HTTP rules to the internet are the platform's egress
# point, carried as accepted risk T05 until the edge VM takes them over (ADR
# 0020). The router's reach the mesh VPN's coordination service and relays,
# whose addresses the vendor changes without notice (ADR 0025). The same
# finding on any other subnet still fails. The edge stage moves the
# orchestrator's key to the edge subnet.
#trivy:ignore:AZU-0051[each.key=orchestrator]
#trivy:ignore:AZU-0051[each.key=router]
resource "azurerm_network_security_group" "this" {
  for_each = var.subnets

  name                = "nsg-${var.name}-${each.key}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags

  # A dynamic block, not a list assigned to security_rule. Trivy reads the
  # rules in a dynamic block and skips a list built by a for expression.
  # Checkov reads neither here: it does not resolve each.value in for_each.
  dynamic "security_rule" {
    for_each = concat(each.value.rules, local.baseline_rules)
    content {
      name                       = security_rule.value.name
      description                = security_rule.value.description
      priority                   = security_rule.value.priority
      direction                  = security_rule.value.direction
      access                     = security_rule.value.access
      protocol                   = security_rule.value.protocol
      source_address_prefix      = security_rule.value.source_address_prefix
      source_port_range          = try(security_rule.value.source_port_range, "*")
      destination_address_prefix = security_rule.value.destination_address_prefix
      destination_port_range     = security_rule.value.destination_port_range
    }
  }
}

resource "azurerm_subnet" "this" {
  for_each = var.subnets

  name                 = "snet-${each.key}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [each.value.address_prefix]

  # No implicit outbound internet. Egress is designed, not inherited.
  default_outbound_access_enabled = false
}

resource "azurerm_subnet_network_security_group_association" "this" {
  for_each = var.subnets

  subnet_id                 = azurerm_subnet.this[each.key].id
  network_security_group_id = azurerm_network_security_group.this[each.key].id
}

# One half of each link. The other half belongs to whoever owns the other
# network.
resource "azurerm_virtual_network_peering" "this" {
  for_each = var.peerings

  name                      = each.key
  resource_group_name       = var.resource_group_name
  virtual_network_name      = azurerm_virtual_network.this.name
  remote_virtual_network_id = each.value.remote_virtual_network_id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = false
  allow_gateway_transit        = false
  use_remote_gateways          = false

  # Peer only after every subnet has its security group attached.
  depends_on = [azurerm_subnet_network_security_group_association.this]
}
