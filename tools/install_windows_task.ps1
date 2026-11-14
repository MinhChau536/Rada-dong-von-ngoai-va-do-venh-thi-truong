# Dang ky bo lap lich FTSE Flow Radar chay nen tren Windows (Task Scheduler).
#   - Tu khoi dong khi dang nhap Windows, chay an (pythonw), khong can mo terminal.
#   - Khi khoi dong: tai bu moi phien con thieu tu SSI roi dung lai chi bao.
#   - Hang ngay 15:05: cap nhat; 15:15: Closing Report + Telegram; 22:00: luot du phong.
#   - Bi dung bat thuong -> Task Scheduler chay lai sau 5 phut (toi da 999 lan).
#
#   powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1              # dang ky + chay ngay
#   powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1 -Uninstall   # go bo
#   Get-ScheduledTask -TaskName FTSEFlowRadar | Get-ScheduledTaskInfo                     # xem trang thai
# Nhat ky: logs\app.log ; trang thai cap nhat gan nhat: logs\last_update.json
param([switch]$Uninstall, [string]$TaskName = "FTSEFlowRadar")

$root = Split-Path -Parent $PSScriptRoot
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"

if ($Uninstall) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Da go tac vu $TaskName"
    exit 0
}
if (-not (Test-Path $pyw)) { Write-Error "Khong thay $pyw - hay tao .venv va pip install -r requirements.txt"; exit 1 }
if (-not (Test-Path (Join-Path $root ".env"))) { Write-Error "Thieu tep .env (SSI_API_KEY, SSI_API_SECRET)"; exit 1 }

$action = New-ScheduledTaskAction -Execute $pyw -Argument "-m src.data.scheduler" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 5) -RestartCount 999 -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "FTSE Flow Radar: cap nhat du lieu SSI FastConnect V3 lien tuc, bao cao va canh bao" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Da dang ky va khoi dong tac vu $TaskName (chay khi dang nhap Windows)."
Write-Host "Nhat ky: $root\logs\app.log"
