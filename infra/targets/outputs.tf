output "virtual_network_id" {
  description = "Give this to the platform root as targets_virtual_network_id."
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

output "peering_name" {
  description = "Name of the target side of the peering, or null before it exists."
  value       = module.network.peering_name
}
