# 종가베팅 추천 시스템 — Windows 작업스케줄러 3잡 등록
# 사용:  .\register_tasks.ps1              (기본: backend\.venv 파이썬 사용)
#        .\register_tasks.ps1 -PythonExe "C:\Python314\python.exe"
param(
    [string]$PythonExe = "",
    [string]$BackendDir = "$PSScriptRoot\.."
)

$BackendDir = (Resolve-Path $BackendDir).Path

# 기본 파이썬 = backend\.venv — 시스템 python 은 pykrx/KIS 의존성이 없어 잡이 즉시 죽는다.
if (-not $PythonExe) {
    $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "가상환경 파이썬을 찾을 수 없습니다: $venvPython  (-PythonExe 로 직접 지정하세요)"
    }
    $PythonExe = $venvPython
}
Write-Host "python: $PythonExe" -ForegroundColor DarkGray

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
# 익일 오전 채점 + DART 오버나잇 재스캔 — 반드시 10:00 이후(09:00–10:00 VWAP 창
# 완료 후). 09:05에 돌리면 5분치 부분 VWAP으로 잘못 채점되고 멱등이라 영구 고착.
Register-OneTask -Name "CBR-Scoring"   -Module "app.scheduler.scoring_job" -Time "10:05"

Write-Host "done. 확인: Get-ScheduledTask -TaskName 'CBR-*'"
