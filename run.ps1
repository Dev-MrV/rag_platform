# Enterprise RAG Platform - Startup Script
# Run from the project root: .\run.ps1

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND = Join-Path $ROOT "backend"
$FRONTEND = Join-Path $ROOT "frontend"
$MONGOD = "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe"
$MONGO_DATA = Join-Path $ROOT "mongo_data"

Write-Host ""
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host "   Enterprise RAG Platform  v1.0 (Ollama)" -ForegroundColor Cyan
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Check .env exists ----------------------------------------
$envFile = Join-Path $ROOT ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "[ERR] .env file not found at $envFile" -ForegroundColor Red
    exit 1
}
Write-Host "[OK]  .env file found." -ForegroundColor Green

# -- 2. Check Ollama is running ----------------------------------
$ollamaRunning = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaRunning) {
    Write-Host "[OK]  Ollama is already running." -ForegroundColor Green
} else {
    Write-Host "[WARN] Ollama process not detected. Starting..." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Minimized
    Start-Sleep -Seconds 2
    Write-Host "[OK]  Ollama started." -ForegroundColor Green
}

# -- 3. Start MongoDB --------------------------------------------
$mongoRunning = Get-Process -Name "mongod" -ErrorAction SilentlyContinue
if ($mongoRunning) {
    Write-Host "[OK]  MongoDB is already running." -ForegroundColor Green
} else {
    if (Test-Path $MONGOD) {
        if (-not (Test-Path $MONGO_DATA)) {
            New-Item -ItemType Directory -Path $MONGO_DATA | Out-Null
        }
        Write-Host "[...] Starting MongoDB..." -ForegroundColor Cyan
        Start-Process -FilePath $MONGOD -ArgumentList "--dbpath", $MONGO_DATA -WindowStyle Minimized
        Start-Sleep -Seconds 3
        Write-Host "[OK]  MongoDB started." -ForegroundColor Green
    } else {
        Write-Host "[WARN] mongod.exe not found. Expected: $MONGOD" -ForegroundColor Yellow
    }
}

# -- 4. Install Python dependencies ------------------------------
Write-Host "[...] Installing Python dependencies..." -ForegroundColor Cyan
$reqFile = Join-Path $BACKEND "requirements.txt"
pip install -r $reqFile --quiet
Write-Host "[OK]  Dependencies ready." -ForegroundColor Green

# -- 5. Start FastAPI backend ------------------------------------
Write-Host "[...] Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Cyan
$backendJob = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--reload" `
    -WorkingDirectory $BACKEND `
    -PassThru -WindowStyle Normal

Start-Sleep -Seconds 3
Write-Host "[OK]  Backend running (PID $($backendJob.Id))." -ForegroundColor Green

# -- 6. Open Frontend --------------------------------------------
$indexHtml = Join-Path $FRONTEND "index.html"
Write-Host "[...] Opening UI in browser..." -ForegroundColor Cyan
Start-Process $indexHtml
Write-Host "[OK]  Frontend opened." -ForegroundColor Green

Write-Host ""
Write-Host "  =============================================" -ForegroundColor DarkCyan
Write-Host "  Platform is ready!" -ForegroundColor Green
Write-Host "  API  -> http://localhost:8000" -ForegroundColor White
Write-Host "  Docs -> http://localhost:8000/docs" -ForegroundColor White
Write-Host "  UI   -> $indexHtml" -ForegroundColor White
Write-Host "  =============================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  Press Ctrl+C in the backend window to stop." -ForegroundColor DarkGray
Write-Host ""
