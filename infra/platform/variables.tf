variable "name_prefix" {
  description = "Short prefix for resource names. Must match the bootstrap root."
  type        = string
  default     = "aisec"
}

variable "resource_group_name" {
  description = "Platform resource group, created by the bootstrap root."
  type        = string
  default     = "rg-aisec-platform"
}

variable "address_space" {
  description = "Platform virtual network range."
  type        = string
  default     = "10.40.0.0/20"
}

variable "targets_address_space" {
  description = "Target virtual network range. An agreed input, not read from the target root's state."
  type        = string
  default     = "10.50.0.0/20"
}

variable "egress_enabled" {
  description = "Create the NAT gateway and its public address. Both bill by the hour while they exist. Set to false to park the lab, and back to true before the orchestrator starts."
  type        = bool
  default     = true
}

variable "targets_virtual_network_id" {
  description = "Resource ID of the target virtual network. Leave null until the target root has created it."
  type        = string
  default     = null
}
