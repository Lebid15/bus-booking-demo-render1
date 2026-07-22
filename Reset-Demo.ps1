$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "سيتم حذف قاعدة البيانات التجريبية وإعادة إنشائها." -ForegroundColor Yellow
docker compose -f docker-compose.yml -f docker-compose.demo.yml down -v
& "$PSScriptRoot\Start-Demo.ps1"
