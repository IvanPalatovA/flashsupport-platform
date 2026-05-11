# FlashSupport Demo Script
Write-Host "`n🚀 FlashSupport - емонстрация системы" -ForegroundColor Cyan
Write-Host "=====================================`n" -ForegroundColor Cyan

# 1. роверка сервисов
Write-Host "1. роверка работоспособности сервисов..." -ForegroundColor Yellow
$services = @(
    @{name="Auth Service"; port=8070},
    @{name="RAG Engine"; port=8080},
    @{name="Knowledge Pipeline"; port=8085},
    @{name="Chat Orchestrator"; port=8090},
    @{name="LLM Runtime"; port=8100}
)

foreach ($svc in $services) {
    try {
        Invoke-RestMethod "http://localhost:$($svc.port)/health" -TimeoutSec 3 | Out-Null
        Write-Host "   ✅ $($svc.name)" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ $($svc.name)" -ForegroundColor Red
    }
}

# 2. емонстрация RAG поиска
Write-Host "`n2. емонстрация поиска в базе знаний..." -ForegroundColor Yellow
$testQuery = "ак сбросить пароль?"
Write-Host "   апрос: $testQuery"
# десь будет вызов к RAG Engine

# 3. роверка базы знаний
Write-Host "`n3. аза знаний:" -ForegroundColor Yellow
docker compose -p flashsupport exec postgres psql -U flash_admin -d flash_support -c "SELECT COUNT(*) as chunks FROM chunks;" 2>$null

Write-Host "`n✅ емонстрация завершена!" -ForegroundColor Green
