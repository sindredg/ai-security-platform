variable "name_prefix" {
  description = "Short prefix for resource names. Must match the bootstrap root."
  type        = string
  default     = "aisec"
}

variable "resource_group_name" {
  description = "Target resource group, created by the bootstrap root."
  type        = string
  default     = "rg-aisec-targets"
}

variable "address_space" {
  description = "Target virtual network range."
  type        = string
  default     = "10.50.0.0/20"
}

variable "orchestrator_address_prefix" {
  description = "Platform orchestrator subnet. An agreed input, not read from the platform root's state."
  type        = string
  default     = "10.40.0.0/27"
}

variable "platform_virtual_network_id" {
  description = "Resource ID of the platform virtual network. Leave null until the platform root has created it."
  type        = string
  default     = null
}
