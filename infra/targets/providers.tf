# Run this root as the targets deployment identity. Subscription, tenant, client
# ID, and certificate come from ARM_* environment variables.
provider "azurerm" {
  storage_use_azuread = true

  features {}
}
