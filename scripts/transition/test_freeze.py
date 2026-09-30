import pathlib,subprocess,unittest
SOURCE=pathlib.Path(__file__).with_name('freeze_1x.ps1').read_text()

class FreezeProcessTests(unittest.TestCase):
    def check(self,normal=False,reused=False):
        setup=SOURCE[SOURCE.index("    $node ="):SOURCE.index("    $stage = 'identify_runtimes'")]
        stop=SOURCE[SOURCE.index('    Disable-ScheduledTask'):SOURCE.index('    $result.Resident1xStopped=')]
        mock=r'''
$ErrorActionPreference='Stop'
$global:Killed=@()
$global:T=[pscustomobject]@{Settings=[pscustomobject]@{Enabled=$true};State='Running'}
$global:MockProcesses=@(
 [pscustomobject]@{ProcessId=101;Name='python.exe';CreationDate='original';CommandLine='python.exe node-resident --node-root D:\ECOS\Node'},
 [pscustomobject]@{ProcessId=202;Name='python.exe';CreationDate='resident2';CommandLine='python.exe D:\ECOS\Node\runtime\resident2x\executor.py'},
 [pscustomobject]@{ProcessId=303;Name='python.exe';CreationDate='unrelated';CommandLine='python.exe other.py'})
function Get-CimInstance {param($ClassName) $global:MockProcesses}
function Disable-ScheduledTask {param($InputObject) $global:T.Settings.Enabled=$false}
function Stop-ScheduledTask {param($InputObject)
 $global:T.State='Disabled'
 if(NORMAL){$global:MockProcesses=@($global:MockProcesses|Where-Object ProcessId -ne 101)}
 if(REUSED){$global:MockProcesses[0]=[pscustomobject]@{ProcessId=101;Name='python.exe';CreationDate='replacement';CommandLine='python.exe node-resident --node-root D:\ECOS\Node'}}
}
function Stop-Process {param($Id,[switch]$Force,$ErrorAction) $global:Killed+=$Id;$global:MockProcesses=@($global:MockProcesses|Where-Object ProcessId -ne $Id)}
function Start-Sleep {param($Seconds)}
'''.replace('NORMAL','$true' if normal else '$false').replace('REUSED','$true' if reused else '$false')
        script=mock+setup+"\n$task=$global:T;$original=@(LegacyProcesses)\ntry {\n"+stop+"\n} catch {$global:Failure=$_.Exception.Message}\n"
        script+="if(@($global:MockProcesses|Where-Object ProcessId -in @(202,303)).Count -ne 2){throw 'unrelated_touched'}\n"
        if reused:script+="if($global:Killed.Count -ne 0 -or $global:Failure -ne 'LegacyProcessIdentityChanged'){throw 'pid_reuse_not_fenced'}"
        else:script+="if($global:Failure -or (LegacyProcesses).Count -or $global:T.Settings.Enabled){throw 'freeze_failed'}"
        r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_normal_stop(self):self.check(normal=True)
    def test_forced_stop_preserves_2x_and_unrelated(self):self.check()
    def test_changed_process_identity_blocks_force(self):self.check(reused=True)

if __name__=='__main__':unittest.main()
