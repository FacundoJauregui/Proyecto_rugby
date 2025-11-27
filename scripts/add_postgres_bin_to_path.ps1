param(
    [string]$PostgresBin = "",
    [switch]$Persist
)

# Try to auto-detect a PostgreSQL bin if not provided
if (-not $PostgresBin) {
    $defaultRoot = "C:\\Program Files\\PostgreSQL"
    if (Test-Path $defaultRoot) {
        $candidates = Get-ChildItem -Path $defaultRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        foreach ($dir in $candidates) {
            $binCandidate = Join-Path $dir.FullName "bin"
            if (Test-Path (Join-Path $binCandidate "pg_dump.exe")) {
                $PostgresBin = $binCandidate
                break
            }
        }
    }
}

if (-not $PostgresBin) {
    Write-Error "No se encontró una instalación de PostgreSQL. Instalá PostgreSQL 17 o el cliente y especificá -PostgresBin 'C:\\Program Files\\PostgreSQL\\17\\bin'"
    exit 1
}

if (-not (Test-Path (Join-Path $PostgresBin "pg_dump.exe"))) {
    Write-Error "No existe pg_dump.exe en '$PostgresBin'. Verificá la ruta o instalá PostgreSQL."
    exit 1
}

# Add to PATH for current session
if ($env:Path -notlike "*$PostgresBin*") {
    $env:Path = "$PostgresBin;" + $env:Path
    Write-Host "Agregado a PATH (sesión): $PostgresBin"
} else {
    Write-Host "PATH ya contiene: $PostgresBin"
}

# Optionally persist to User PATH
if ($Persist) {
    $userPath = [Environment]::GetEnvironmentVariable("Path","User")
    if ($userPath -notlike "*$PostgresBin*") {
        [Environment]::SetEnvironmentVariable("Path", "$PostgresBin;" + $userPath, "User")
        Write-Host "Agregado a PATH (usuario): $PostgresBin"
        Write-Host "Cerrá y reabrí PowerShell para que tome efecto."
    } else {
        Write-Host "PATH de usuario ya contiene: $PostgresBin"
    }
}

# Print versions
try {
    & (Join-Path $PostgresBin "pg_dump.exe") --version
    & (Join-Path $PostgresBin "pg_restore.exe") --version | Out-Null
} catch {
    Write-Warning "No se pudo ejecutar pg_dump/pg_restore. Verificá permisos."
}
