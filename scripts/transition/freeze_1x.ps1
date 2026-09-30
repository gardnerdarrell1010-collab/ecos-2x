$ErrorActionPreference = 'Stop'
$result = [ordered]@{ ResidentFreezeSucceeded=$false; CheckpointSaved=$false; MaintenanceFence=$false; Resident1xStopped=$false; AutomaticLauncherDisabled=$false; Resident2xPreserved=$false; OnlineLaunchers='OWNER_CONFIRMED_DISABLED'; ActiveOnlineOccurrences='RECONCILIATION_REQUIRED'; Claims='PRESERVED_NO_REPLAY'; EvidenceDirectory=''; FailureStage='' }
$stage = 'administrator_preflight'
try {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'AdministratorRequired' }
    $node = 'D:\ECOS\Node'
    $launcher = Join-Path $node 'Start-EcosResidentAda.ps1'
    $lp = '(?i)(?:^|[\s"''])'+[regex]::Escape($launcher)+'(?=$|[\s"''])'
    $rp = '(?i)(?:^|[\s"''])'+[regex]::Escape($node)+'(?=$|[\s"''])'
    $py = '(?i)(?:^|[\s"''])'+[regex]::Escape((Join-Path $node 'Start-EcosResidentAda.py'))+'(?=$|[\s"''])'
    function LegacyProcesses {
        @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and (($_.CommandLine -match $rp -and $_.CommandLine -match '(?i)(?:^|\s)node-resident(?:\s|$)') -or $_.CommandLine -match $py) })
    }
    $stage = 'identify_runtimes'
    $tasks = @(Get-ScheduledTask | Where-Object { @($_.Actions | Where-Object { $_.Arguments -match $lp }).Count -gt 0 })
    if ($tasks.Count -ne 1) { throw 'LegacyTaskIdentity' }
    $task = $tasks[0]
    $state2 = 'D:\ECOS\Node\runtime\resident2x\state\home01-20260930T071253Z'
    $config2 = Get-Content -LiteralPath (Join-Path $state2 'config.json') -Raw | ConvertFrom-Json
    $process2 = Get-Content -LiteralPath (Join-Path $state2 'process.json') -Raw | ConvertFrom-Json
    if ($config2.identity -ne 'RESIDENT_ADA_2X_HOME01' -or $config2.control_plane -ne 'POSTGRESQL') { throw 'Resident2Identity' }
    $before2 = Get-CimInstance Win32_Process -Filter "ProcessId=$($process2.pid)"
    if (-not $before2 -or $before2.CommandLine -notlike '*resident2x*') { throw 'Resident2NotRunning' }
    $original = @(LegacyProcesses)
    if (@($original | Where-Object ProcessId -eq $process2.pid).Count) { throw 'RuntimeOverlap' }
    $stage = 'checkpoint'
    $evidence = Join-Path $node ('runtime\maintenance-evidence\freeze-1x-'+[guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $evidence | Out-Null
    $who = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $evidence /inheritance:r /grant:r "${who}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'EvidenceAcl' }
    $result.EvidenceDirectory = $evidence
    Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Set-Content -LiteralPath (Join-Path $evidence 'scheduled-task-before.xml') -Encoding UTF8
    $original | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'processes-before.json') -Encoding UTF8
    foreach ($relative in @('runtime\releases\active.json','runtime\resident-ada\heartbeat.json','runtime\resident-ada\state.json','runtime\authoritative-command\ada-runtime\state.json','runtime\authoritative-command\ada-runtime\heartbeat.json')) {
        $source = Join-Path $node $relative
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $evidence ($relative.Replace('\','_'))) }
    }
    $python = 'D:\ECOS\Node\runtime\python-envs\0.4.136-rc.1\python.exe'
    & $python -B (Join-Path $PSScriptRoot 'freeze_checkpoint.py') $evidence before
    if ($LASTEXITCODE -ne 0) { throw 'GovernedCheckpoint' }
    $result.CheckpointSaved=$true; $result.MaintenanceFence=$true
    $stage = 'stop_resident_1x'
    $marker = Join-Path $node 'runtime\authoritative-command\ada-runtime\stop.requested'
    if (Test-Path -LiteralPath $marker) { Copy-Item -LiteralPath $marker -Destination (Join-Path $evidence 'stop-requested-before') }
    'OWNER_FREEZE_1X_NO_AUTOMATIC_RESTART' | Set-Content -LiteralPath $marker -Encoding UTF8
    Disable-ScheduledTask -InputObject $task | Out-Null
    Stop-ScheduledTask -InputObject $task
    for ($i=0;$i -lt 3;$i++) { if (!(LegacyProcesses).Count) { break }; Start-Sleep -Seconds 1 }
    foreach ($p in @(LegacyProcesses)) {
        $prior=@($original | Where-Object { $_.ProcessId -eq $p.ProcessId -and $_.CreationDate -eq $p.CreationDate -and $_.CommandLine -ceq $p.CommandLine })
        if ($prior.Count -ne 1) { throw 'LegacyProcessIdentityChanged' }
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    }
    for ($i=0;$i -lt 3;$i++) { if (!(LegacyProcesses).Count) { break }; Start-Sleep -Seconds 1 }
    if ((LegacyProcesses).Count) { throw 'LegacyStillRunning' }
    $result.Resident1xStopped=$true
    $checkTask=Get-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
    if ($checkTask.Settings.Enabled -or [string]$checkTask.State -ne 'Disabled') { throw 'LauncherNotDisabled' }
    $result.AutomaticLauncherDisabled=$true
    $stage = 'post_freeze_verification'
    $after2=Get-CimInstance Win32_Process -Filter "ProcessId=$($process2.pid)"
    if (-not $after2 -or $after2.CreationDate -ne $before2.CreationDate -or $after2.CommandLine -cne $before2.CommandLine) { throw 'Resident2Changed' }
    $heartbeat2=Get-Content -LiteralPath (Join-Path $state2 'heartbeat.json') -Raw | ConvertFrom-Json
    if ($heartbeat2.pid -ne $process2.pid -or ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($heartbeat2.at)).TotalSeconds -gt 90) { throw 'Resident2HeartbeatStale' }
    $result.Resident2xPreserved=$true
    & $python -B (Join-Path $PSScriptRoot 'freeze_checkpoint.py') $evidence after
    if ($LASTEXITCODE -ne 0) { throw 'PostFreezeCheckpoint' }
    $result.ResidentFreezeSucceeded=$true
} catch { $result.FailureStage=$stage }
finally {
    if ($result.EvidenceDirectory) { $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $result.EvidenceDirectory 'freeze-result.json') -Encoding UTF8 }
    Write-Output '========== PASTE BACK ONLY THIS SECTION =========='
    $result.GetEnumerator() | ForEach-Object { Write-Output ($_.Key+'='+$_.Value) }
    Write-Output '========== END SECTION =========='
}
