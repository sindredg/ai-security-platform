#!/bin/bash
# Installs the audit daemon and AIDE on the orchestrator or the worker (ADR
# 0054). Run as root, from the folder that holds the rules, the plugin file,
# the AIDE configurations, the two AIDE commands, and the unit and timer.
# Cloud-init runs it at first boot; the host audit runbook runs it on a built
# machine, and again after a change to any of the files.
#   install-host-audit.sh [orchestrator|worker]
# Without an argument the role is the host name without its aisec- prefix.
# It writes the baseline only where there is none. After an install step the
# new baseline is aisec-aide-baseline, run by hand.
set -euo pipefail
# A failed command stops the script, and this names it: on 2026-10-31 a
# second install on the orchestrator printed "Bus error" and nothing else.
trap 'echo "install-host-audit.sh: failed at line $LINENO: $BASH_COMMAND" >&2' ERR
here="$(cd "$(dirname "$0")" && pwd)"
role=${1:-$(hostname -s)}
role=${role#aisec-}
case $role in
  orchestrator|worker) ;;
  *) echo "role: orchestrator or worker, not $role" >&2; exit 1 ;;
esac
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

# Both from Ubuntu's archive, through Squid, which serves the archive hosts
# at any time. Not pinned, like every other Ubuntu package (ADR 0011):
# unattended upgrades move them. The versions installed are printed. aide
# without aide-common: Debian's configuration, daily check, and mail are not
# used, so there is no package configuration file to keep in step.
DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
  -o DPkg::Lock::Timeout=120 auditd aide
dpkg-query -W -f='${Package} ${Version}\n' auditd aide

# The directories the worker's rules watch exist before the runbook steps that
# fill them, so each watch is a directory watch, which covers what is written
# under it later. Root's, as the steps make them.
if [ "$role" = worker ]; then
  install -d -m 0755 -o root -g root /opt/aisec /home/aisec-job /home/aisec-feed /home/aisec-logexport
fi

# The rules, which augenrules reads after the package's own file, and the
# plugin that sends every record to syslog. The package's syslog.conf stays
# inactive. Ubuntu's unit has no reload, so reload-or-restart restarts the
# daemon, which starts the plugin; a failed rule stops the script here.
# augenrules prints the kernel's status after loading; its errors still show.
install -m 0640 -o root -g root "$here/$role.rules" /etc/audit/rules.d/50-aisec.rules
install -m 0640 -o root -g root "$here/aisec-syslog.conf" /etc/audit/plugins.d/aisec-syslog.conf
systemctl enable --now auditd
augenrules --load >/dev/null
systemctl reload-or-restart auditd
auditctl -s | grep -E "^(enabled|pid|lost) "
echo "rules loaded: $(auditctl -l | grep -c .)"
echo "syslog plugin: $(pgrep -c -x audisp-syslog)"

# AIDE: the configuration, the two commands, the unit and timer, and the
# first baseline. The configuration is read once before anything uses it.
install -d -m 0755 -o root -g root /etc/aisec /usr/local/sbin
install -m 0644 -o root -g root "$here/$role.aide.conf" /etc/aisec/aide.conf
install -m 0755 -o root -g root "$here/aisec-aide-check" "$here/aisec-aide-baseline" /usr/local/sbin/
install -m 0644 -o root -g root "$here/aisec-aide-check.service" "$here/aisec-aide-check.timer" /etc/systemd/system/
aide --config /etc/aisec/aide.conf --config-check
systemctl daemon-reload
# Enabled before the baseline: the link it writes under /etc/systemd/system is
# in the scope. Started after it: the timer is persistent, so its first start
# runs the check at once, against the baseline just written.
systemctl enable aisec-aide-check.timer
if [ ! -e /var/lib/aisec/aide/aide.db ]; then
  /usr/local/sbin/aisec-aide-baseline
fi
systemctl start aisec-aide-check.timer
systemctl list-timers --no-legend aisec-aide-check.timer
