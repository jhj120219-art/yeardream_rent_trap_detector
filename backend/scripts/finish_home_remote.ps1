#Requires -RunAsAdministrator
param(
    [Parameter(Mandatory=$true)][string]$PublicKeyFile,
    [Parameter(Mandatory=$true)][string]$ShopIP,
    [Parameter(Mandatory=$true)][string]$HomeIP,
    [Parameter(Mandatory=$true)][string]$ExpectedHomeName,
    [Parameter(Mandatory=$true)][string]$HomeUser
)
$ErrorActionPreference = 'Stop'
# Run locally on the HOME PC only. No password auth, public bind, or MySQL change.
if ($env:COMPUTERNAME -ne $ExpectedHomeName) { throw 'Wrong PC. Run this on the home PC.' }
foreach ($ipText in @($ShopIP,$HomeIP)) {
    $ip = [Net.IPAddress]::Parse($ipText); $bytes = $ip.GetAddressBytes()
    if ($bytes.Length -ne 4 -or $bytes[0] -ne 100 -or $bytes[1] -lt 64 -or $bytes[1] -gt 127) { throw 'Expected Tailscale IPv4.' }
}
$ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
$status = (& $ts status --json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $status.BackendState -ne 'Running' -or $status.Self.TailscaleIPs -notcontains $HomeIP) { throw 'Home Tailscale IP changed or login needed.' }
$peers = @($status.Peer.psobject.Properties.Value | Where-Object { $_.TailscaleIPs -contains $ShopIP })
if ($peers.Count -ne 1) { throw 'Shop device not found in this tailnet.' }
if ($HomeUser -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Unsupported local account name.' }
$user = Get-LocalUser -Name $HomeUser
$admins = @(Get-LocalGroupMember -SID 'S-1-5-32-544')
$isAdmin = @($admins | Where-Object { $_.SID.Value -eq $user.SID.Value }).Count -gt 0
$key = (Get-Content -LiteralPath $PublicKeyFile -Raw).Trim()
if ($key -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?$') { throw 'Expected an Ed25519 PUBLIC key.' }
$service = Get-Service sshd
if ($service.Status -eq 'Running') { throw 'Existing SSH is running. Inspect its configuration first; no change performed.' }
$root = Join-Path $env:ProgramData 'YeardreamRentRemote'
New-Item -ItemType Directory -Path $root -Force | Out-Null
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private folder ACL failed.' }
$sshd = Join-Path $env:WINDIR 'System32\OpenSSH\sshd.exe'
$hostPublic = Join-Path $env:ProgramData 'ssh\ssh_host_ed25519_key.pub'
if (-not (Test-Path -LiteralPath $hostPublic)) { throw 'Existing host public key missing. Stop and inspect; host keys were not replaced.' }
$config = Join-Path $env:ProgramData 'ssh\sshd_config'
if (-not (Test-Path -LiteralPath $config)) { throw 'Existing home SSH configuration missing.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
Copy-Item -LiteralPath $config -Destination (Join-Path $root ('sshd_config-before-'+$stamp))
if ($isAdmin) {
    $keyFile = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
} else {
    $profileKey = Get-ItemProperty -LiteralPath ('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\'+$user.SID.Value)
    $sshFolder = Join-Path $profileKey.ProfileImagePath '.ssh'
    New-Item -ItemType Directory -Path $sshFolder -Force | Out-Null
    $keyFile = Join-Path $sshFolder 'authorized_keys'
}
$old = if (Test-Path -LiteralPath $keyFile) { Get-Content -LiteralPath $keyFile -Raw } else { '' }
if ($old) { Copy-Item -LiteralPath $keyFile -Destination (Join-Path $root ('authorized_keys-before-'+$stamp)) }
$line = 'from="'+$ShopIP+'",no-port-forwarding,no-agent-forwarding,no-X11-forwarding '+$key
$newKeys = $old.TrimEnd()+"`r`n"+$line+"`r`n"
$newKeys | Set-Content -LiteralPath $keyFile -Encoding ascii
$grants = @('*S-1-5-18:F','*S-1-5-32-544:F')
if (-not $isAdmin) { $grants += ('*'+$user.SID.Value+':F') }
& icacls.exe $keyFile /inheritance:r /grant:r $grants | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Public key ACL failed. SSH was not started.' }
$keyPath = $keyFile.Replace('\','/')
$newConfig = @"
# Yeardream home-only SSH, shop public key, 2026-10-22
Port 22222
ListenAddress $HomeIP
HostKey __PROGRAMDATA__/ssh/ssh_host_ed25519_key
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
AuthorizedKeysFile "$keyPath"
AllowUsers $HomeUser
StrictModes yes
AllowTcpForwarding no
AllowAgentForwarding no
X11Forwarding no
PermitTunnel no
GatewayPorts no
Subsystem sftp sftp-server.exe
"@
$candidate = Join-Path $root ('sshd_config-candidate-'+$stamp)
$newConfig | Set-Content -LiteralPath $candidate -Encoding ascii
& $sshd -t -f $candidate
if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed. Original configuration preserved.' }
Copy-Item -LiteralPath $candidate -Destination $config
& $sshd -t -f $config
if ($LASTEXITCODE -ne 0) { throw 'SSH validation failed; do not start.' }
$ruleName = 'Yeardream-SSH-Shop-Only'
Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -Name $ruleName -DisplayName 'Yeardream SSH from shop Tailscale only' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22222 -LocalAddress $HomeIP -RemoteAddress $ShopIP -Profile Any | Out-Null
# The service listens only on the VPN IP and key login is restricted to the shop IP.
Set-Service sshd -StartupType Automatic
try { Start-Service sshd } catch {
    Set-Service sshd -StartupType Manual
    Disable-NetFirewallRule -Name $ruleName
    throw
}
$public = (Get-Content -LiteralPath $hostPublic -Raw).Trim()
$result = [ordered]@{home_ip=$HomeIP;home_user=$HomeUser;ssh_port=22222;home_device_id=$status.Self.ID;home_device_name=$status.Self.HostName;shop_ip=$ShopIP;host_public_key=$public;key_path=$keyFile;is_administrator=$isAdmin;setup_at=(Get-Date).ToString('o')}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'yeardream-home-connection.json') -Encoding utf8
Write-Host 'Home setup finished. Send yeardream-home-connection.json and independently confirm this host fingerprint with the shop:'
& (Join-Path $env:WINDIR 'System32\OpenSSH\ssh-keygen.exe') -lf $hostPublic
Write-Host 'No passwords or private keys should be sent. MySQL configuration was not changed.'
