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
resource "azurerm_network_security_group" "this" {
  for_each = var.subnets

  name                = "nsg-${var.name}-${each.key}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags

  security_rule = [
    for rule in concat(each.value.rules, local.baseline_rules) : {
      name                       = rule.name
      description                = rule.description
      priority                   = rule.priority
      direction                  = rule.direction
      access                     = rule.access
      protocol                   = rule.protocol
      source_address_prefix      = rule.source_address_prefix
      source_port_range          = "*"
      destination_address_prefix = rule.destination_address_prefix
      destination_port_range     = rule.destination_port_range

      source_address_prefixes                    = []
      source_port_ranges                         = []
      source_application_security_group_ids      = []
      destination_address_prefixes               = []
      destination_port_ranges                    = []
      destination_application_security_group_ids = []
    }
  ]
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

# One half of the link. The other half belongs to the other root.
resource "azurerm_virtual_network_peering" "this" {
  count = var.peering == null ? 0 : 1

  name                      = var.peering.name
  resource_group_name       = var.resource_group_name
  virtual_network_name      = azurerm_virtual_network.this.name
  remote_virtual_network_id = var.peering.remote_virtual_network_id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = false
  allow_gateway_transit        = false
  use_remote_gateways          = false

  # Peer only after every subnet has its security group attached.
  depends_on = [azurerm_subnet_network_security_group_association.this]
}
