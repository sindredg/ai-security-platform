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

variable "zone" {
  description = "Availability zone for both VMs."
  type        = string
  default     = "1"
}

variable "orchestrator_size" {
  description = "VM size for the orchestrator. x64."
  type        = string
  default     = "Standard_B2as_v2"
}

variable "worker_size" {
  description = "VM size for the AI worker. Arm64, for two physical cores inside a 2 vCPU quota."
  type        = string
  default     = "Standard_D2ps_v6"
}

variable "image_version" {
  description = "Ubuntu 26.04 LTS image version, the same for both architectures."
  type        = string
  default     = "26.04.202610070"
}

variable "admin_username" {
  description = "Administrator account on both VMs. Key authentication only."
  type        = string
  default     = "aisec"
}

variable "operator_ssh_public_key" {
  description = "The operator's SSH public key, in OpenSSH format. The only key the VMs trust at first boot."
  type        = string
}

variable "tailscale_auth_key" {
  description = "Mesh VPN auth key for the orchestrator. Single use, short expiry, tagged. Needed only for the apply that creates the orchestrator, and ignored after that. Pass it as TF_VAR_tailscale_auth_key and never write it to a file in the repository. It ends up in the VM's custom data and in state, which is why it has to be single use."
  type        = string
  sensitive   = true
  default     = ""
}

variable "tailscale_version" {
  description = "Mesh VPN agent version, as the package repository names it."
  type        = string
  default     = "1.104.1"
}

variable "k3s_version" {
  description = "K3s release. The stable channel version at the time of writing."
  type        = string
  default     = "v1.36.5+k3s1"
}

variable "k3s_sha256" {
  description = "SHA-256 of the amd64 k3s binary for k3s_version, from the release's sha256sum-amd64.txt."
  type        = string
  default     = "d73847bcd3c5fccef0115b372e2f9a91f3032dc84bbf71518a4617565294d313"
}

variable "k3s_install_sha256" {
  description = "SHA-256 of install.sh at the k3s_version tag."
  type        = string
  default     = "46177d4c99440b4c0311b67233823a8e8a2fc09693f6c89af1a7161e152fbfad"
}
