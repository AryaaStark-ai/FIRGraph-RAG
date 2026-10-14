# FIRGraph-RAG - prerequisite checker
# Run in PowerShell from the project folder:
#   powershell -ExecutionPolicy Bypass -File .\check_setup.ps1
# Then copy everything it prints and paste it into the chat.

function Check($name, $cmd) {
    try {
        $out = (Invoke-Expression $cmd 2>&1 | Select-Object -First 1)
        Write-Host ("[OK]      {0,-12} {1}" -f $name, $out) -ForegroundColor Green
    } catch {
        Write-Host ("[MISSING] {0,-12}" -f $name) -ForegroundColor Red
    }
}

Write-Host "`n=== FIRGraph-RAG setup check ===`n"
Check "Git"        "git --version"
Check "Python"     "python --version"
Check "pip"        "python -m pip --version"
Check "Node.js"    "node --version"
Check "npm"        "npm --version"
Check "Ollama"     "ollama --version"
Check "Docker"     "docker --version"
Check "Tesseract"  "tesseract --version"
Check "NVIDIA GPU" "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader"

# Node must be 20 or newer
try {
    $nv = (node --version).TrimStart('v').Split('.')[0]
    if ([int]$nv -lt 20) { Write-Host "  -> Node $nv is too old, need 20+" -ForegroundColor Yellow }
} catch {}

# Tesseract must have the Marathi language pack
try {
    $langs = tesseract --list-langs 2>&1
    if ($langs -match "^mar$") { Write-Host "  -> Tesseract Marathi (mar): installed" -ForegroundColor Green }
    else { Write-Host "  -> Tesseract Marathi (mar): MISSING" -ForegroundColor Yellow }
} catch {}

# Docker engine must actually be running, not just installed
try {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "  -> Docker engine: running" -ForegroundColor Green }
    else { Write-Host "  -> Docker engine: NOT running (open Docker Desktop)" -ForegroundColor Yellow }
} catch {}

# Ollama models already downloaded
try { Write-Host "`nOllama models:"; ollama list } catch {}

Write-Host "`n=== done - paste this output into the chat ===`n"
