# Script PowerShell para activar entorno y correr FastAPI con Uvicorn
# Uso: haz doble clic o ejecuta en PowerShell: ./run_backend.ps1

$env:VIRTUAL_ENV = "$PSScriptRoot\venv311"
$env:PATH = "$env:VIRTUAL_ENV\Scripts;" + $env:PATH

Write-Host "[INFO] Entorno virtual activado: $env:VIRTUAL_ENV"

# Instalar dependencias si faltan
pip install --upgrade pip
pip install -r requirements.txt

# Lanzar el backend
python -m uvicorn main:app --reload
