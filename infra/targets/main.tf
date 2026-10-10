data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

locals {
  subnet_prefixes = {
    netbox     = cidrsubnet(var.address_space, 7, 0) # 10.50.0.0/27
    consumer   = cidrsubnet(var.address_space, 7, 1) # 10.50.0.32/27
    unintended = cidrsubnet(var.address_space, 7, 2) # 10.50.0.64/27
    rehearsal  = cidrsubnet(var.address_space, 7, 8) # 10.50.1.0/27
  }
}

module "network" {
  source = "../modules/network"

  name                = "${var.name_prefix}-targets"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  address_space       = var.address_space

  # Every subnet starts closed. The only way in is SSH from the orchestrator.
  # Service ports arrive with the service that listens on them.
  subnets = {
    for name, prefix in local.subnet_prefixes : name => {
      address_prefix = prefix
      rules = [
        {
          name                       = "allow-ssh-from-orchestrator"
          priority                   = 1000
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = var.orchestrator_address_prefix
          destination_address_prefix = prefix
          destination_port_range     = "22"
          description                = "Administration through the orchestrator."
        },
      ]
    }
  }

  peering = var.platform_virtual_network_id == null ? null : {
    name                      = "peer-targets-to-platform"
    remote_virtual_network_id = var.platform_virtual_network_id
  }

  tags = {
    project    = "ai-security-platform"
    side       = "targets"
    managed-by = "terraform-targets"
  }
}
