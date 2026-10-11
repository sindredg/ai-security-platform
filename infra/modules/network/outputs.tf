output "virtual_network_id" {
  description = "Resource ID of the virtual network. The other root needs it to peer."
  value       = azurerm_virtual_network.this.id
}

output "subnet_ids" {
  description = "Subnet resource IDs by subnet name."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.id }
}

output "network_security_group_names" {
  description = "Security group names by subnet name."
  value       = { for name, nsg in azurerm_network_security_group.this : name => nsg.name }
}

output "peering_name" {
  description = "Name of this side's peering, or null before it exists."
  value       = one(azurerm_virtual_network_peering.this[*].name)
}
