# 종가베팅 EXE 빌드 — 프론트 정적 빌드 + PyInstaller 원파일 패키징
# 사용:  .\scripts\build_exe.ps1        (backend 디렉터리에서)
# 결과:  <repo>\ClosingBet.exe
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$backend = (Resolve-Path "$PSScriptRoot\..").Path
$repo = (Resolve-Path "$backend\..").Path
$python = Join-Path $backend ".venv\Scripts\python.exe"
$dist = Join-Path $repo "frontend\dist"

if (-not (Test-Path $python)) { throw "가상환경 없음: $python" }

# 1) 프론트 정적 빌드 (.env.production 의 VITE_API_BASE=/api 사용)
if (-not $SkipFrontend) {
    Write-Host "[1/2] 프론트 빌드..." -ForegroundColor Yellow
    Push-Location (Join-Path $repo "frontend")
    npm run build
    Pop-Location
}
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    throw "프론트 dist 없음: $dist  (npm run build 먼저)"
}

# 2) PyInstaller — dist 를 frontend_dist 로 번들(app/desktop.py 가 _MEIPASS 에서 찾는다)
Write-Host "[2/2] EXE 빌드... (수 분 걸립니다)" -ForegroundColor Yellow
Push-Location $backend
# PyInstaller 는 진행 로그를 stderr 로 낸다. ErrorActionPreference=Stop 이면 PowerShell 이
# 그걸 NativeCommandError 로 오인해 정상 빌드를 실패로 만든다 → 종료코드로만 판정한다.
$ErrorActionPreference = "Continue"
& $python -m PyInstaller `
    --noconfirm --clean --onefile --noconsole `
    --name "ClosingBet" `
    --distpath $repo `
    --workpath (Join-Path $backend "build") `
    --specpath (Join-Path $backend "build") `
    --add-data "$dist;frontend_dist" `
    --hidden-import "app.scheduler.service" `
    --hidden-import "app.scheduler.premarket" `
    --hidden-import "app.scheduler.daily_run" `
    --hidden-import "app.scheduler.scoring_job" `
    --hidden-import "app.data.pykrx_client" `
    --hidden-import "app.data.kis_client" `
    --hidden-import "app.data.dart_client" `
    --hidden-import "pykrx" `
    --hidden-import "apscheduler.triggers.cron" `
    --hidden-import "apscheduler.executors.pool" `
    --hidden-import "apscheduler.jobstores.memory" `
    --collect-all "pykrx" `
    --collect-submodules "uvicorn" `
    launcher.py
$code = $LASTEXITCODE
Pop-Location
$ErrorActionPreference = "Stop"
if ($code -ne 0) { throw "PyInstaller 실패 (exit $code)" }

$exe = Join-Path $repo "ClosingBet.exe"
if (Test-Path $exe) {
    $mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "`n완료: $exe  ($mb MB)" -ForegroundColor Green
    Write-Host "부팅 시 자동 실행 등록:  .\scripts\install_autostart.ps1" -ForegroundColor DarkGray
} else {
    throw "EXE 생성 실패"
}
