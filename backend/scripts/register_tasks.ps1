# 종가베팅 추천 시스템 — Windows 작업스케줄러 3잡 등록
# 사용: 관리자 PowerShell에서  .\register_tasks.ps1 -PythonExe "C:\Python314\python.exe" -BackendDir "D:\work\git\closing-bet-recommender\backend"
param(
    [string]$PythonExe = "python",
    [string]$BackendDir = "$PSScriptRoot\.."
)

$BackendDir = (Resolve-Path $BackendDir).Path

function Register-OneTask {
    param([string]$Name, [string]$Module, [string]$Time)
    $action  = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m $Module" -WorkingDirectory $BackendDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "registered: $Name -> -m $Module @ $Time"
}

# 장전 FINAL prefetch + 헬스체크 (fail-closed)
Register-OneTask -Name "CBR-Premarket" -Module "app.scheduler.premarket" -Time "08:30"
# 15:20 런 — 15:18 기동(부팅·토큰 갱신 여유), 모듈이 캘린더로 15:20–15:30 창·거래일 판정
Register-OneTask -Name "CBR-DailyRun"  -Module "app.scheduler.daily_run" -Time "15:18"
# 익일 오전 채점(09:00–10:00 VWAP 산출 후) + DART 오버나잇 재스캔
Register-OneTask -Name "CBR-Scoring"   -Module "app.scheduler.scoring_job" -Time "09:05"

Write-Host "done. 확인: Get-ScheduledTask -TaskName 'CBR-*'"
