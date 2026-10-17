# Monitoring in Azure Monitor, over Private Link (ADR 0021, ADR 0027).
#
# The orchestrator, the edge, and the router each run the Azure Monitor Agent
# and send to one workspace through one private endpoint. The workspace takes
# no ingestion from public networks. The worker runs no agent: its journal
# reaches the workspace through the orchestrator's copy (ADR 0019).

locals {
  # The VMs with a log agent. The worker is left out on purpose.
  monitored = toset(["orchestrator", "edge", "router"])

  # The configuration endpoint has to be in the agent's own region. Ingestion
  # goes through the workspace's region (ADR 0027).
  collection_endpoint_region = {
    orchestrator = "platform"
    edge         = "edge"
    router       = "edge"
  }

  # One custom table per copied file. Each row is one line of the file,
  # unchanged, in RawData. Queries parse it, so what is stored is what the VM
  # wrote.
  custom_tables = {
    tool_audit = {
      name        = "AisecToolAudit_CL"
      description = "One row per line of the tool service's audit copy on the orchestrator."
    }
    worker_journal = {
      name        = "AisecWorkerJournal_CL"
      description = "One row per line of the worker's journal copy on the orchestrator."
    }
    squid_access = {
      name        = "AisecSquidAccess_CL"
      description = "One row per line of Squid's access log on the edge."
    }
  }

  text_log_columns = [
    { name = "TimeGenerated", type = "dateTime" },
    { name = "Computer", type = "string" },
    { name = "FilePath", type = "string" },
    { name = "RawData", type = "string" },
  ]

  # The entries the agents need, as "address name" lines, from the private
  # endpoint's own record of them. Sorted so a plan shows a real change only.
  monitoring_hosts = join("\n", sort(distinct(flatten([
    for config in azurerm_private_endpoint.monitoring.custom_dns_configs : [
      for address in config.ip_addresses : "${address} ${config.fqdn}"
    ]
  ]))))
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${var.name_prefix}"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = local.platform_location
  sku                 = "PerGB2018"
  tags                = local.tags

  # 31 days are included in the ingestion price.
  retention_in_days = 31
  daily_quota_gb    = var.log_daily_cap_gb

  # Agents send over the private endpoint only. The operator queries from the
  # portal, over the internet, with an Entra sign-in.
  internet_ingestion_access_type = "Disabled"
  internet_query_access_type     = "Enabled"

  # No shared keys. Every writer and reader is an Entra identity, and a VM's
  # identity holds no role here, so it can send but not read or delete.
  local_authentication_enabled    = false
  allow_resource_only_permissions = false
}

resource "azurerm_log_analytics_workspace_table_custom_log" "this" {
  for_each = local.custom_tables

  name         = each.value.name
  workspace_id = azurerm_log_analytics_workspace.this.id
  description  = each.value.description
  plan         = "Analytics"

  dynamic "column" {
    for_each = local.text_log_columns
    content {
      name = column.value.name
      type = column.value.type
    }
  }
}

resource "azurerm_monitor_private_link_scope" "this" {
  name                = "ampls-${var.name_prefix}"
  resource_group_name = data.azurerm_resource_group.this.name
  tags                = local.tags

  ingestion_access_mode = "PrivateOnly"
  query_access_mode     = "Open"
}

# One endpoint per region with an agent. Agents fetch their rules from the one
# in their region. Every rule sends through the platform one.
resource "azurerm_monitor_data_collection_endpoint" "this" {
  for_each = {
    platform = local.platform_location
    edge     = var.edge_location
  }

  name                          = "dce-${var.name_prefix}-${each.key}"
  resource_group_name           = data.azurerm_resource_group.this.name
  location                      = each.value
  kind                          = "Linux"
  public_network_access_enabled = false
  tags                          = local.tags
}

