# ape-lab-portproxy.ps1
#
# Refresh Windows -> WSL2 port forwarding for the APE DNS lab.
#
# Why this exists:
#   Windows 10 (build < Win11 22H2) cannot use `networkingMode=mirrored`, so
#   WSL2 runs in NAT mode and gets a new virtual IP every restart. To reach
#   Backstage / ArgoCD / ingress-nginx from this Windows host or from another
#   PC on the LAN, we need `netsh interface portproxy` rules pointing at the
#   *current* WSL2 IP. That IP rotates, so this script re-reads it and rewrites
#   the four rules idempotently.
#
# Usage (elevated PowerShell on the Windows host):
#   PS> Set-ExecutionPolicy -Scope Process Bypass
#   PS> .\ape-lab-portproxy.ps1
#
# Firewall rules are created by this script on first run. On subsequent runs
# it only touches the portproxy table.

$ErrorActionPreference = 'Stop'

# Must be elevated: portproxy + firewall both require admin.
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run from an elevated PowerShell (Run as Administrator)."
    exit 1
}

# Discover current WSL2 IP. `wsl hostname -I` returns space-separated IPs;
# the first is the eth0 address we want.
$wslIp = (wsl -e sh -c "hostname -I | awk '{print `$1}'").Trim()
if ([string]::IsNullOrWhiteSpace($wslIp)) {
    Write-Error "Could not determine WSL2 IP. Is WSL running? Try: wsl -d Ubuntu echo ok"
    exit 1
}
Write-Host ">>> Current WSL2 IP: $wslIp"

$ports = @(80, 443, 3000, 7007)

Write-Host ">>> Resetting portproxy rules (v4tov4 on 0.0.0.0)"
foreach ($p in $ports) {
    # Delete then re-add -- avoids stale mappings from a previous WSL IP.
    netsh interface portproxy delete v4tov4 listenport=$p listenaddress=0.0.0.0 2>$null | Out-Null
    netsh interface portproxy add    v4tov4 listenport=$p listenaddress=0.0.0.0 `
        connectport=$p connectaddress=$wslIp | Out-Null
    Write-Host "    :$p  ->  ${wslIp}:$p"
}

Write-Host ""
Write-Host ">>> Current portproxy table:"
netsh interface portproxy show v4tov4

# One-time firewall rules. Idempotent: skip if already present.
$firewallRules = @(
    @{ Name = 'APE lab - HTTP';          Port = 80   },
    @{ Name = 'APE lab - HTTPS';         Port = 443  },
    @{ Name = 'APE lab - Backstage UI';  Port = 3000 },
    @{ Name = 'APE lab - Backstage API'; Port = 7007 }
)

Write-Host ""
Write-Host ">>> Ensuring inbound firewall rules"
foreach ($rule in $firewallRules) {
    if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule.Name `
            -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $rule.Port | Out-Null
        Write-Host "    created: $($rule.Name) (TCP $($rule.Port))"
    } else {
        Write-Host "    exists : $($rule.Name) (TCP $($rule.Port))"
    }
}

# Surface the Windows LAN IP so the user knows what to hit from the other PC.
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress)

Write-Host ""
Write-Host ">>> Done."
if ($lanIp) {
    Write-Host "    Backstage UI  : http://${lanIp}:3000"
    Write-Host "    Backstage API : http://${lanIp}:7007"
    Write-Host "    ArgoCD        : http://argocd.localtest.me/  (add '$lanIp argocd.localtest.me' to"
    Write-Host "                    the client PC's C:\Windows\System32\drivers\etc\hosts)"
} else {
    Write-Host "    Could not auto-detect LAN IPv4; run 'ipconfig | findstr IPv4' manually."
}
