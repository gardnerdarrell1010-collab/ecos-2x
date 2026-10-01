[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ExpectedHead,
    [Parameter(Mandatory=$true)][string]$ReleaseDirectory,
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [string]$Repository = 'C:\ECOS\ecos-2x'
)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{Status='FAILED'; Administrator=$false; HEADVerified=$false; ReleaseVerified=$false; TaskInstalled=$false; Resident2xHealthy=$false; ExistingRuntimeStopped=$false; RestartAfterBoot='NOT_TESTED'}
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator required' }
    $result.Administrator = $true
    $git = 'C:\Program Files\Git\cmd\git.exe'
    $head = (& $git -C $Repository rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -ne $ExpectedHead) { throw 'HEAD mismatch' }
    $dirty = & $git -C $Repository status --porcelain
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Working tree not clean' }
    $result.HEADVerified = $true
    $release = [IO.Path]::GetFullPath($ReleaseDirectory)
    $manifest = Get-Content -LiteralPath (Join-Path $release 'installed-manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.head -ne $ExpectedHead) { throw 'Release HEAD mismatch' }
    foreach ($file in $manifest.files.PSObject.Properties) {
        $path = [IO.Path]::GetFullPath((Join-Path $release $file.Name))
        if (-not $path.StartsWith($release.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path outside release' }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) { throw 'Release hash mismatch' }
    }
    $result.ReleaseVerified = $true
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    if ($config.identity -ne 'RESIDENT_ADA_2X_HOME01' -or $config.control_plane -ne 'POSTGRESQL' -or @($config.work_sources).Count -ne 1 -or $config.work_sources[0] -ne 'POSTGRESQL') { throw 'Executor profile mismatch' }
    $state = [IO.Path]::GetFullPath($config.state_directory)
    $receipt = Join-Path $state ('startup-install-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $receipt | Out-Null
    $process = Get-Content -LiteralPath (Join-Path $state 'process.json') -Raw | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($process.runtime) -ne (Join-Path $release 'runtime\resident2x\executor.py')) { throw 'Running release mismatch' }
    $python = Join-Path $Repository '.venv\Scripts\python.exe'
    $runner = Join-Path $release 'scripts\resident2x_watchdog.py'
    $arguments = '-B "'+$runner+'" --config "'+[IO.Path]::GetFullPath($ConfigPath)+'"'
    $name = 'ECOS HOME01 Resident Ada 2.x'
    if ($config.domain -eq 'gmail.operations') {
        $name = 'ECOS HOME01 Resident Ada 2.x Gmail'
    }
    $existing = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
    if ($existing) { throw 'Existing task requires reconciliation; no overwrite performed' }
    $action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $release
    $triggers = @((New-ScheduledTaskTrigger -AtStartup),(New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)))
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $task = New-ScheduledTask -Action $action -Trigger $triggers -Principal $taskPrincipal -Settings $settings -Description 'Resident 2.x process continuity only. PostgreSQL selects all work. No 1.x fallback.'
    Register-ScheduledTask -TaskName $name -TaskPath '\' -InputObject $task | Out-Null
    Export-ScheduledTask -TaskName $name -TaskPath '\' | Set-Content -LiteralPath (Join-Path $receipt 'task.xml') -Encoding UTF8
    $readback = Get-ScheduledTask -TaskName $name -TaskPath '\'
    if ($readback.Actions.Execute -ne $python -or $readback.Actions.Arguments -ne $arguments -or -not $readback.Settings.Enabled -or $readback.Principal.LogonType -ne 'S4U') { throw 'Scheduled task readback mismatch' }
    $result.TaskInstalled = $true
    Start-ScheduledTask -TaskName $name -TaskPath '\'
    Start-Sleep -Seconds 5
    $info = Get-ScheduledTaskInfo -TaskName $name -TaskPath '\'
    if ($info.LastTaskResult -ne 0) { throw 'Watchdog invocation failed' }
    $heartbeat = Get-Content -LiteralPath (Join-Path $state 'heartbeat.json') -Raw | ConvertFrom-Json
    if ($heartbeat.instance_id -ne $config.instance_id -or ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($heartbeat.at)).TotalSeconds -gt 90) { throw 'Resident heartbeat stale' }
    $current = Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$heartbeat.pid)
    if (-not $current -or $current.CommandLine -notlike ('*'+$ConfigPath+'*')) { throw 'Resident process identity mismatch' }
    $result.Resident2xHealthy = $true
    $result.Status = 'PASS'
    $result.Receipt = $receipt
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receipt 'verification.json') -Encoding UTF8
} catch {
    $result.ErrorType = $_.Exception.GetType().Name
} finally {
    Write-Output '========== PASTE BACK ONLY THIS SECTION =========='
    $result.GetEnumerator() | ForEach-Object { Write-Output ($_.Key+': '+$_.Value) }
    Write-Output '========== END SECTION =========='
}