resource "azurerm_monitor_private_link_scoped_service" "workspace" {
  name                = "workspace"
  resource_group_name = data.azurerm_resource_group.this.name
  scope_name          = azurerm_monitor_private_link_scope.this.name
  linked_resource_id  = azurerm_log_analytics_workspace.this.id
}

resource "azurerm_monitor_private_link_scoped_service" "endpoint" {
  for_each = azurerm_monitor_data_collection_endpoint.this

  name                = "dce-${each.key}"
  resource_group_name = data.azurerm_resource_group.this.name
  scope_name          = azurerm_monitor_private_link_scope.this.name
  linked_resource_id  = each.value.id
}

# No private DNS zone group: the VMs get hosts entries instead (ADR 0021).
resource "azurerm_private_endpoint" "monitoring" {
  name                          = "pe-${var.name_prefix}-monitoring"
  resource_group_name           = data.azurerm_resource_group.this.name
  location                      = local.platform_location
  subnet_id                     = module.network.subnet_ids["monitoring"]
  custom_network_interface_name = "nic-${var.name_prefix}-pe-monitoring"
  tags                          = local.tags

  private_service_connection {
    name                           = "ampls"
    private_connection_resource_id = azurerm_monitor_private_link_scope.this.id
    subresource_names              = ["azuremonitor"]
    is_manual_connection           = false
  }

  # The endpoint's names and addresses are fixed when it is created, and only
  # for the resources in the scope at that time.
  depends_on = [
    azurerm_monitor_private_link_scoped_service.workspace,
    azurerm_monitor_private_link_scoped_service.endpoint,
  ]
}

# The hosts entries, written by the VM agent. A change of address or name
# runs the script again (ADR 0027).
resource "azurerm_virtual_machine_run_command" "monitor_hosts" {
  for_each = local.monitored

  name               = "aisec-monitor-hosts"
  location           = local.vms[each.key].location
  virtual_machine_id = azurerm_linux_virtual_machine.vm[each.key].id
  tags               = local.tags

  source {
    script = file("${path.module}/../../platform/monitoring/aisec-monitor-hosts")
  }

  parameter {
    name  = "AISEC_MONITOR_HOSTS_B64"
    value = base64encode(local.monitoring_hosts)
  }
}

resource "azurerm_virtual_machine_extension" "monitor_agent" {
  for_each = local.monitored

  name                 = "AzureMonitorLinuxAgent"
  virtual_machine_id   = azurerm_linux_virtual_machine.vm[each.key].id
  publisher            = "Microsoft.Azure.Monitor"
  type                 = "AzureMonitorLinuxAgent"
  type_handler_version = var.monitor_agent_version
  tags                 = local.tags

  # Moves by hand, like every other pin. Azure picks the newest patch release
  # within the pinned minor version, which this cannot pin.
  auto_upgrade_minor_version = false
  automatic_upgrade_enabled  = false

  depends_on = [azurerm_virtual_machine_run_command.monitor_hosts]
}

# Each agent fetches its rules from the endpoint in its own region.
resource "azurerm_monitor_data_collection_rule_association" "endpoint" {
  for_each = local.monitored

  target_resource_id          = azurerm_linux_virtual_machine.vm[each.key].id
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.this[local.collection_endpoint_region[each.key]].id
  description                 = "Configuration access over the private endpoint."
}

