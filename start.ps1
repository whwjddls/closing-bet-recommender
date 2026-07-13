# closing-bet-recommender 로컬 실행 — 백엔드 + 프론트 + (선택)폰 터널
# 사용법:  우클릭 > PowerShell로 실행   또는   PowerShell에서:  .\start.ps1
#          폰 터널까지:  .\start.ps1 -Tunnel
param([switch]$Tunnel)

$root = "D:\work\git\closing-bet-recommender"
$cloudflared = "C:\Users\PC_2403002\tools\cloudflared.exe"

Write-Host "종가베팅 콘솔 실행 중..." -ForegroundColor Yellow

# 1) 백엔드 (FastAPI :8010) — 새 창
Start-Process powershell -ArgumentList "-NoExit","-Command",
  "cd '$root\backend'; .\.venv\Scripts\uvicorn app.main:app --port 8010 --reload"
Write-Host "  [1/3] 백엔드  http://localhost:8010" -ForegroundColor Green

# 2) 프론트 (Vite :5173) — 새 창
Start-Process powershell -ArgumentList "-NoExit","-Command",
  "cd '$root\frontend'; npm run dev"
Write-Host "  [2/3] 프론트  http://localhost:5173  (← PC에서 볼 주소)" -ForegroundColor Green

# 3) 폰 터널(cloudflared) — -Tunnel 옵션 줬을 때만.
#    임시 터널은 켤 때마다 주소가 바뀌므로 로그를 파싱해 state/public_url.txt 에 기록한다.
#    15:20 스케줄러의 텔레그램 알림이 이 파일을 읽어 "보드 열기" 링크로 붙인다.
if ($Tunnel) {
  $log = "$root\backend\state\cloudflared.log"
  $urlFile = "$root\backend\state\public_url.txt"
  if (Test-Path $log) { Remove-Item $log -Force }

  Start-Process powershell -ArgumentList "-NoExit","-Command",
    "& '$cloudflared' tunnel --url http://localhost:5173 --logfile '$log'"

  # 로그에 주소가 찍힐 때까지 최대 30초 대기 → 감지되면 파일로 저장.
  $url = $null
  foreach ($i in 1..30) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
      $match = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' |
               Select-Object -First 1
      if ($match) { $url = $match.Matches[0].Value; break }
    }
  }
  if ($url) {
    # Set-Content -Encoding utf8 은 BOM 을 붙여 URL 이 "﻿https://..." 로 깨진다.
    # WriteAllText 는 BOM 없는 UTF-8 로 쓴다.
    [System.IO.File]::WriteAllText($urlFile, $url)
    Write-Host "  [3/3] 폰 터널  $url" -ForegroundColor Green
    Write-Host "         (알림 링크용으로 state/public_url.txt 에 저장했습니다)" -ForegroundColor DarkGray
  } else {
    Write-Host "  [3/3] 폰 터널  주소 감지 실패 — 열린 창의 주소를 직접 확인하세요" -ForegroundColor Yellow
  }
} else {
  Write-Host "  [3/3] 폰 터널  생략 (폰으로 보려면:  .\start.ps1 -Tunnel )" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "10~20초 뒤 브라우저에서 http://localhost:5173 접속하세요." -ForegroundColor Yellow
Write-Host "추천 스캔은 작업스케줄러(CBR-DailyRun)가 매일 15:18에 자동 실행합니다." -ForegroundColor DarkGray
Write-Host "끄려면 각 창을 닫으면 됩니다." -ForegroundColor DarkGray
