# Run this root as the operator, signed in with the Azure CLI. The subscription
# comes from ARM_SUBSCRIPTION_ID so that no real ID is written to a file here.
provider "azurerm" {
  # Shared key access is off on the state accounts, so the provider has to use
  # Microsoft Entra ID for storage too.
  storage_use_azuread = true

  features {}
}

provider "azuread" {}
