param(
  [string]$LocalHost = "localhost",
  [int]$LocalPort = 5432,
  [string]$LocalUser = "postgres",
  [string]$LocalDb   = "rugby_player_db",
  [string]$DumpPath  = "",

  # Proxy de Cloud SQL ya iniciado antes de ejecutar este script
  [string]$CloudProxyHost = "127.0.0.1",
  [int]$CloudProxyPort = 5433,
  [string]$CloudDb   = "rugby_player_db",
  [string]$CloudUser = "postgres",

  # Passwords (si se omiten, se pedirán de forma interactiva y se usarán solo para la invocación)
  [string]$LocalPassword,
  [string]$CloudPassword,

  # Concede permisos a un usuario de aplicación luego de restaurar
  [switch]$GrantAppUser,
  [string]$AppUser = "appuser",

  # (Opcional) Ruta a la carpeta bin de PostgreSQL que contiene pg_dump/pg_restore/psql
  [string]$PgBinPath = ""
)

function Ensure-Cli {
  param([string]$name)
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $cmd) {
    # Si pasaron PgBinPath, lo agregamos temporalmente al PATH y reintentamos
    if ($PgBinPath -and (Test-Path $PgBinPath)) {
      $env:PATH = "$PgBinPath;" + $env:PATH
      $cmd = Get-Command $name -ErrorAction SilentlyContinue
      if ($cmd) { return }
    }

    # Auto-detección de rutas comunes en Windows
    $commonRoots = @(
      "C:\\Program Files\\PostgreSQL",
      "C:\\Program Files (x86)\\PostgreSQL"
    )
    $versions = 18..12  # probar varias versiones posibles
    foreach ($root in $commonRoots) {
      foreach ($v in $versions) {
        $bin = Join-Path (Join-Path $root $v) 'bin'
        $exe = Join-Path $bin ("$name.exe")
        if (Test-Path $exe) {
          $env:PATH = "$bin;" + $env:PATH
          $cmd = Get-Command $name -ErrorAction SilentlyContinue
          if ($cmd) { return }
        }
      }
    }
    throw "No se encontró '$name' en PATH. Instalá PostgreSQL client tools o pasá -PgBinPath 'C:\\Program Files\\PostgreSQL\\17\\bin'"
  }
}

function Read-PasswordIfEmpty {
  param([string]$current, [string]$prompt)
  if ($current) { return $current }
  $secure = Read-Host -AsSecureString -Prompt $prompt
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

try {
  Ensure-Cli pg_dump
  Ensure-Cli pg_restore
  Ensure-Cli psql

  if (-not $DumpPath -or $DumpPath.Trim() -eq "") {
    $ts = Get-Date -Format 'yyyyMMdd-HHmm'
    $outDir = Join-Path (Get-Location) 'backups'
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
    $DumpPath = Join-Path $outDir ("${LocalDb}_${ts}.backup")
  }

  Write-Host "Creando dump personalizado (-Fc) desde $LocalDb -> $DumpPath" -ForegroundColor Cyan
  $lp = Read-PasswordIfEmpty -current $LocalPassword -prompt "Password local para usuario $LocalUser"
  $old = $env:PGPASSWORD; $env:PGPASSWORD = $lp
  try {
    & pg_dump -h $LocalHost -p $LocalPort -U $LocalUser -d $LocalDb -Fc -f $DumpPath
    if ($LASTEXITCODE -ne 0) { throw "pg_dump falló" }
  } finally {
    $env:PGPASSWORD = $old
  }

  Write-Host "Probando conexión al proxy de Cloud SQL en ${CloudProxyHost}:${CloudProxyPort}..." -ForegroundColor Yellow
  $cp = Read-PasswordIfEmpty -current $CloudPassword -prompt "Password Cloud SQL para usuario $CloudUser"
  $old2 = $env:PGPASSWORD; $env:PGPASSWORD = $cp
  try {
    & psql "host=$CloudProxyHost port=$CloudProxyPort dbname=$CloudDb user=$CloudUser sslmode=disable" -c "SELECT 1;" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo conectar a Cloud SQL vía proxy. ¿Está corriendo el proxy?" }
  } finally { $env:PGPASSWORD = $old2 }

  Write-Host "Restaurando dump en Cloud SQL ($CloudDb) con --clean --if-exists --no-owner --no-privileges" -ForegroundColor Cyan
  $env:PGPASSWORD = $cp
  try {
    & pg_restore -h $CloudProxyHost -p $CloudProxyPort -U $CloudUser -d $CloudDb --no-owner --no-privileges --clean --if-exists -j 2 $DumpPath
    if ($LASTEXITCODE -ne 0) { throw "pg_restore falló" }
  } finally { $env:PGPASSWORD = $old2 }

  if ($GrantAppUser) {
    Write-Host "Otorgando permisos a '$AppUser'..." -ForegroundColor Yellow
    $sql = @(
      "GRANT CONNECT ON DATABASE $CloudDb TO $AppUser;",
      "GRANT USAGE ON SCHEMA public TO $AppUser;",
      "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $AppUser;",
      "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO $AppUser;",
      "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $AppUser;",
      "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO $AppUser;"
    )
    $env:PGPASSWORD = $cp
    try {
      foreach ($q in $sql) {
        & psql "host=$CloudProxyHost port=$CloudProxyPort dbname=$CloudDb user=$CloudUser sslmode=disable" -c $q
        if ($LASTEXITCODE -ne 0) { throw "Fallo al ejecutar: $q" }
      }
    } finally { $env:PGPASSWORD = $old2 }
  }

  Write-Host "Dump y restore completados correctamente." -ForegroundColor Green
  Write-Host "Archivo generado: $DumpPath" -ForegroundColor Green
}
catch {
  Write-Error $_
  exit 1
}
