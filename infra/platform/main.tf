data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

locals {
  orchestrator_prefix = cidrsubnet(var.address_space, 7, 0)      # 10.40.0.0/27
  worker_prefix       = cidrsubnet(var.address_space, 7, 1)      # 10.40.0.32/27
  monitoring_prefix   = cidrsubnet(var.address_space, 7, 2)      # 10.40.0.64/27
  edge_prefix         = cidrsubnet(var.edge_address_space, 3, 0) # 10.45.0.0/27
  router_prefix       = cidrsubnet(var.edge_address_space, 3, 1) # 10.45.0.32/27

  # Operator sessions arrive from the router, which translates them to its own
  # address (ADR 0025). Every VM takes SSH from that subnet.
  allow_ssh_from_router = {
    name                       = "allow-ssh-from-router"
    priority                   = 1020
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = local.router_prefix
    destination_address_prefix = "*"
    destination_port_range     = "22"
    description                = "Operator sessions through the mesh VPN router."
  }

  # Nothing that starts in the target network gets in, whatever else is allowed
  # later. This rule is on the platform side so no target change can remove it.
  deny_from_targets = {
    name                       = "deny-from-targets"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_address_prefix      = var.targets_address_space
    destination_address_prefix = "*"
    destination_port_range     = "*"
    description                = "Containment. The target network never opens a connection into the platform."
  }

  # The log agents reach Azure Monitor through the private endpoint in the
  # monitoring subnet, and through nothing else (ADR 0021).
  allow_monitoring_out = {
    name                       = "allow-monitoring-private-endpoint"
    priority                   = 1030
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "*"
    destination_address_prefix = local.monitoring_prefix
    destination_port_range     = "443"
    description                = "The log agent, to Azure Monitor's private endpoint."
  }

  tags = {
    project    = "ai-security-platform"
    side       = "platform"
    managed-by = "terraform-platform"
  }
}

module "network" {
  source = "../modules/network"

  name                = "${var.name_prefix}-platform"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  address_space       = var.address_space

  subnets = {
    orchestrator = {
      address_prefix = local.orchestrator_prefix
      rules = [
        local.deny_from_targets,
        local.allow_ssh_from_router,
        {
          name                       = "allow-tool-service-from-worker"
          priority                   = 1010
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.worker_prefix
          destination_address_prefix = local.orchestrator_prefix
          destination_port_range     = "30443"
          description                = "Tool calls. The tool service checks the job token on every call."
        },
        {
          name                       = "deny-to-internet"
          priority                   = 110
          direction                  = "Outbound"
          access                     = "Deny"
          protocol                   = "*"
          source_address_prefix      = "*"
          destination_address_prefix = "Internet"
          destination_port_range     = "*"
          description                = "Containment. The orchestrator reaches the internet only through Squid on the edge."
        },
        {
          name                       = "deny-to-azure-dns"
          priority                   = 120
          direction                  = "Outbound"
          access                     = "Deny"
          protocol                   = "*"
          source_address_prefix      = "*"
          destination_address_prefix = "AzurePlatformDNS"
          destination_port_range     = "*"
          description                = "Containment. Squid resolves names for the orchestrator, and a resolver can carry data out."
        },
        {
          name                       = "allow-ssh-to-worker"
          priority                   = 1000
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = local.worker_prefix
          destination_port_range     = "22"
          description                = "Administration through the orchestrator."
        },
        {
          name                       = "allow-ssh-to-targets"
          priority                   = 1010
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = var.targets_address_space
          destination_port_range     = "22"
          description                = "Administration through the orchestrator."
        },
        {
          name                       = "allow-proxy-to-edge"
          priority                   = 1020
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = local.edge_prefix
          destination_port_range     = "3128"
          description                = "Squid on the edge: packages always, other downloads during a fetch window."
        },
        {
          name                       = "allow-target-packages-to-edge"
          priority                   = 1040
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = "${local.orchestrator_ip}/32"
          destination_address_prefix = local.edge_prefix
          destination_port_range     = "3129"
          description                = "The targets' packages, which the orchestrator forwards to them over SSH during an update run (ADR 0036)."
        },
        local.allow_monitoring_out,
      ]
    }

    worker = {
      address_prefix = local.worker_prefix
      rules = [
        local.deny_from_targets,
        local.allow_ssh_from_router,
        {
          name                       = "deny-to-targets"
          priority                   = 100
          direction                  = "Outbound"
          access                     = "Deny"
          protocol                   = "*"
          source_address_prefix      = "*"
          destination_address_prefix = var.targets_address_space
          destination_port_range     = "*"
          description                = "Containment. The worker never reaches the target network."
        },
        {
          name                       = "deny-to-internet"
          priority                   = 110
          direction                  = "Outbound"
          access                     = "Deny"
          protocol                   = "*"
          source_address_prefix      = "*"
          destination_address_prefix = "Internet"
          destination_port_range     = "*"
          description                = "Containment. The worker never reaches the internet."
        },
        {
          name                       = "deny-to-azure-dns"
          priority                   = 120
          direction                  = "Outbound"
          access                     = "Deny"
          protocol                   = "*"
          source_address_prefix      = "*"
          destination_address_prefix = "AzurePlatformDNS"
          destination_port_range     = "*"
          description                = "Containment. Azure DNS ignores every rule that does not name this tag, and a resolver can carry data out."
        },
        {
          name                       = "allow-package-proxy-to-edge"
          priority                   = 1020
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.worker_prefix
          destination_address_prefix = local.edge_prefix
          destination_port_range     = "3128"
          description                = "Package updates, through Squid on the edge."
        },
        {
          name                       = "allow-tool-service-to-orchestrator"
          priority                   = 1010
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.worker_prefix
          destination_address_prefix = local.orchestrator_prefix
          destination_port_range     = "30443"
          description                = "Tool calls. With package updates, the only connections the worker may start."
        },
        {
          name                       = "allow-ssh-from-orchestrator"
          priority                   = 1000
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = local.worker_prefix
          destination_port_range     = "22"
          description                = "Administration through the orchestrator."
        },
      ]
    }

    # The private endpoint of the Azure Monitor Private Link Scope. It takes
    # the log agents' connections and starts none (ADR 0021).
    monitoring = {
      address_prefix                    = local.monitoring_prefix
      private_endpoint_network_policies = "Enabled"
      rules = [
        local.deny_from_targets,
        {
          name                       = "allow-agents-from-orchestrator"
          priority                   = 1000
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = local.monitoring_prefix
          destination_port_range     = "443"
          description                = "The orchestrator's log agent."
        },
        {
          name                       = "allow-agents-from-edge"
          priority                   = 1010
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.edge_prefix
          destination_address_prefix = local.monitoring_prefix
          destination_port_range     = "443"
          description                = "The edge VM's log agent, over the peering."
        },
        {
          name                       = "allow-agents-from-router"
          priority                   = 1020
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.router_prefix
          destination_address_prefix = local.monitoring_prefix
          destination_port_range     = "443"
          description                = "The router's log agent, over the peering."
        },
      ]
    }
  }

  peerings = merge(
    var.targets_virtual_network_id == null ? {} : {
      peer-platform-to-targets = { remote_virtual_network_id = var.targets_virtual_network_id }
    },
    { peer-platform-to-edge = { remote_virtual_network_id = module.edge_network.virtual_network_id } },
  )

  tags = local.tags
}

# The module held one peering in a list. It holds a map of them now.
moved {
  from = module.network.azurerm_virtual_network_peering.this[0]
  to   = module.network.azurerm_virtual_network_peering.this["peer-platform-to-targets"]
}
