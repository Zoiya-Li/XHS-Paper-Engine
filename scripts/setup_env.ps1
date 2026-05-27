$ErrorActionPreference = "Stop"

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonBin = $env:PYTHON_BIN
if (-not $PythonBin) { $PythonBin = "python" }
$VenvDir = $env:VENV_DIR
if (-not $VenvDir) { $VenvDir = Join-Path $ProjectDir ".venv" }

$WithPoppler = $false
$WithJava = $false
foreach ($arg in $args) {
  if ($arg -eq "--with-poppler") { $WithPoppler = $true }
  if ($arg -eq "--with-java") { $WithJava = $true }
  if ($arg -eq "--all") { $WithPoppler = $true; $WithJava = $true }
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

if ($WithJava) {
  # Figure extraction (pdffigures2) needs a Java runtime.
  if (Get-Command choco -ErrorAction SilentlyContinue) {
    choco install temurin -y
  } else {
    Write-Host "==> Please install a Java runtime (JRE 11+) manually (e.g. Adoptium Temurin)."
  }
  Write-Host "==> NOTE: also place the pdffigures2 fat JAR at ~/.xhs-paper-engine/pdffigures2.jar"
  Write-Host "==>       (build it via scripts/build_pdffigures2_jar.sh, or see the README)."
}

Write-Host "==> Done."
