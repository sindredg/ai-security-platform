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

variable "edge_location" {
  description = "Region of the edge network, the router, and the edge VM (ADR 0020)."
  type        = string
  default     = "denmarkeast"
}

variable "edge_address_space" {
  description = "Edge virtual network range. The edge subnet is its first /27, the router subnet its second."
  type        = string
  default     = "10.45.0.0/24"
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
  description = "Availability zone for every VM, in its own region."
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
  description = "Ubuntu 26.04 LTS image version of the orchestrator and the worker, the same for both architectures."
  type        = string
  default     = "26.04.202610070"
}

variable "router_size" {
  description = "VM size for the mesh VPN router. x64, 1 GB (ADR 0025)."
  type        = string
  default     = "Standard_B2ats_v2"
}

# Its own pin, so that a newer image for the router does not rebuild the
# orchestrator and the worker. image_version moves with their next rebuild.
variable "router_image_version" {
  description = "Ubuntu 26.04 LTS image version of the router."
  type        = string
  default     = "26.04.202610140"
}

variable "admin_username" {
  description = "Administrator account on every VM. Certificate authentication only (ADR 0022)."
  type        = string
  default     = "aisec"
}

variable "operator_ssh_public_key" {
  description = "The operator's SSH public key, in OpenSSH format. Azure requires one and writes it to the administrator account's authorized_keys, which sshd ignores for that account: it takes only a certificate (ADR 0022). Certificates are signed for this key."
  type        = string
}

variable "operator_user_ca_public_key" {
  description = "Public half of the operator's SSH certificate authority, in OpenSSH format (ADR 0022). The administrator account on each VM accepts only certificates it signed. A change does not reach running VMs: replace /etc/ssh/aisec-user-ca.pub on each, then update this for the next rebuild."
  type        = string

  validation {
    condition     = can(regex("^ssh-ed25519 [A-Za-z0-9+/]+={0,2}( [A-Za-z0-9@._-]+)?$", var.operator_user_ca_public_key))
    error_message = "One Ed25519 public key on one line, in OpenSSH format."
  }
}

variable "tailscale_auth_key" {
  description = "Mesh VPN auth key for the router, under tag:aisec-router. Single use, short expiry. Needed only for the apply that creates the router, and ignored after that. Pass it as TF_VAR_tailscale_auth_key and never write it to a file in the repository. It ends up in the VM's custom data and in state, which is why it has to be single use."
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
