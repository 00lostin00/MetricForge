param([int]$Port = 8014)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    uv run --frozen --all-extras uvicorn metricforge.api:app --host 127.0.0.1 --port $Port
} finally { Pop-Location }
