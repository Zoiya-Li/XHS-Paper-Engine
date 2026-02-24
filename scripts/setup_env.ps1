$ErrorActionPreference = "Stop"

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonBin = $env:PYTHON_BIN
if (-not $PythonBin) { $PythonBin = "python" }
$VenvDir = $env:VENV_DIR
if (-not $VenvDir) { $VenvDir = Join-Path $ProjectDir ".venv" }

$WithPoppler = $false
$WithDetectron2 = $false
foreach ($arg in $args) {
  if ($arg -eq "--with-poppler") { $WithPoppler = $true }
  if ($arg -eq "--with-detectron2") { $WithDetectron2 = $true }
  if ($arg -eq "--all") { $WithPoppler = $true; $WithDetectron2 = $true }
}

Write-Host "==> Project: $ProjectDir"
Write-Host "==> Python:  $PythonBin"
Write-Host "==> Venv:    $VenvDir"

& $PythonBin -m venv $VenvDir
$Activate = Join-Path $VenvDir "Scripts\\Activate.ps1"
. $Activate

python -m pip install --upgrade pip
pip install -r (Join-Path $ProjectDir "requirements.txt")
python -m playwright install chromium

$EnvFile = Join-Path $ProjectDir ".env"
$EnvExample = Join-Path $ProjectDir ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
  Copy-Item $EnvExample $EnvFile
  Write-Host "==> Created .env from .env.example (fill in your API keys)."
}

if ($WithPoppler) {
  if (Get-Command choco -ErrorAction SilentlyContinue) {
    choco install poppler -y
  } elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
    scoop install poppler
  } else {
    Write-Host "==> Please install poppler manually (pdftotext is required)."
  }
}

if ($WithDetectron2) {
  Write-Host "==> detectron2 source install is not automated on Windows."
  Write-Host "==> Recommendation: use WSL2 or follow the official detectron2 Windows guide."
}

Write-Host "==> Done."
