locals {
  # Fixed addresses. The fed machines have no DNS, so every machine knows the
  # others by address and a hosts file.
  orchestrator_ip = cidrhost(local.orchestrator_prefix, 4) # 10.40.0.4
  worker_ip       = cidrhost(local.worker_prefix, 4)       # 10.40.0.36

  image = {
    publisher = "Canonical"
    offer     = "ubuntu-26_04-lts"
    version   = var.image_version
  }

  vms = {
    orchestrator = {
      size      = var.orchestrator_size
      subnet    = "orchestrator"
      address   = local.orchestrator_ip
      image_sku = "server"
      disk_gb   = 64
      cloud_init = templatefile("${path.module}/cloud-init/orchestrator.yaml.tftpl", {
        admin_username     = var.admin_username
        orchestrator_ip    = local.orchestrator_ip
        worker_ip          = local.worker_ip
        advertised_routes  = "${var.address_space},${var.targets_address_space}"
        tailscale_version  = var.tailscale_version
        tailscale_auth_key = var.tailscale_auth_key
        k3s_version        = var.k3s_version
        k3s_sha256         = var.k3s_sha256
        k3s_install_sha256 = var.k3s_install_sha256
      })
    }
    worker = {
      size      = var.worker_size
      subnet    = "worker"
      address   = local.worker_ip
      image_sku = "server-arm64"
      disk_gb   = 64
      cloud_init = templatefile("${path.module}/cloud-init/worker.yaml.tftpl", {
        orchestrator_ip = local.orchestrator_ip
      })
    }
  }
}

# Trivy wants a security group on the interface. Every subnet here has its own,
# ending in a deny-all, and one place for the rules is easier to audit than two.
#trivy:ignore:AZU-0068
resource "azurerm_network_interface" "vm" {
  for_each = local.vms

  name                = "nic-${var.name_prefix}-${each.key}"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  tags                = local.tags

  # No public address, and no IP forwarding. The orchestrator routes for the
  # mesh VPN, but it translates what it forwards to its own address first.
  ip_configuration {
    name                          = "primary"
    subnet_id                     = module.network.subnet_ids[each.value.subnet]
    private_ip_address_allocation = "Static"
    private_ip_address            = each.value.address
  }
}

resource "azurerm_linux_virtual_machine" "vm" {
  #checkov:skip=CKV_AZURE_50:The VM agent runs extensions for run-command, which is the way in when the mesh VPN is down
  for_each = local.vms

  name                = "vm-${var.name_prefix}-${each.key}"
  computer_name       = "${var.name_prefix}-${each.key}"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  zone                = var.zone
  size                = each.value.size
  tags                = local.tags

  network_interface_ids = [azurerm_network_interface.vm[each.key].id]

  admin_username                  = var.admin_username
  disable_password_authentication = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.operator_ssh_public_key
  }

  secure_boot_enabled = true
  vtpm_enabled        = true

  os_disk {
    name                 = "osdisk-${var.name_prefix}-${each.key}"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = each.value.disk_gb
  }

  source_image_reference {
    publisher = local.image.publisher
    offer     = local.image.offer
    sku       = each.value.image_sku
    version   = local.image.version
  }

  # The serial console and its boot log, on managed storage. With run-command,
  # this is the way in when the orchestrator's mesh VPN is down.
  boot_diagnostics {}

  custom_data = base64encode(each.value.cloud_init)

  # Custom data only runs on first boot. A new image or a changed template means
  # a rebuild, and that is a decision, not a side effect of a plan.
  #
  # The operator key is the same. Azure replaces a VM whose key changes, so a
  # rotation swaps the key on the running VMs and updates the variable for the
  # next rebuild.
  lifecycle {
    ignore_changes = [custom_data, admin_ssh_key]
  }
}
