# 부팅(로그온) 시 종가베팅 EXE 자동 실행 등록/해제
# 등록:  .\scripts\install_autostart.ps1
# 해제:  .\scripts\install_autostart.ps1 -Uninstall
#
# EXE 내장 스케줄러는 프로세스가 떠 있어야 돈다 — 로그온 시 자동 실행해 트레이에 상주시킨다.
# (Windows 작업스케줄러와 달리 절전에서 PC 를 깨우지는 못한다.)
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$exe = Join-Path $repo "ClosingBet.exe"
$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "종가베팅.lnk"

if ($Uninstall) {
    if (Test-Path $link) { Remove-Item $link -Force; Write-Host "자동 실행 해제됨" -ForegroundColor Green }
    else { Write-Host "등록된 자동 실행 없음" -ForegroundColor DarkGray }
    return
}

if (-not (Test-Path $exe)) { throw "EXE 없음: $exe  (먼저 .\scripts\build_exe.ps1)" }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $repo
$shortcut.Description = "종가베팅 추천 (트레이 상주 · 15:18 자동 스캔)"
$shortcut.Save()

Write-Host "자동 실행 등록: $link" -ForegroundColor Green
Write-Host "다음 로그온부터 트레이에 상주합니다." -ForegroundColor DarkGray
