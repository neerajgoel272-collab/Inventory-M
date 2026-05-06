Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "== Smart Inventory runner =="

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "Creating venv (.venv) using Python 3.13..."
  py -3.13 -m venv .venv
}

Write-Host "Installing requirements..."
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path ".\.env")) {
  Write-Host "Creating .env from .env.example"
  Copy-Item ".\.env.example" ".\.env"
}

function Get-EnvValueFromFile([string]$path, [string]$key) {
  if (-not (Test-Path $path)) { return $null }
  $line = Get-Content $path | Where-Object { $_ -match ("^\s*" + [regex]::Escape($key) + "\s*=") } | Select-Object -First 1
  if (-not $line) { return $null }
  return ($line -split "=", 2)[1].Trim()
}

$port = Get-EnvValueFromFile ".\.env" "PORT"
if (-not $port) { $port = "5000" }

$listener = Get-NetTCPConnection -LocalPort ([int]$port) -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  Write-Host "PORT $port is already in use. Close the other running server or change PORT in .env."
  Write-Host ("Owning PID(s): " + (($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "))
  exit 1
}

Write-Host "Starting server..."
Write-Host "Running migrations..."
try {
  .\.venv\Scripts\python.exe -m flask --app app db upgrade
} catch {
  Write-Host "Migration upgrade failed. If this is an existing DB, stamping head and retrying..."
  .\.venv\Scripts\python.exe -m flask --app app db stamp head
  .\.venv\Scripts\python.exe -m flask --app app db upgrade
}

Write-Host "Seeding demo data (if empty)..."
.\.venv\Scripts\python.exe -m flask --app app seed-demo

.\.venv\Scripts\python.exe app.py