# Syslog and performance counters, the same on all three VMs.
resource "azurerm_monitor_data_collection_rule" "system" {
  name                        = "dcr-${var.name_prefix}-system"
  resource_group_name         = data.azurerm_resource_group.this.name
  location                    = local.platform_location
  kind                        = "Linux"
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.this["platform"].id
  description                 = "Syslog and load from the orchestrator, the edge, and the router."
  tags                        = local.tags

  destinations {
    log_analytics {
      name                  = "workspace"
      workspace_resource_id = azurerm_log_analytics_workspace.this.id
    }
  }

  data_sources {
    # sshd logs an accepted login at info, so the two login facilities are
    # read from info up (ADR 0027).
    syslog {
      name           = "logins"
      facility_names = ["auth", "authpriv"]
      log_levels     = ["Info", "Notice", "Warning", "Error", "Critical", "Alert", "Emergency"]
      streams        = ["Microsoft-Syslog"]
    }

    # The fetch window logs its opens and closes through logger, at user.notice.
    syslog {
      name           = "user"
      facility_names = ["user"]
      log_levels     = ["Notice", "Warning", "Error", "Critical", "Alert", "Emergency"]
      streams        = ["Microsoft-Syslog"]
    }

    syslog {
      name           = "system"
      facility_names = ["kern", "daemon"]
      log_levels     = ["Warning", "Error", "Critical", "Alert", "Emergency"]
      streams        = ["Microsoft-Syslog"]
    }

    performance_counter {
      name                          = "load"
      streams                       = ["Microsoft-Perf"]
      sampling_frequency_in_seconds = 60
      counter_specifiers = [
        "Processor(*)\\% Processor Time",
        "Memory(*)\\% Used Memory",
        "Memory(*)\\Available MBytes Memory",
        "Logical Disk(*)\\% Used Space",
      ]
    }
  }

  data_flow {
    streams      = ["Microsoft-Syslog", "Microsoft-Perf"]
    destinations = ["workspace"]
  }
}

# A rule for each copied file. Each line of the file becomes one row.
locals {
  file_rules = {
    orchestrator = {
      vm          = "orchestrator"
      description = "The audit copy and the worker's journal copy (ADR 0019)."
      files = {
        tool_audit     = "/var/log/aisec/tool-audit.jsonl"
        worker_journal = "/var/log/aisec/worker-journal.jsonl"
      }
    }
    edge = {
      vm          = "edge"
      description = "Squid's access log: both clients, refusals included."
      files = {
        squid_access = "/var/log/squid/access.log"
      }
    }
  }
}

resource "azurerm_monitor_data_collection_rule" "files" {
  for_each = local.file_rules

  name                        = "dcr-${var.name_prefix}-files-${each.key}"
  resource_group_name         = data.azurerm_resource_group.this.name
  location                    = local.platform_location
  kind                        = "Linux"
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.this["platform"].id
  description                 = each.value.description
  tags                        = local.tags

  destinations {
    log_analytics {
      name                  = "workspace"
      workspace_resource_id = azurerm_log_analytics_workspace.this.id
    }
  }

  dynamic "stream_declaration" {
    for_each = each.value.files
    content {
      stream_name = "Custom-${local.custom_tables[stream_declaration.key].name}"
      dynamic "column" {
        for_each = local.text_log_columns
        content {
          name = column.value.name
          type = lower(column.value.type)
        }
      }
    }
  }

  data_sources {
    # No timestamp format: every line is one record. A format would split a
    # line at any timestamp inside it.
    dynamic "log_file" {
      for_each = each.value.files
      content {
        name          = replace(log_file.key, "_", "-")
        format        = "text"
        file_patterns = [log_file.value]
        streams       = ["Custom-${local.custom_tables[log_file.key].name}"]
      }
    }
  }

  dynamic "data_flow" {
    for_each = each.value.files
    content {
      streams       = ["Custom-${local.custom_tables[data_flow.key].name}"]
      destinations  = ["workspace"]
      output_stream = "Custom-${local.custom_tables[data_flow.key].name}"
      transform_kql = "source"
    }
  }

  depends_on = [azurerm_log_analytics_workspace_table_custom_log.this]
}

resource "azurerm_monitor_data_collection_rule_association" "system" {
  for_each = local.monitored

  name                    = "system"
  target_resource_id      = azurerm_linux_virtual_machine.vm[each.key].id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.system.id
}

resource "azurerm_monitor_data_collection_rule_association" "files" {
  for_each = local.file_rules

  name                    = "files"
  target_resource_id      = azurerm_linux_virtual_machine.vm[each.value.vm].id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.files[each.key].id
}
