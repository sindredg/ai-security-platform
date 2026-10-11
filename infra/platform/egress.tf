# The one way out of the whole system. It is attached to the orchestrator
# subnet and to nothing else. The worker and the targets are fed from the
# orchestrator and never get an outbound method.
resource "azurerm_public_ip" "egress" {
  count = var.egress_enabled ? 1 : 0

  name                = "pip-${var.name_prefix}-platform-egress"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  allocation_method   = "Static"
  sku                 = "StandardV2"
  tags                = local.tags
}

resource "azurerm_nat_gateway" "egress" {
  count = var.egress_enabled ? 1 : 0

  name                = "ng-${var.name_prefix}-platform-egress"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  sku_name            = "StandardV2"
  tags                = local.tags
}

resource "azurerm_nat_gateway_public_ip_association" "egress" {
  count = var.egress_enabled ? 1 : 0

  nat_gateway_id       = azurerm_nat_gateway.egress[0].id
  public_ip_address_id = azurerm_public_ip.egress[0].id
}

resource "azurerm_subnet_nat_gateway_association" "orchestrator" {
  count = var.egress_enabled ? 1 : 0

  subnet_id      = module.network.subnet_ids["orchestrator"]
  nat_gateway_id = azurerm_nat_gateway.egress[0].id

  # A gateway without an address drops everything it is given.
  depends_on = [azurerm_nat_gateway_public_ip_association.egress]
}
