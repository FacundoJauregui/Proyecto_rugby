# Actualizar imagen Docker y desplegar a Cloud Run (Windows / PowerShell)

Este flujo recompila la imagen, la sube a Artifact Registry y actualiza el servicio de Cloud Run.

## Script recomendado

Usá el script `scripts/deploy_cloud_run.ps1` para automatizar build → push → deploy.

### Parámetros
- `-Project`: ID del proyecto GCP (ej: `spheric-wonder-473601-a9`).
- `-Region`: región (ej: `southamerica-east1`).
- `-Repo`: nombre del repo en Artifact Registry (ej: `rugby-repo`).
- `-Service`: nombre del servicio de Cloud Run (ej: `sportframe`).
- `-ImageName`: nombre de la imagen (ej: `sportframe`).
- `-Tag`: (opcional) tag de la imagen, por defecto timestamp.
- `-ConnectionName`: (opcional) `<project>:<region>:<instance>` para adjuntar Cloud SQL.
- `-NoCache`: (opcional) fuerza build sin caché.
- `-AllowUnauthenticated`: (switch) por defecto activo; quitalo si no querés acceso público.
 - `-DeployOnly`: (switch) saltea build/push y solo despliega usando la imagen indicada (por `-Tag`).
 - `-FromService`: (switch) reutiliza la imagen actualmente configurada en el servicio (descubierta automáticamente) y no hace build/push.

### Ejemplo de uso

```powershell
# Variables
$Project = "spheric-wonder-473601-a9"
$Region  = "southamerica-east1"
$Repo    = "rugby-repo"
$Service = "sportframe"
$Image   = "sportframe"
$Conn    = "spheric-wonder-473601-a9:southamerica-east1:rugby-sql"  # opcional

# Build (sin cache), push y deploy con tag por timestamp
./scripts/deploy_cloud_run.ps1 -Project $Project -Region $Region -Repo $Repo -Service $Service -ImageName $Image -ConnectionName $Conn -NoCache
```

### Solo redeploy sin construir (reusar imagen existente)

- Reutilizando un tag existente (ej. `v1`):

```powershell
./scripts/deploy_cloud_run.ps1 -Project $Project -Region $Region -Repo $Repo -Service $Service -ImageName $Image -Tag "v1" -DeployOnly
```

- Reutilizando la imagen que ya usa el servicio (descubierta automáticamente):

```powershell
./scripts/deploy_cloud_run.ps1 -Project $Project -Region $Region -Repo $Repo -Service $Service -ImageName $Image -FromService
```

## Notas

- El Dockerfile está en la raíz del proyecto. Asegurate de que `requirements.txt` esté actualizado antes de reconstruir.
- El script hace `gcloud auth configure-docker` para la región automáticamente (solo cuando no usás `-DeployOnly`).
- Si necesitás setear variables de entorno del servicio (DB, SECRET, etc.), podés usar `gcloud run services update ... --update-env-vars` aparte o extender el script.
- Para limpiar imágenes antiguas en Artifact Registry, podés configurar políticas de limpieza o borrarlas manualmente.

### Troubleshooting (PowerShell)

- Error de sintaxis con `:` en la línea del ImageUri: PowerShell requiere delimitar variables cuando están seguidas por `:`. En el script ya usamos `${ImageName}:${Tag}` para evitar el error `InvalidVariableReferenceWithDrive`.
 - Si Docker o gcloud no están en PATH, abrí una nueva terminal después de instalarlos o agregalos al PATH.
