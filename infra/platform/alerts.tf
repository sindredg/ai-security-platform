# Alert rules on the workspace (ADR 0021, ADR 0028). None has an action
# group: a fired alert shows under Monitor, Alerts, in the portal, and nothing
# is sent. Each rule is stateful: it fires once when its condition starts and
# resolves when it ends, so a condition that lasts does not fire every run.
#
# Each query returns one row per finding, and a rule fires when it returns
# more than none, except the two that watch for silence.
#
# Windows are longer than the frequency where ingestion can be late. A row
# carries the time the agent collected it, and a new table's first row took
# eight minutes on 2026-10-17. A late row still lands in a later window.

locals {
  monitored_computers = join(", ", [for vm in sort(tolist(local.monitored)) : "\"${local.computer_name[vm]}\""])
  computer_name       = { for vm in keys(local.vms) : vm => "${var.name_prefix}-${vm}" }

  # The orchestrator and the worker subnets, which have no way out but Squid.
  contained_prefix = cidrsubnet(var.address_space, 6, 0) # 10.40.0.0/26

  # Squid's native log line: time, elapsed, client, result/status, ...
  squid_fields = <<-KQL
    extend client = extract(@"^\S+\s+\d+\s+(\S+)\s", 1, RawData),
           result = extract(@"^\S+\s+\d+\s+\S+\s+([A-Z_]+)/", 1, RawData)
  KQL

  audit_fields = <<-KQL
    extend line = parse_json(RawData)
    | extend start = tostring(line.start), seq = tolong(line.seq),
             event = tostring(line.event), decision = tostring(line.decision)
  KQL

  alert_rules = {
    heartbeat-missing = {
      description = "No heartbeat from the orchestrator, the edge, or the router for 10 minutes."
      severity    = 1
      frequency   = "PT5M"
      window      = "PT10M"
      query       = <<-KQL
        datatable(Computer: string) [${local.monitored_computers}]
        | join kind=leftanti (Heartbeat | where TimeGenerated > ago(10m) | distinct Computer) on Computer
      KQL
    }

    audit-sequence = {
      description = "A hole in an audit start's sequence, or a new start whose first line is not 1."
      severity    = 1
      frequency   = "PT5M"
      window      = "P2D"
      query       = <<-KQL
        AisecToolAudit_CL
        | ${local.audit_fields}
        | where isnotempty(start) and isnotnull(seq)
        | summarize first_seen = min(TimeGenerated), lowest = min(seq), highest = max(seq), lines = dcount(seq) by start, FilePath
        | where highest - lowest + 1 != lines or (first_seen > ago(30m) and lowest != 1)
      KQL
    }

    copy-marker = {
      description = "A marker line in the audit copy or the journal copy: a line the copier refused, or a full file."
      severity    = 1
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        union AisecToolAudit_CL, AisecWorkerJournal_CL
        | where RawData has_cs "\"event\":\"copy\""
      KQL
    }

    journal-missing = {
      description = "No row from the worker's journal copy for 15 minutes. The pull runs every five."
      severity    = 2
      frequency   = "PT5M"
      window      = "PT15M"
      silence     = true
      query       = "AisecWorkerJournal_CL"
    }

    squid-refused-orchestrator = {
      description = "Squid refused a request from the orchestrator. The checks make one on purpose (P.15)."
      severity    = 1
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        AisecSquidAccess_CL
        | ${local.squid_fields}
        | where client == "${local.orchestrator_ip}" and result startswith "TCP_DENIED"
      KQL
    }

    fetch-window-opened = {
      description = "The operator opened a fetch window on the edge."
      severity    = 3
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        Syslog
        | where Computer == "${local.computer_name["edge"]}" and ProcessName == "aisec-fetch-window"
        | where SyslogMessage startswith "open for"
      KQL
    }

    # The table exists only after traffic analytics first writes, so the query
    # cannot be validated when the rule is created. For a public destination,
    # traffic analytics leaves DestIp empty and puts the address in
    # DestPublicIps.
    denied-flow-to-internet = {
      description = "A denied flow from the orchestrator or worker subnet to a public address. The checks make some on purpose (C.1, E.12)."
      severity    = 1
      frequency   = "PT10M"
      window      = "PT30M"
      skip_valid  = true
      query       = <<-KQL
        NTANetAnalytics
        | where SubType == "FlowLog" and FlowStatus == "Denied"
        | where ipv4_is_in_range(SrcIp, "${local.contained_prefix}") and isnotempty(DestPublicIps)
      KQL
    }

    ssh-login-accepted = {
      description = "An SSH login was accepted on the orchestrator, the edge, or the router."
      severity    = 3
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        Syslog
        | where ProcessName in ("sshd", "sshd-session") and SyslogMessage startswith "Accepted "
      KQL
    }

    ssh-login-failed = {
      description = "An SSH login failed on the orchestrator, the edge, or the router."
      severity    = 2
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        Syslog
        | where ProcessName in ("sshd", "sshd-session")
        | where SyslogMessage startswith "Failed " or SyslogMessage startswith "Invalid user"
            or SyslogMessage has "Refusing certificate"
      KQL
    }

    tool-refusal-burst = {
      description = "More than 20 tool service refusals in 5 minutes."
      severity    = 2
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        AisecToolAudit_CL
        | ${local.audit_fields}
        | where event == "request" and decision == "refused"
        | summarize refusals = count() by bin(TimeGenerated, 5m)
        | where refusals > 20
      KQL
    }

    daily-cap = {
      description = "The workspace's daily cap was reached. Ingestion stops until the reset hour."
      severity    = 1
      frequency   = "PT15M"
      window      = "PT15M"
      query       = <<-KQL
        _LogOperation
        | where Category =~ "Ingestion" and Detail contains "OverQuota"
      KQL
    }

    # The root file system and the boot partitions. Container mounts sit on
    # the same disk as /.
    disk-or-memory = {
      description = "A disk over 85 percent, or memory over 90 percent."
      severity    = 2
      frequency   = "PT15M"
      window      = "PT15M"
      query       = <<-KQL
        Perf
        | where (ObjectName == "Logical Disk" and CounterName == "% Used Space"
                 and InstanceName in ("/", "/boot", "/boot/efi") and CounterValue > 85)
             or (ObjectName == "Memory" and CounterName == "% Used Memory" and CounterValue > 90)
      KQL
    }

    failed-unit = {
      description = "A systemd unit failed on the orchestrator, the edge, or the router."
      severity    = 2
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        Syslog
        | where SyslogMessage has "Failed with result"
      KQL
    }

    # The audit daemon's syslog plugin writes each record as one line (ADR
    # 0054). The orchestrator's arrive through the log agent on local6, the
    # worker's in its journal copy, where the record is the entry's MESSAGE
    # field with its quotes escaped. A write to one of the platform's own
    # files carries the key aisec-config. The install, and every runbook step
    # that writes such a file, fires this on purpose.
    audit-config-write = {
      description = "The audit daemon recorded a write to one of the platform's own files on the orchestrator or the worker."
      severity    = 2
      frequency   = "PT5M"
      window      = "PT15M"
      query       = <<-KQL
        union (Syslog | where Facility == "local6" and SyslogMessage has_cs "type=SYSCALL" and SyslogMessage has_cs "aisec-config"
                 | project TimeGenerated, Computer, line = SyslogMessage),
              (AisecWorkerJournal_CL | where RawData has_cs "type=SYSCALL" and RawData has_cs "aisec-config"
                 | project TimeGenerated, Computer = "aisec-worker", line = RawData)
      KQL
    }

    # The AIDE check logs one line per run with the tag aisec-aide. A check
    # that found nothing reads "added=0 removed=0 changed=0"; anything else
    # is a difference, a failed check, or a new baseline.
    aide-report = {
      description = "The AIDE check on the orchestrator or the worker found a difference from its baseline, failed, or a baseline was written."
      severity    = 2
      frequency   = "PT15M"
      window      = "PT30M"
      query       = <<-KQL
        union (Syslog | where ProcessName == "aisec-aide" | project TimeGenerated, Computer, line = SyslogMessage),
              (AisecWorkerJournal_CL | where RawData has_cs "\"SYSLOG_IDENTIFIER\":\"aisec-aide\""
                 | project TimeGenerated, Computer = "aisec-worker", line = RawData)
        | where not(line has_cs "added=0 removed=0 changed=0")
      KQL
    }

    # The timer runs the check daily on both VMs, so a day without a line
    # from one of them is a stopped timer, a stopped daemon's plugin on the
    # orchestrator, a stopped journal copy from the worker, or a machine
    # root has quieted. As heartbeat-missing: the rows are the machines
    # without a line.
    aide-check-missing = {
      description = "No AIDE check line from the orchestrator or the worker for 26 hours. The timer runs daily."
      severity    = 2
      frequency   = "PT1H"
      window      = "P2D"
      query       = <<-KQL
        datatable(Computer: string) ["${local.computer_name["orchestrator"]}", "${local.computer_name["worker"]}"]
        | join kind=leftanti (
            union (Syslog | where ProcessName == "aisec-aide" | project TimeGenerated, Computer, line = SyslogMessage),
                  (AisecWorkerJournal_CL | where RawData has_cs "\"SYSLOG_IDENTIFIER\":\"aisec-aide\""
                     | project TimeGenerated, Computer = "${local.computer_name["worker"]}", line = RawData)
            | where TimeGenerated > ago(26h) and line has_cs "check "
            | distinct Computer) on Computer
      KQL
    }
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "this" {
  for_each = local.alert_rules

  name                  = "alert-${var.name_prefix}-${each.key}"
  display_name          = each.key
  description           = each.value.description
  resource_group_name   = data.azurerm_resource_group.this.name
  location              = local.platform_location
  scopes                = [azurerm_log_analytics_workspace.this.id]
  severity              = each.value.severity
  evaluation_frequency  = each.value.frequency
  window_duration       = each.value.window
  skip_query_validation = try(each.value.skip_valid, false)
  tags                  = local.tags

  auto_mitigation_enabled = true

  criteria {
    query                   = each.value.query
    time_aggregation_method = "Count"
    operator                = try(each.value.silence, false) ? "LessThan" : "GreaterThan"
    threshold               = try(each.value.silence, false) ? 1 : 0

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  depends_on = [azurerm_log_analytics_workspace_table_custom_log.this]
}
