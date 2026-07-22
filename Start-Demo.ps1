$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "" 
Write-Host "=== منصة حجز البولمن - النسخة التجريبية ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "Docker Desktop غير مثبت أو غير موجود في PATH." -ForegroundColor Red
  Write-Host "ثبّت Docker Desktop ثم أعد تشغيل هذا الملف."
  Read-Host "اضغط Enter للإغلاق"
  exit 1
}

try {
  docker info | Out-Null
} catch {
  Write-Host "Docker Desktop غير مشغّل. شغّله وانتظر حتى يصبح Ready ثم أعد المحاولة." -ForegroundColor Red
  Read-Host "اضغط Enter للإغلاق"
  exit 1
}

Write-Host "يتم بناء الخدمات وتهيئة بيانات Demo..." -ForegroundColor Yellow
docker compose -f docker-compose.yml -f docker-compose.demo.yml up --build -d
if ($LASTEXITCODE -ne 0) { throw "فشل تشغيل Docker Compose" }

Write-Host "انتظار جاهزية الخادم..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/health/ready" -TimeoutSec 3
    if ($response.status -eq "ok") { $ready = $true; break }
  } catch { Start-Sleep -Seconds 2 }
}

if (-not $ready) {
  Write-Host "لم تصبح الخدمة جاهزة. هذه آخر السجلات:" -ForegroundColor Red
  docker compose -f docker-compose.yml -f docker-compose.demo.yml logs --tail=80 api
  Read-Host "اضغط Enter للإغلاق"
  exit 1
}

Write-Host "" 
Write-Host "تم التشغيل بنجاح." -ForegroundColor Green
Write-Host "الموقع:       http://localhost:3000"
Write-Host "تسجيل الدخول: http://localhost:3000/login"
Write-Host ""
Write-Host "مدير المنصة: admin@demo.local / DemoAdmin!2026"
Write-Host "مالك المكتب: office@demo.local / DemoOffice!2026"
Write-Host "موظف الحجز:  agent@demo.local / DemoAgent!2026"
Write-Host ""
Start-Process "http://localhost:3000/login"
Write-Host "يمكنك إغلاق هذه النافذة؛ ستبقى الخدمات تعمل في الخلفية."
Read-Host "اضغط Enter للإغلاق"
