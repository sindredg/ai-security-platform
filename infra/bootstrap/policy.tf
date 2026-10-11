# Policy is assigned here because neither deployment identity can change a
# policy assignment. A rule in a root is only as strong as that root's
# discipline. These hold whatever the roots do.

locals {
  builtin_policy = {
    no_public_ip_on_interface  = "/providers/Microsoft.Authorization/policyDefinitions/83a86a26-fd1f-447c-b59d-e51f44264114"
    not_allowed_resource_types = "/providers/Microsoft.Authorization/policyDefinitions/6c112d4e-5bc7-47ae-a041-ea2d9dccd749"
  }
}

# No VM on either side gets a public address. The platform's NAT gateway is not
# a network interface, so its address is unaffected.
resource "azurerm_resource_group_policy_assignment" "no_public_ip_on_interface" {
  for_each = local.sides

  name                 = "deny-public-ip-on-interface"
  display_name         = "Network interfaces must not have a public address"
  description          = "Built-in definition: Network interfaces should not have public IPs."
  resource_group_id    = azurerm_resource_group.workload[each.key].id
  policy_definition_id = local.builtin_policy.no_public_ip_on_interface

  non_compliance_message {
    content = "No VM in this project has a public address. Administration goes over the mesh VPN and egress through the platform NAT gateway."
  }
}

# The target side has no way out at all. Without a public address there is no
# NAT gateway, no outbound load balancer rule, and no firewall to build one from.
resource "azurerm_resource_group_policy_assignment" "targets_no_public_ip_resources" {
  name                 = "deny-public-ip-resources"
  display_name         = "The target side must not hold public IP resources"
  description          = "Built-in definition: Not allowed resource types."
  resource_group_id    = azurerm_resource_group.workload["targets"].id
  policy_definition_id = local.builtin_policy.not_allowed_resource_types

  parameters = jsonencode({
    effect = { value = "Deny" }
    listOfResourceTypesNotAllowed = {
      value = [
        "Microsoft.Network/publicIPAddresses",
        "Microsoft.Network/publicIPPrefixes",
      ]
    }
  })

  non_compliance_message {
    content = "Targets have no internet egress. The orchestrator pushes what they need."
  }
}
