data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

locals {
  orchestrator_prefix = cidrsubnet(var.address_space, 7, 0) # 10.40.0.0/27
  worker_prefix       = cidrsubnet(var.address_space, 7, 1) # 10.40.0.32/27

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
        {
          name                       = "allow-package-proxy-from-worker"
          priority                   = 1000
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.worker_prefix
          destination_address_prefix = local.orchestrator_prefix
          destination_port_range     = "3128"
          description                = "The worker's package manager. The proxy forwards to two package hosts and nothing else."
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
          name                       = "allow-https-to-internet"
          priority                   = 1100
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "443"
          description                = "Egress. Downloads, registries, feeds, GitHub, and the mesh VPN control and relay servers."
        },
        {
          name                       = "allow-http-to-internet"
          priority                   = 1110
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "80"
          description                = "Egress. Package mirrors that serve signed packages over plain HTTP."
        },
        {
          name                       = "allow-mesh-stun"
          priority                   = 1120
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Udp"
          source_address_prefix      = local.orchestrator_prefix
          destination_address_prefix = "Internet"
          destination_port_range     = "3478"
          description                = "Mesh VPN. The agent learns how it is seen from outside."
        },
        {
          name                       = "allow-mesh-direct"
          priority                   = 1130
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Udp"
          source_address_prefix      = local.orchestrator_prefix
          source_port_range          = "41641"
          destination_address_prefix = "Internet"
          destination_port_range     = "*"
          description                = "Mesh VPN. Direct connection attempts from the agent's own port."
        },
      ]
    }

    worker = {
      address_prefix = local.worker_prefix
      rules = [
        local.deny_from_targets,
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
          description                = "Containment. Azure DNS ignores every rule that does not name this tag, and a resolver is a way out."
        },
        {
          name                       = "allow-package-proxy-to-orchestrator"
          priority                   = 1000
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = local.worker_prefix
          destination_address_prefix = local.orchestrator_prefix
          destination_port_range     = "3128"
          description                = "Package updates. The only connection the worker may start."
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
  }

  peering = var.targets_virtual_network_id == null ? null : {
    name                      = "peer-platform-to-targets"
    remote_virtual_network_id = var.targets_virtual_network_id
  }

  tags = local.tags
}
