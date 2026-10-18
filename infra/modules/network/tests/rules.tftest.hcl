# The module's own refusals, tested with a mocked provider: no credentials, no
# cloud, and nothing created. Each run plans one subnet with one rule.
#
# Checkov does not read the rules the module builds (issue 99), and Trivy runs
# on pull requests only. This test shows the module itself refuses an inbound
# allow from any address, wherever it is called from.

mock_provider "azurerm" {}

variables {
  name                = "test"
  resource_group_name = "rg-test"
  location            = "swedencentral"
  address_space       = "10.0.0.0/24"
}

# The control: a rule of the shape the platform uses plans.
run "allow_from_a_subnet" {
  command = plan

  variables {
    subnets = {
      worker = {
        address_prefix = "10.0.0.32/27"
        rules = [{
          name                       = "allow-ssh-from-orchestrator"
          priority                   = 100
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = "10.0.0.4"
          destination_address_prefix = "10.0.0.32/27"
          destination_port_range     = "22"
          description                = "Test."
        }]
      }
    }
  }
}

# A deny from any address is how the targets' isolation rules are written.
run "deny_from_any" {
  command = plan

  variables {
    subnets = {
      worker = {
        address_prefix = "10.0.0.32/27"
        rules = [{
          name                       = "deny-from-anywhere"
          priority                   = 100
          direction                  = "Inbound"
          access                     = "Deny"
          protocol                   = "*"
          source_address_prefix      = "*"
          destination_address_prefix = "*"
          destination_port_range     = "*"
          description                = "Test."
        }]
      }
    }
  }
}

run "allow_from_any_is_refused" {
  command = plan

  variables {
    subnets = {
      worker = {
        address_prefix = "10.0.0.32/27"
        rules = [{
          name                       = "allow-ssh-from-anywhere"
          priority                   = 100
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = "*"
          destination_address_prefix = "10.0.0.32/27"
          destination_port_range     = "22"
          description                = "Test."
        }]
      }
    }
  }

  expect_failures = [var.subnets]
}

run "allow_from_internet_tag_is_refused" {
  command = plan

  variables {
    subnets = {
      worker = {
        address_prefix = "10.0.0.32/27"
        rules = [{
          name                       = "allow-https-from-internet"
          priority                   = 100
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = "Internet"
          destination_address_prefix = "10.0.0.32/27"
          destination_port_range     = "443"
          description                = "Test."
        }]
      }
    }
  }

  expect_failures = [var.subnets]
}

run "allow_from_all_addresses_is_refused" {
  command = plan

  variables {
    subnets = {
      worker = {
        address_prefix = "10.0.0.32/27"
        rules = [{
          name                       = "allow-ssh-from-all"
          priority                   = 100
          direction                  = "Inbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = "0.0.0.0/0"
          destination_address_prefix = "10.0.0.32/27"
          destination_port_range     = "22"
          description                = "Test."
        }]
      }
    }
  }

  expect_failures = [var.subnets]
}

# Outbound to the internet is a separate decision, made per subnet (ADR 0020).
run "allow_to_internet_plans" {
  command = plan

  variables {
    subnets = {
      edge = {
        address_prefix = "10.0.0.0/27"
        rules = [{
          name                       = "allow-https-to-internet"
          priority                   = 100
          direction                  = "Outbound"
          access                     = "Allow"
          protocol                   = "Tcp"
          source_address_prefix      = "*"
          destination_address_prefix = "Internet"
          destination_port_range     = "443"
          description                = "Test."
        }]
      }
    }
  }
}
