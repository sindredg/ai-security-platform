terraform {
  required_version = "1.16.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "5.9.0"
    }
  }

  # The storage account name comes from backend.hcl, which is not committed.
  backend "azurerm" {
    container_name   = "tfstate"
    key              = "targets.tfstate"
    use_azuread_auth = true
  }
}
