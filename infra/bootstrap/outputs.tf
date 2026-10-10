output "tenant_id" {
  description = "Microsoft Entra tenant of the deployment identities."
  value       = data.azuread_client_config.current.tenant_id
}

output "deploy_client_ids" {
  description = "Client ID of each side's deployment identity."
  value       = { for side, app in azuread_application.deploy : side => app.client_id }
}

output "workload_resource_groups" {
  description = "Resource group each root deploys into."
  value       = { for side, rg in azurerm_resource_group.workload : side => rg.name }
}

output "state_storage_accounts" {
  description = "Storage account holding each root's state."
  value       = { for side, account in azurerm_storage_account.state : side => account.name }
}

output "state_container" {
  description = "Blob container name, the same in both state accounts."
  value       = "tfstate"
}
