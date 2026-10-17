locals {
  # Fixed addresses. The fed machines have no DNS, so every machine knows the
  # others by address and a hosts file.
  orchestrator_ip = cidrhost(local.orchestrator_prefix, 4) # 10.40.0.4
  worker_ip       = cidrhost(local.worker_prefix, 4)       # 10.40.0.36
  router_ip       = cidrhost(local.router_prefix, 4)       # 10.45.0.36
  edge_ip         = cidrhost(local.edge_prefix, 4)         # 10.45.0.4

  image = {
    publisher = "Canonical"
    offer     = "ubuntu-26_04-lts"
  }

  platform_location = data.azurerm_resource_group.this.location

  vms = {
    orchestrator = {
      location      = local.platform_location
      size          = var.orchestrator_size
      subnet_id     = module.network.subnet_ids["orchestrator"]
      address       = local.orchestrator_ip
      image_sku     = "server"
      image_version = var.image_version
      disk_gb       = 64
      cloud_init = templatefile("${path.module}/cloud-init/orchestrator.yaml.tftpl", {
        admin_username              = var.admin_username
        operator_user_ca_public_key = var.operator_user_ca_public_key
        orchestrator_ip             = local.orchestrator_ip
        worker_ip                   = local.worker_ip
        worker_prefix               = local.worker_prefix
        k3s_version                 = var.k3s_version
        k3s_sha256                  = var.k3s_sha256
        k3s_install_sha256          = var.k3s_install_sha256
        # The audit copier's files, as they are in the repository (ADR 0019).
        audit_copy_py        = filebase64("${path.module}/../../platform/logs/aisec_audit_copy.py")
        audit_copy_unit      = filebase64("${path.module}/../../platform/logs/aisec-audit-copy.service")
        audit_copy_install   = filebase64("${path.module}/../../platform/logs/install-audit-copy.sh")
        journal_pull_py      = filebase64("${path.module}/../../platform/logs/aisec_journal_pull.py")
        journal_pull_unit    = filebase64("${path.module}/../../platform/logs/aisec-journal-pull.service")
        journal_pull_timer   = filebase64("${path.module}/../../platform/logs/aisec-journal-pull.timer")
        journal_pull_install = filebase64("${path.module}/../../platform/logs/install-journal-pull.sh")
      })
    }
    worker = {
      location      = local.platform_location
      size          = var.worker_size
      subnet_id     = module.network.subnet_ids["worker"]
      address       = local.worker_ip
      image_sku     = "server-arm64"
      image_version = var.image_version
      disk_gb       = 64
      cloud_init = templatefile("${path.module}/cloud-init/worker.yaml.tftpl", {
        admin_username              = var.admin_username
        operator_user_ca_public_key = var.operator_user_ca_public_key
        orchestrator_ip             = local.orchestrator_ip
        # The account the orchestrator pulls the journal through (ADR 0019).
        log_export_command = filebase64("${path.module}/../../worker/log-export/aisec-journal-export")
        log_export_install = filebase64("${path.module}/../../worker/log-export/install-log-export.sh")
        # The account the feed key logs in to (ADR 0026).
        feed_receive_command = filebase64("${path.module}/../../worker/feed/aisec-feed-receive")
        feed_receive_install = filebase64("${path.module}/../../worker/feed/install-feed-account.sh")
      })
    }
    router = {
      location      = var.edge_location
      size          = var.router_size
      subnet_id     = module.edge_network.subnet_ids["router"]
      address       = local.router_ip
      image_sku     = "server"
      image_version = var.image_version
      disk_gb       = 30
      cloud_init = templatefile("${path.module}/cloud-init/router.yaml.tftpl", {
        admin_username              = var.admin_username
        operator_user_ca_public_key = var.operator_user_ca_public_key
        # The edge subnet is advertised with the other two, so operator
        # sessions reach the edge VM (ADR 0025).
        advertised_routes  = "${var.address_space},${var.targets_address_space},${local.edge_prefix}"
        tailscale_version  = var.tailscale_version
        tailscale_auth_key = var.tailscale_auth_key
      })
    }
    edge = {
      location      = var.edge_location
      size          = var.edge_size
      subnet_id     = module.edge_network.subnet_ids["edge"]
      address       = local.edge_ip
      image_sku     = "server"
      image_version = var.image_version
      disk_gb       = 30
      cloud_init = templatefile("${path.module}/cloud-init/edge.yaml.tftpl", {
        admin_username              = var.admin_username
        operator_user_ca_public_key = var.operator_user_ca_public_key
        edge_ip                     = local.edge_ip
        orchestrator_ip             = local.orchestrator_ip
        worker_prefix               = local.worker_prefix
        # The fetch window's command and host list, as they are in the
        # repository (ADR 0020).
        fetch_window = filebase64("${path.module}/../../edge/aisec-fetch-window")
        fetch_hosts  = filebase64("${path.module}/../../edge/fetch-hosts")
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
  location            = each.value.location
  tags                = local.tags

  # No public address, and no IP forwarding. The router forwards for the mesh
  # VPN, but it translates what it forwards to its own address first.
  ip_configuration {
    name                          = "primary"
    subnet_id                     = each.value.subnet_id
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
  location            = each.value.location
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
    version   = each.value.image_version
  }

  # The serial console and its boot log, on managed storage. With run-command,
  # this is the way in when the router is down.
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
