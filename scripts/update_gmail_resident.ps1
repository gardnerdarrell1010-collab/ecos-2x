[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ExpectedHead,
      [Parameter(Mandatory=$true)][string]$ReleaseDirectory,
      [string]$ConfigurationCandidate,
      [string]$ConfigPath = 'D:\ECOS\Node\runtime\resident2x\state\gmail-home01\config.json',
      [string]$ConfigurationSHA256,
      [switch]$KeepStopped,
      [switch]$Home01IdentityCorrection)
$ErrorActionPreference = 'Stop'
$receipt = $null
$result = [ordered]@{Status='FAILED'; Administrator=$false; ReleaseVerified=$false; TaskUpdated=$false; GmailHealthy=$false; ToastModified=$false; ProviderWritesPerformed=$false}
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator required' }
    $result.Administrator = $true
    $result.ToastModified = ([IO.Path]::GetFullPath($ConfigPath) -ne 'D:\ECOS\Node\runtime\resident2x\state\gmail-home01\config.json')
    $repo = 'C:\ECOS\ecos-2x'
    $git = 'C:\Program Files\Git\cmd\git.exe'
    if ((& $git -C $repo rev-parse HEAD).Trim() -ne $ExpectedHead -or $LASTEXITCODE -ne 0) { throw 'HEAD mismatch' }
    if ((& $git -C $repo status --porcelain) -or $LASTEXITCODE -ne 0) { throw 'Working tree dirty' }
    $release = [IO.Path]::GetFullPath($ReleaseDirectory)
    if (-not $release.StartsWith('D:\ECOS\Node\runtime\resident2x\releases\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Release outside Gmail directory' }
    $manifest = Get-Content -LiteralPath (Join-Path $release 'installed-manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.head -ne $ExpectedHead) { throw 'Manifest HEAD mismatch' }
    foreach ($f in $manifest.files.PSObject.Properties) {
        $path = [IO.Path]::GetFullPath((Join-Path $release $f.Name))
        if (-not $path.StartsWith($release+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid manifest path' }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $f.Value) { throw 'Release hash mismatch' }
    }
    $result.ReleaseVerified = $true
    $config = [IO.Path]::GetFullPath($ConfigPath)
    if (-not $config.StartsWith('D:\ECOS\Node\runtime\resident2x\state\',[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $config)) { throw 'Existing Resident configuration required' }
    $state = Split-Path -Parent $config
    if ($ConfigurationCandidate) {
        $candidate = [IO.Path]::GetFullPath($ConfigurationCandidate)
        if (-not $candidate.StartsWith($state+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Configuration outside existing profile' }
        if ((Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigurationSHA256) { throw 'Configuration hash mismatch' }
        $before = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
        $after = Get-Content -LiteralPath $candidate -Raw | ConvertFrom-Json
        $allowed = @('capabilities','capability_source','shared_capability','operational_sms')
        if ($Home01IdentityCorrection) {
            if ($config -ne 'D:\ECOS\Node\runtime\resident2x\state\home01-20260930T071253Z\config.json') { throw 'Home01 profile required' }
            $allowed = @('instance_id','executor_id','principal_id','database','database_password_file')
        }
        foreach ($property in $before.PSObject.Properties) {
            if ($property.Name -notin $allowed -and (($property.Value | ConvertTo-Json -Depth 100 -Compress) -ne ($after.($property.Name) | ConvertTo-Json -Depth 100 -Compress))) { throw 'Existing profile changed' }
        }
        foreach ($property in $after.PSObject.Properties) {
            if ($property.Name -notin $allowed -and $property.Name -notin $before.PSObject.Properties.Name) { throw 'Unexpected configuration field' }
        }
        if ($after.capability_source -ne 'POSTGRESQL' -or $after.PSObject.Properties.Name -contains 'capabilities') { throw 'Capabilities must be loaded from PostgreSQL bootstrap' }

    }
    $python = Join-Path $repo '.venv\Scripts\python.exe'
    $helper = Join-Path $release 'scripts\prepare_gmail_runtime_resume.py'
    $preflightArgs = @('--config', $config, '--check-only')
    if (-not $KeepStopped) { $preflightArgs += '--require-operational' }
    if ($Home01IdentityCorrection) {
        if (-not $ConfigurationCandidate) { throw 'Canonical candidate required' }
        & $python -B (Join-Path $release 'scripts\home01_identity_preflight.py') --config $config --candidate $candidate | Out-Null
    } else { & $python -B $helper @preflightArgs | Out-Null }
    if ($LASTEXITCODE -eq 2) { $result.FailureCode = 'executor_not_operational'; throw 'PostgreSQL executor disabled or unavailable; task unchanged' }
    if ($LASTEXITCODE -ne 0) { throw 'SQL recovery preflight failed' }
    $matches = @(Get-ScheduledTask -TaskPath '\' | Where-Object { $_.Actions.Arguments -like ('*"'+$config+'"*') })
    if ($matches.Count -ne 1) { throw 'Unique existing Resident task required' }
    $task = $matches[0]
    $name = $task.TaskName
    if (@($task.Actions).Count -ne 1 -or $task.Actions.Execute -ne $python -or $task.Actions.Arguments -notlike ('*"'+$config+'"*')) { throw 'Task identity mismatch' }
    $receipt = Join-Path $state ('gmail-update-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $receipt | Out-Null
    Copy-Item -LiteralPath $config -Destination (Join-Path $receipt 'config-before.json')
    Export-ScheduledTask -TaskName $name -TaskPath '\' | Set-Content -LiteralPath (Join-Path $receipt 'task-before.xml') -Encoding UTF8
    Disable-ScheduledTask -TaskName $name -TaskPath '\' | Out-Null
    Stop-ScheduledTask -TaskName $name -TaskPath '\'
    $processes = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like ('*'+$config+'*') })
    $processes | Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receipt 'processes-before.json') -Encoding UTF8
    foreach ($process in $processes) {
        if ($process.CommandLine -notlike '*\resident2x\releases\*' -or ($process.CommandLine -notlike '*resident2x.py*' -and $process.CommandLine -notlike '*resident2x_watchdog.py*')) { throw 'Unexpected Gmail process; task left disabled' }
    }
    foreach ($process in $processes) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like ('*'+$config+'*') }) { throw 'Gmail process still running' }
    if ($Home01IdentityCorrection) {
        & $python -B (Join-Path $release 'scripts\home01_identity_preflight.py') --config $config --candidate $candidate | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Canonical identity recheck failed' }
        $stateFile = Join-Path $state 'state.json'
        Copy-Item -LiteralPath $stateFile -Destination (Join-Path $receipt 'state-before.json')
        $journal = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        $journal.instance_id = $after.instance_id
        $journal | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $stateFile -Encoding ascii
    } else {
        & $python -B $helper --config $config | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Local claim archive failed; task left disabled' }
    }
    if ($ConfigurationCandidate) {
        Copy-Item -LiteralPath $candidate -Destination $config
        if ((Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigurationSHA256) { throw 'Installed configuration readback mismatch' }
        $result.ConfigurationVerified = $true
    }
    $arguments = '-B "'+(Join-Path $release 'scripts\resident2x_watchdog.py')+'" --config "'+$config+'"'
    $action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $release
    Set-ScheduledTask -TaskName $name -TaskPath '\' -Action $action | Out-Null
    if ($KeepStopped) {
        $readback = Get-ScheduledTask -TaskName $name -TaskPath '\'
        if ($readback.Actions.Arguments -ne $arguments -or $readback.Settings.Enabled) { throw 'Stopped installation readback mismatch' }
        if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like ('*'+$config+'*') }) { throw 'Resident unexpectedly running' }
        $result.TaskUpdated = $true
        $result.RuntimeInstalled = $true
        $result.RuntimeStarted = $false
        $result.TaskEnabled = $false
        $result.Status = 'PASS'
        $result.Receipt = $receipt
        $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receipt 'verification.json') -Encoding UTF8
        return
    }
    Enable-ScheduledTask -TaskName $name -TaskPath '\' | Out-Null
    $readback = Get-ScheduledTask -TaskName $name -TaskPath '\'
    if ($readback.Actions.Arguments -ne $arguments -or -not $readback.Settings.Enabled) { throw 'Task readback mismatch' }
    $result.TaskUpdated = $true
    Start-ScheduledTask -TaskName $name -TaskPath '\'
    Start-Sleep -Seconds 8
    $heartbeat = Get-Content -LiteralPath (Join-Path $state 'heartbeat.json') -Raw | ConvertFrom-Json
    $profile = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    $current = Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$heartbeat.pid)
    if ($heartbeat.instance_id -ne $profile.instance_id -or ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($heartbeat.at)).TotalSeconds -gt 30 -or -not $current -or $current.CommandLine -notlike ('*'+$release+'*') -or $current.CommandLine -notlike ('*'+$config+'*')) { throw 'Updated Gmail heartbeat not verified' }
    $result.GmailHealthy = $true
    $result.Status = 'PASS'
    $result.Receipt = $receipt
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receipt 'verification.json') -Encoding UTF8
} catch { $result.ErrorType = $_.Exception.GetType().Name }
finally {
    if ($receipt -and (Test-Path -LiteralPath $receipt)) {
        $result.Receipt = $receipt
        $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receipt 'verification.json') -Encoding UTF8
    }
    Write-Output '========== PASTE BACK ONLY THIS SECTION =========='
    $result.GetEnumerator() | ForEach-Object { Write-Output ($_.Key+': '+$_.Value) }
    Write-Output '========== END SECTION =========='
}
