terraform {
  required_version = "1.17.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "5.10.0"
    }
  }

  # The storage account name comes from backend.hcl, which is not committed.
  backend "azurerm" {
    container_name   = "tfstate"
    key              = "platform.tfstate"
    use_azuread_auth = true
  }
}
