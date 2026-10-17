output "virtual_network_id" {
  description = "Give this to the target root as platform_virtual_network_id."
  value       = module.network.virtual_network_id
}

output "subnet_ids" {
  description = "Subnet resource IDs by subnet name."
  value       = module.network.subnet_ids
}

output "network_security_group_names" {
  description = "Security group names by subnet name."
  value       = module.network.network_security_group_names
}

output "edge_virtual_network_id" {
  description = "Give this to the target root as edge_virtual_network_id."
  value       = module.edge_network.virtual_network_id
}

output "edge_egress_public_ip" {
  description = "Address the platform's outbound traffic comes from, the router's and Squid's, or null while egress is off."
  value       = one(azurerm_public_ip.edge_egress[*].ip_address)
}

output "peering_names" {
  description = "Names of the platform's halves of its peerings, by network."
  value = {
    platform = module.network.peering_names
    edge     = module.edge_network.peering_names
  }
}

output "vm_private_ips" {
  description = "Private address of each VM, by role."
  value       = { for name, nic in azurerm_network_interface.vm : name => nic.private_ip_address }
}
