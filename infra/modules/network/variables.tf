variable "name" {
  description = "Name stem for the virtual network and its security groups, for example \"aisec-platform\"."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group to deploy into."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "address_space" {
  description = "Address range of the virtual network."
  type        = string
}

variable "subnets" {
  description = "Subnets by name. Each gets its own security group. Rules listed here sit above a deny-all in both directions."
  type = map(object({
    address_prefix = string
    rules = optional(list(object({
      name                       = string
      priority                   = number
      direction                  = string
      access                     = string
      protocol                   = string
      source_address_prefix      = string
      destination_address_prefix = string
      destination_port_range     = string
      description                = string
    })), [])
  }))

  validation {
    condition = alltrue(flatten([
      for subnet in values(var.subnets) : [
        for rule in subnet.rules : rule.priority >= 100 && rule.priority < 4000
      ]
    ]))
    error_message = "Rule priorities must be from 100 to 3999. 4096 is reserved for the deny-all baseline."
  }
}

variable "peering" {
  description = "Remote virtual network to peer with. Leave null until the remote network exists."
  type = object({
    name                      = string
    remote_virtual_network_id = string
  })
  default = null
}

variable "tags" {
  description = "Tags for every resource."
  type        = map(string)
  default     = {}
}
