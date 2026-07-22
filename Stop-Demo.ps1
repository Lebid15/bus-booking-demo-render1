$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
docker compose -f docker-compose.yml -f docker-compose.demo.yml down
Write-Host "تم إيقاف النسخة التجريبية." -ForegroundColor Green
Read-Host "اضغط Enter للإغلاق"
