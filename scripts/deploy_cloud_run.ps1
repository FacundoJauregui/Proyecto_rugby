param(
  [Parameter(Mandatory=$true)][string]$Project,
  [Parameter(Mandatory=$true)][string]$Region,
  [Parameter(Mandatory=$true)][string]$Repo,          # Artifact Registry repo name
  [Parameter(Mandatory=$true)][string]$Service,       # Cloud Run service name
  [Parameter(Mandatory=$true)][string]$ImageName,     # e.g. sportframe
  [string]$Tag = (Get-Date -Format 'yyyyMMdd-HHmmss'), # default timestamp tag
  [string]$ConnectionName = "",                      # optional: <project>:<region>:<instance>
  [string]$EnvVars = "",                              # optional: cadena --set-env-vars KEY=VAL,KEY2=VAL2
  [switch]$NoCache,
  [switch]$AllowUnauthenticated = $true,
  [switch]$DeployOnly,                                 # Solo despliega, no build/push
  [switch]$FromService                                 # Reusa la imagen actual del servicio
)

# --- Normalización y fallback de Tag ---
if (-not $Tag -or $Tag.Trim() -eq "") {
  $Tag = (Get-Date -Format 'yyyyMMdd-HHmmss')
  Write-Host "Tag vacío; usando tag generado: $Tag" -ForegroundColor Yellow
}
# Convertir a minúsculas y reemplazar caracteres inválidos por '-'
$cleanTag = $Tag.ToLower() -replace '[^a-z0-9_.-]', '-'
if ($cleanTag -ne $Tag) {
  Write-Host "Tag normalizado de '$Tag' a '$cleanTag'" -ForegroundColor DarkYellow
  $Tag = $cleanTag
}
if ($Tag.EndsWith(':')) {
  # Si accidentalmente queda un ':' final, lo quitamos.
  $Tag = $Tag.TrimEnd(':')
  Write-Host "Removido ':' sobrante en tag. Nuevo tag: $Tag" -ForegroundColor DarkYellow
}
if ($Tag -eq "") {
  throw "El tag final quedó vacío tras normalización. Proporciona un valor válido (ej: v2025-11-18)."
}

# Si se solicita reutilizar la imagen actual del servicio, la resolvemos primero
if ($FromService) {
  Write-Host "Obteniendo imagen actual de Cloud Run para '$Service'..." -ForegroundColor Yellow
  $currentImage = (gcloud run services describe $Service --region $Region --format="value(spec.template.spec.containers[0].image)" 2>$null)
  if (-not $currentImage) { throw "No se pudo obtener la imagen actual del servicio. Verificá permisos/nombre/región." }
  $global:ImageUri = $currentImage
  $DeployOnly = $true
} else {
  # Compose image URI con Project/Repo/ImageName:Tag
  $global:ImageUri = "${Region}-docker.pkg.dev/${Project}/${Repo}/${ImageName}:${Tag}"
}
Write-Host "Imagen destino: $ImageUri" -ForegroundColor Cyan

if (-not $DeployOnly) {
  # Ensure docker is authenticated for Artifact Registry in this region
  Write-Host "Autenticando Docker contra Artifact Registry ($Region)..."
  gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet
  if ($LASTEXITCODE -ne 0) { throw "Fallo configure-docker" }

  # Build image
  $buildArgs = @('build','-t', $ImageUri, '.')
  if ($NoCache) { $buildArgs = @('build','--no-cache','-t', $ImageUri, '.') }
  Write-Host "Construyendo imagen..." -ForegroundColor Yellow
  & docker $buildArgs
  if ($LASTEXITCODE -ne 0) { throw "Fallo docker build" }

  # Push image
  Write-Host "Pushing $ImageUri..." -ForegroundColor Yellow
  & docker push $ImageUri
  if ($LASTEXITCODE -ne 0) { throw "Fallo docker push" }
} else {
  Write-Host "Modo DeployOnly: no se construye ni se hace push; se reutiliza la imagen existente" -ForegroundColor DarkYellow
}

# Deploy/update Cloud Run
$argsList = @(
  'run','deploy', $Service,
  "--image=$ImageUri",
  "--region=$Region",
  '--platform=managed'
)
if ($AllowUnauthenticated) { $argsList += '--allow-unauthenticated' }
if ($ConnectionName) { $argsList += "--add-cloudsql-instances=$ConnectionName" }
if ($EnvVars -and $EnvVars.Trim() -ne "") { $argsList += "--set-env-vars=$EnvVars" }

Write-Host "Desplegando a Cloud Run servicio '$Service'..." -ForegroundColor Yellow
Write-Host ("gcloud " + ($argsList -join ' '))
& gcloud @argsList
if ($LASTEXITCODE -ne 0) {
  throw "Fallo gcloud run deploy"
}

Write-Host "Despliegue OK. Imagen activa: $ImageUri" -ForegroundColor Green
