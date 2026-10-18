# The parts of monitoring that the platform identity must not be able to
# change (ADR 0021, ADR 0028).

# Virtual network flow logs for the platform and edge networks, with traffic
# analytics into the platform workspace (ADR 0021, ADR 0028).
#
# They are here, and not in the platform root, for two reasons. Traffic
# analytics creates its own collection rule and endpoint, and Azure checks
# that permission on the workspace's subscription, which the platform identity
# does not hold. And here the platform identity cannot turn them off: the flow
# logs live under Azure's network watchers, and their storage in the platform
# state group, where it has no role.
#
# This root reads the networks and the workspace by name, so the platform
# root has to be applied first.
locals {
  flow_logs = {
    platform = {
      location = var.platform_location
      network  = "vnet-${var.name_prefix}-platform"
    }
    edge = {
      location = var.edge_location
      network  = "vnet-${var.name_prefix}-edge"
    }
  }
}

data "azurerm_virtual_network" "flow_logs" {
  for_each = local.flow_logs

  name                = each.value.network
  resource_group_name = azurerm_resource_group.workload["platform"].name
}

data "azurerm_log_analytics_workspace" "platform" {
  name                = "log-${var.name_prefix}"
  resource_group_name = azurerm_resource_group.workload["platform"].name
}

# A flow log has to write to an account in its network's region. Trivy
# findings accepted, as on the state accounts:
#   AZU-0012  A network rule would have to admit Network Watcher, which writes
#             as a trusted service. Reads take an Entra token with a data role.
#   AZU-0057  Nothing reads the blobs but traffic analytics.
#   AZU-0058  Flow records are kept for 90 days. LRS is enough for that.
#   AZU-0060  A customer-managed key needs a key vault, for no gain here.
#   AZU-0061  Infrastructure encryption can only be set at creation.
#trivy:ignore:AZU-0012
#trivy:ignore:AZU-0057
#trivy:ignore:AZU-0058
#trivy:ignore:AZU-0060
#trivy:ignore:AZU-0061
resource "azurerm_storage_account" "flow_logs" {
  #checkov:skip=CKV_AZURE_59:No network rule. Network Watcher writes as a trusted service, and reads need an Entra data role
  #checkov:skip=CKV2_AZURE_33:A private endpoint serves clients in a network. Network Watcher is not one
  #checkov:skip=CKV_AZURE_33:No queues exist on these accounts
  #checkov:skip=CKV_AZURE_206:Flow records are kept for 90 days. LRS is enough for that
  #checkov:skip=CKV2_AZURE_1:A customer-managed key needs a key vault and adds a component for no gain
  for_each = local.flow_logs

  # At most 24 characters: "staisecflowplat" or "staisecflowedge", and the
  # state accounts' suffix.
  name                = "st${var.name_prefix}flow${substr(each.key, 0, 4)}${random_string.state_suffix["platform"].result}"
  resource_group_name = azurerm_resource_group.state["platform"].name
  location            = each.value.location
  tags                = local.tags["platform"]

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  # Microsoft Entra ID only. Network Watcher writes as a trusted service,
  # which needs no account key.
  shared_access_key_enabled        = false
  default_to_oauth_authentication  = true
  allow_nested_items_to_be_public  = false
  local_user_enabled               = false
  cross_tenant_replication_enabled = false

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_network_watcher_flow_log" "this" {
  for_each = local.flow_logs

  name                 = "fl-${var.name_prefix}-${each.key}"
  network_watcher_name = "NetworkWatcher_${each.value.location}"
  resource_group_name  = "NetworkWatcherRG"
  location             = each.value.location
  target_resource_id   = data.azurerm_virtual_network.flow_logs[each.key].id
  storage_account_id   = azurerm_storage_account.flow_logs[each.key].id
  enabled              = true
  version              = 2
  tags                 = local.tags["platform"]

  # 90 days, the scanners' floor. The raw records are small, and the rows
  # traffic analytics makes from them keep the workspace's 31 days.
  retention_policy {
    enabled = true
    days    = 90
  }

  traffic_analytics {
    enabled               = true
    workspace_id          = data.azurerm_log_analytics_workspace.platform.workspace_id
    workspace_region      = data.azurerm_log_analytics_workspace.platform.location
    workspace_resource_id = data.azurerm_log_analytics_workspace.platform.id
    interval_in_minutes   = 10
  }
}

# Changes to the controls themselves, anywhere in the subscription. The
# Activity Log keeps them whether or not anything else does, and these rules
# cost nothing. They sit in the platform state group, where neither deployment
# identity has a role, so neither can delete them. No action group: a fired
# alert shows under Monitor, Alerts, in the portal.
locals {
  control_changes = {
    security-groups = {
      resource_type = "Microsoft.Network/networkSecurityGroups"
      description   = "A security group was written or deleted."
    }
    security-rules = {
      resource_type = "Microsoft.Network/networkSecurityGroups/securityRules"
      description   = "A security rule was written or deleted on its own, outside its group."
    }
    role-assignments = {
      resource_type = "Microsoft.Authorization/roleAssignments"
      description   = "A role assignment was written or deleted."
    }
    policy-assignments = {
      resource_type = "Microsoft.Authorization/policyAssignments"
      description   = "A policy assignment was written or deleted."
    }
  }
}

resource "azurerm_monitor_activity_log_alert" "control_change" {
  for_each = local.control_changes

  name                = "alert-${var.name_prefix}-${each.key}"
  resource_group_name = azurerm_resource_group.state["platform"].name
  location            = "global"
  scopes              = [data.azurerm_subscription.current.id]
  description         = each.value.description
  tags                = local.tags["platform"]

  # Only finished writes and deletes. A request that Azure refused changed
  # nothing, and every operation also logs a start.
  criteria {
    category      = "Administrative"
    resource_type = each.value.resource_type
    status        = "Succeeded"
  }
}
