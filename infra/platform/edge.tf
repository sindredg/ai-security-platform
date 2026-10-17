# The edge network in Denmark East (ADR 0020, ADR 0025). It belongs to the
# platform root and the platform resource group. The group's region does not
# bind its resources, and Sweden Central's quota is full.
#
# The router subnet holds the mesh VPN node and nothing else. No subnet has a
# rule that reaches it: the tunnel is opened outbound. The edge subnet holds
# Squid, the one proxy the orchestrator and the worker may use.
module "edge_network" {
  source = "../modules/network"

  name                = "${var.name_prefix}-edge"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = var.edge_location
  address_space       = var.edge_address_space

  subnets = {
    edge = {
      address_prefix = local.edge_prefix
      rules = [
        local.deny_from_targets,
        local.allow_ssh_from_router,
        {
          name                       = "allow-proxy-from-orchestrator"
          priority                   = 1000
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = local.edge_prefix
          destination_port_range     = "3128"
          description                = "The orchestrator's packages, and its fetches while a fetch window is open."
        },
        {
          name                       = "allow-proxy-from-worker"
          priority                   = 1010
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.worker_prefix
          destination_address_prefix = local.edge_prefix
          destination_port_range     = "3128"
          description                = "The worker's packages. Squid forwards them to two package hosts and nothing else."
        },
        {
          name                       = "allow-https-to-internet"
          priority                   = 1000
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.edge_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "443"
          description                = "Squid's tunnels during a fetch window."
        },
        {
          name                       = "allow-http-to-internet"
          priority                   = 1010
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.edge_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "80"
          description                = "Ubuntu mirrors, which serve signed packages over plain HTTP."
        },
        local.allow_monitoring_out,
      ]
    }

    router = {
      address_prefix = local.router_prefix
      rules = [
        {
          name                       = "allow-https-to-internet"
          priority                   = 1000
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.router_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "443"
          description                = "The mesh VPN's coordination service and relays, and the agent's signed package repository."
        },
        {
          name                       = "allow-http-to-internet"
          priority                   = 1010
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.router_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "80"
          description                = "Ubuntu mirrors, which serve signed packages over plain HTTP."
        },
        {
          name                       = "allow-ssh-to-platform"
          priority                   = 1100
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.router_prefix
          destination_address_prefix = var.address_space
          destination_port_range     = "22"
          description                = "Routed operator sessions to the orchestrator and the worker."
        },
        {
          name                       = "allow-ssh-to-targets"
          priority                   = 1110
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.router_prefix
          destination_address_prefix = var.targets_address_space
          destination_port_range     = "22"
          description                = "Routed operator sessions to the targets."
        },
        {
          name                       = "allow-ssh-to-edge"
          priority                   = 1120
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.router_prefix
          destination_address_prefix = local.edge_prefix
          destination_port_range     = "22"
          description                = "Routed operator sessions to the edge VM."
        },
        local.allow_monitoring_out,
      ]
    }
  }

  peerings = merge(
    { peer-edge-to-platform = { remote_virtual_network_id = module.network.virtual_network_id } },
    var.targets_virtual_network_id == null ? {} : {
      peer-edge-to-targets = { remote_virtual_network_id = var.targets_virtual_network_id }
    },
  )

  tags = local.tags
}

# The platform's way out. The router and the edge VM use it, and no other
# subnet has an outbound method.
resource "azurerm_public_ip" "edge_egress" {
  count = var.egress_enabled ? 1 : 0

  name                = "pip-${var.name_prefix}-edge-egress"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = var.edge_location
  allocation_method   = "Static"
  sku                 = "StandardV2"
  tags                = local.tags
}

resource "azurerm_nat_gateway" "edge_egress" {
  count = var.egress_enabled ? 1 : 0

  name                = "ng-${var.name_prefix}-edge-egress"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = var.edge_location
  sku_name            = "StandardV2"
  tags                = local.tags
}

resource "azurerm_nat_gateway_public_ip_association" "edge_egress" {
  count = var.egress_enabled ? 1 : 0

  nat_gateway_id       = azurerm_nat_gateway.edge_egress[0].id
  public_ip_address_id = azurerm_public_ip.edge_egress[0].id
}

resource "azurerm_subnet_nat_gateway_association" "router" {
  count = var.egress_enabled ? 1 : 0

  subnet_id      = module.edge_network.subnet_ids["router"]
  nat_gateway_id = azurerm_nat_gateway.edge_egress[0].id

  # A gateway without an address drops everything it is given.
  depends_on = [azurerm_nat_gateway_public_ip_association.edge_egress]
}

resource "azurerm_subnet_nat_gateway_association" "edge" {
  count = var.egress_enabled ? 1 : 0

  subnet_id      = module.edge_network.subnet_ids["edge"]
  nat_gateway_id = azurerm_nat_gateway.edge_egress[0].id

  depends_on = [azurerm_nat_gateway_public_ip_association.edge_egress]
}
