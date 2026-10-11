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
  description = "Subnets by name. Each gets its own security group. Rules listed here sit above a deny-all in both directions. A rule matches any source port unless it names one."
  type = map(object({
    address_prefix = string
    rules = optional(list(object({
      name                       = string
      priority                   = number
      direction                  = string
      access                     = string
      protocol                   = string
      source_address_prefix      = string
      source_port_range          = optional(string, "*")
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

  # Azure rejects these at apply, after other resources in the plan have already
  # changed. Catch them at plan instead.
  validation {
    condition = alltrue([
      for subnet in values(var.subnets) :
      length(distinct([for rule in subnet.rules : lower(rule.name)])) == length(subnet.rules)
    ])
    error_message = "Rule names must be unique within a subnet."
  }

  validation {
    condition = alltrue([
      for subnet in values(var.subnets) :
      length(distinct([for rule in subnet.rules : "${rule.direction}/${rule.priority}"])) == length(subnet.rules)
    ])
    error_message = "Two rules in one subnet cannot share a direction and a priority."
  }

  validation {
    condition = alltrue(flatten([
      for subnet in values(var.subnets) : [
        for rule in subnet.rules :
        contains(["Inbound", "Outbound"], rule.direction) &&
        contains(["Allow", "Deny"], rule.access) &&
        contains(["Tcp", "Udp", "Icmp", "Esp", "Ah", "*"], rule.protocol)
      ]
    ]))
    error_message = "Use direction Inbound or Outbound, access Allow or Deny, and protocol Tcp, Udp, Icmp, Esp, Ah, or *."
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
