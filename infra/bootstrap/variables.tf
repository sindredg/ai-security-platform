variable "name_prefix" {
  description = "Short prefix for resource names. Lowercase letters and digits, because storage account names allow nothing else."
  type        = string
  default     = "aisec"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,5}$", var.name_prefix))
    error_message = "Use 2 to 6 lowercase letters or digits, starting with a letter."
  }
}

variable "platform_location" {
  description = "Azure region for platform resources."
  type        = string
  default     = "swedencentral"
}

variable "edge_location" {
  description = "Region of the platform's edge network. Its network watcher takes the platform's flow logs there."
  type        = string
  default     = "denmarkeast"
}

variable "targets_location" {
  description = "Azure region for target resources."
  type        = string
  default     = "denmarkeast"
}

variable "platform_certificate_path" {
  description = "Path to the PEM public certificate of the platform deployment identity. The private key stays outside Terraform."
  type        = string
}

variable "targets_certificate_path" {
  description = "Path to the PEM public certificate of the target deployment identity. The private key stays outside Terraform."
  type        = string
}

variable "platform_certificate_end_date" {
  description = "When Microsoft Entra ID stops accepting the platform certificate, as an RFC 3339 timestamp. Must not be later than the certificate's own expiry."
  type        = string

  validation {
    condition     = can(formatdate("YYYY", var.platform_certificate_end_date))
    error_message = "Use an RFC 3339 timestamp such as 2027-01-08T00:00:00Z."
  }
}

variable "targets_certificate_end_date" {
  description = "When Microsoft Entra ID stops accepting the target certificate, as an RFC 3339 timestamp. Must not be later than the certificate's own expiry."
  type        = string

  validation {
    condition     = can(formatdate("YYYY", var.targets_certificate_end_date))
    error_message = "Use an RFC 3339 timestamp such as 2027-01-08T00:00:00Z."
  }
}
