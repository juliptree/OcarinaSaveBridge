$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.build-venv/Scripts/python.exe')) {
    py -3.14 -m venv --without-pip .build-venv
    if ($LASTEXITCODE) { throw 'Python 3.14 venv creation failed' }
}
python -m pip --python .build-venv/Scripts/python.exe install -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
.build-venv/Scripts/python.exe build.py
if ($LASTEXITCODE) { throw 'Build or validation failed' }
