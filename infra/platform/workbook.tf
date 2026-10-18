# One workbook with what the alert rules do not show (ADR 0021). It is a
# Terraform resource, so a change to it is reviewed like a rule.

locals {
  workbook_panels = [
    {
      title         = "Tool calls by decision"
      visualization = "timechart"
      query         = <<-KQL
        AisecToolAudit_CL
        | ${local.audit_fields}
        | where event == "request"
        | summarize calls = count() by decision, bin(TimeGenerated, 15m)
      KQL
    },
    {
      title         = "Squid requests by client and result"
      visualization = "timechart"
      query         = <<-KQL
        AisecSquidAccess_CL
        | ${local.squid_fields}
        | summarize requests = count() by series = strcat(client, " ", result), bin(TimeGenerated, 15m)
      KQL
    },
    {
      title         = "Flows by source subnet and status"
      visualization = "timechart"
      query         = <<-KQL
        NTANetAnalytics
        | where SubType == "FlowLog"
        | extend subnet = case(
            ipv4_is_in_range(SrcIp, "${local.orchestrator_prefix}"), "orchestrator",
            ipv4_is_in_range(SrcIp, "${local.worker_prefix}"), "worker",
            ipv4_is_in_range(SrcIp, "${local.edge_prefix}"), "edge",
            ipv4_is_in_range(SrcIp, "${local.router_prefix}"), "router",
            "other")
        | summarize flows = count() by series = strcat(subnet, " ", FlowStatus), bin(TimeGenerated, 30m)
      KQL
    },
    {
      title         = "CPU and memory by VM"
      visualization = "timechart"
      query         = <<-KQL
        Perf
        | where (ObjectName == "Processor" and InstanceName == "total") or CounterName == "% Used Memory"
        | summarize percent = avg(CounterValue) by series = strcat(Computer, " ", CounterName), bin(TimeGenerated, 15m)
      KQL
    },
  ]
}

resource "azurerm_application_insights_workbook" "this" {
  name                = uuidv5("url", "https://github.com/sindredg/ai-security-platform/workbooks/platform")
  display_name        = "AI security platform"
  description         = "Tool calls, Squid traffic, flows, and load."
  resource_group_name = data.azurerm_resource_group.this.name
  location            = local.platform_location
  source_id           = lower(azurerm_log_analytics_workspace.this.id)
  tags                = local.tags

  data_json = jsonencode({
    version             = "Notebook/1.0"
    fallbackResourceIds = [azurerm_log_analytics_workspace.this.id]
    items = [
      for panel in local.workbook_panels : {
        type = 3
        name = panel.title
        content = {
          version                 = "KqlItem/1.0"
          title                   = panel.title
          query                   = panel.query
          size                    = 0
          timeContext             = { durationMs = 86400000 }
          queryType               = 0
          resourceType            = "microsoft.operationalinsights/workspaces"
          crossComponentResources = [azurerm_log_analytics_workspace.this.id]
          visualization           = panel.visualization
        }
      }
    ]
  })
}
