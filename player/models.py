"""Modelos centrales de la aplicación `player`.

Este módulo define las entidades principales usadas en el dominio de análisis de
partidos y jugadas de rugby, además de perfiles de usuario y configuraciones
auxiliares. Cada clase está documentada en detalle para facilitar el
mantenimiento y la lectura del código.

Resumen rápido de entidades:
 - Country: Catálogo de países (origen de torneos / equipos internacionales).
 - Tournament: Representa un torneo o competición en una temporada específica.
 - Match: Un partido concreto entre dos equipos, vinculado opcionalmente a un torneo.
 - Play: Unidad mínima de análisis dentro de un partido (fragmentos temporales con metadata).
 - Team: Catálogo de equipos (club / selección) usados para perfiles y participaciones.
 - Profile: Extensión del modelo User para asociar rol y equipo principal.
 - CoachTournamentTeamParticipation: Asigna qué equipo dirige un entrenador en un torneo.
 - SelectionPreset: Permite guardar selecciones de jugadas para reutilización/compartir.
"""

from django.db import models
from django.contrib.auth.models import User 
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

class Country(models.Model):
    """Catálogo de países.

    Se usa para normalizar referencias de origen de torneos y potencialmente
    para filtrar datos por región. El `slug` puede emplearse en URLs amigables.
    """
    # Nombre oficial del país (único para evitar duplicados).
    name = models.CharField(max_length=100, unique=True, verbose_name="País")
    # Código ISO de 2 o 3 letras si existiera (único). Permite integraciones externas.
    iso_code = models.CharField(max_length=3, blank=True, null=True, unique=True, verbose_name="ISO (2/3)")
    # Slug opcional para uso en rutas limpias / SEO.
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        verbose_name = "País"
        verbose_name_plural = "Países"
        ordering = ['name']

    def __str__(self):
        return self.name


class Tournament(models.Model):
    """Representa una competición específica.

    Combina país + nombre + temporada para garantizar unicidad (evita duplicar
    instancias cuando el mismo torneo se disputa en varias temporadas).
    `short_name` facilita mostrar siglas en interfaces (por ejemplo, "URBA").
    """
    name = models.CharField(max_length=150, verbose_name="Torneo")
    # País anfitrión / sede. PROTECT para evitar borrar países con torneos existentes.
    country = models.ForeignKey('player.Country', on_delete=models.PROTECT, related_name='tournaments', verbose_name="País")
    # Temporada textual (ej: 2024 o 2024/25). Indexada porque es usada en filtros frecuentes.
    season = models.CharField(max_length=20, blank=True, db_index=True, verbose_name="Temporada")  # ej: 2024 o 2024/25
    # Nivel competitivo / categoría (ej: Primera A, Reserva, etc.).
    level = models.CharField(max_length=100, blank=True, verbose_name="Nivel/Categoría")
    # Siglas abreviadas para UI compacta.
    short_name = models.CharField(max_length=50, blank=True, verbose_name="Torneo abreviado (siglas)")

    class Meta:
        verbose_name = "Torneo"
        verbose_name_plural = "Torneos"
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['name', 'country', 'season'], name='uniq_tournament_country_season')
        ]

    def __str__(self):
        if self.season:
            return f"{self.name} {self.season} ({self.country})"
        return f"{self.name} ({self.country})"


class Match(models.Model):
    """Partido específico entre dos equipos.

    Incluye referencia opcional a un `Tournament` (se mantiene opcional por compatibilidad
    con datos históricos). El `video_id` enlaza la fuente multimedia (YouTube) sobre la
    cual se indexan las jugadas (`Play`).
    """
    # Equipo local en mayúsculas normalizado al guardar (ver `save`). Indexado para búsqueda.
    home_team = models.CharField(max_length=100, verbose_name="Equipo Local", db_index=True)
    # Equipo visitante. También normalizado / indexado.
    away_team = models.CharField(max_length=100, verbose_name="Equipo Visitante", db_index=True)
    # Identificador único de la fuente de video (YouTube u otro). Permite localizar el recurso.
    video_id = models.CharField(max_length=20, unique=True, help_text="El ID único del video de YouTube")
    # Timestamp de creación del registro (cuando se cargó en la plataforma).
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Fecha real en que se disputó el partido. Indexada para filtros cronológicos.
    match_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="Fecha del Partido")
    # Referencia opcional al torneo. SET_NULL evita pérdida de partido si se elimina el torneo.
    tournament = models.ForeignKey('player.Tournament', on_delete=models.SET_NULL, null=True, blank=True, related_name='matches', verbose_name="Torneo")
    # División / categoría competitiva interna.
    class Division(models.TextChoices):
        PRIMERA = 'PRIMERA', 'Primera'
        RESERVA = 'RESERVA', 'Reserva'
        PRE_A = 'PRE_A', 'Pre A'
        PRE_B = 'PRE_B', 'Pre B'

    division = models.CharField(
        max_length=20,
        choices=Division.choices,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="División"
    )

    def __str__(self):  # Representación humana en admin y logs.
        return f"{self.home_team} vs. {self.away_team}"

    class Meta:
        verbose_name = "Partido"
        verbose_name_plural = "Partidos"
        # Orden por defecto (recientes primero)
        ordering = ['-created_at']
        # Evitar que los equipos sean iguales y evitar duplicados por fecha
        constraints = [
            models.CheckConstraint(
                name='match_teams_distinct',
                check=~models.Q(home_team=models.F('away_team')),
            ),
            models.UniqueConstraint(
                fields=['home_team', 'away_team', 'match_date'],
                name='match_unique_teams_date'
            ),
        ]

    def save(self, *args, **kwargs):
        """Normaliza nombres de equipo a MAYÚSCULAS.

        Esta limpieza asegura consistencia para filtros y evita duplicados
        por diferencias de casing. Se ejecuta antes de persistir.
        """
        if self.home_team:
            self.home_team = self.home_team.strip().upper()
        if self.away_team:
            self.away_team = self.away_team.strip().upper()
        super().save(*args, **kwargs)

# Modelo de Jugada ÚNICO Y UNIFICADO
class Play(models.Model):
    """Unidad mínima de análisis dentro de un `Match`.

    Representa un fragmento temporal etiquetado con atributos cualitativos y
    cuantitativos (inicio / fin en segundos, evento, zona, participantes, etc.).
    Muchos campos son opcionales y dependen de la granularidad del análisis.
    El conjunto de índices + constraints favorece consultas rápidas y calidad de datos.
    """
    # Relación fuerte con el partido: CASCADE porque si se borra el partido, las jugadas pierden contexto.
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='plays')

    # Atributos descriptivos (orden final pedido por CSV histórico):
    jugada = models.CharField(max_length=255, blank=True, verbose_name="Jugada")  # Nombre corto / etiqueta principal.
    arbitro = models.CharField(max_length=255, blank=True, verbose_name="Arbitro")  # Árbitro responsable de la acción.
    canal_de_inicio = models.CharField(max_length=100, blank=True, verbose_name="Canal de Inicio")  # Canal / origen táctico.
    evento = models.CharField(max_length=255, blank=True, verbose_name="Evento", db_index=True)  # Tipo general de evento.
    equipo = models.CharField(max_length=255, blank=True, verbose_name="Equipo", db_index=True)  # Equipo asociado.
    fin = models.DecimalField(max_digits=9, decimal_places=3, verbose_name="Fin (segundos)", help_text="Segundo exacto de fin (ms)")  # Marca temporal final.
    ficha = models.CharField(max_length=100, blank=True, verbose_name="Ficha")  # Referencia genérica (documento / etiqueta externa).
    inicia = models.CharField(max_length=100, blank=True, verbose_name="Inicia", db_index=True)  # Actor / rol que inicia.
    inicio = models.DecimalField(max_digits=9, decimal_places=3, verbose_name="Inicio (segundos)", help_text="Segundo exacto de inicio (ms)")  # Marca temporal inicial.
    marcador_final = models.CharField(max_length=50, blank=True, verbose_name="Marcador Final")  # Resultado inmediato de la jugada.
    termina = models.CharField(max_length=100, blank=True, verbose_name="Termina")  # Actor / rol que culmina.
    tiempo = models.CharField(max_length=50, blank=True, verbose_name="Tiempo")  # Periodización (1er tiempo / 2do, etc.).
    torneo = models.CharField(max_length=255, blank=True, verbose_name="Torneo")  # DEPRECADO: usar `match.tournament`.
    zona_fin = models.CharField(max_length=100, blank=True, verbose_name="Zona Fin", db_index=True)  # Ubicación final en el campo.
    zona_inicio = models.CharField(max_length=100, blank=True, verbose_name="Zona Inicio", db_index=True)  # Ubicación inicial.
    resultado = models.CharField(max_length=100, blank=True, verbose_name="Resultado")  # Resultado cualitativo.
    jugadores = models.CharField(max_length=255, blank=True, verbose_name="Jugadores")  # Lista de jugadores involucrados.
    sigue_con = models.CharField(max_length=255, blank=True, verbose_name="Sigue Con")  # Acción / jugada subsiguiente.
    pos_tiro = models.CharField(max_length=100, blank=True, verbose_name="Pos Tiro")  # Posición de tiro si aplica.
    set = models.CharField(max_length=100, blank=True, verbose_name="Set", db_index=True)  # Set / fase táctica.
    tiro = models.CharField(max_length=100, blank=True, verbose_name="Tiro")  # Tipo de tiro / lanzamiento.
    tipo = models.CharField(max_length=100, blank=True, verbose_name="Tipo", db_index=True)  # Clasificación general.
    accion = models.CharField(max_length=100, blank=True, verbose_name="Accion", db_index=True)  # Acción específica.
    termina_en = models.CharField(max_length=100, blank=True, verbose_name="Termina En", db_index=True)  # Resultado espacial final.
    sancion = models.CharField(max_length=100, blank=True, verbose_name="Sancion", db_index=True)  # Sanción asociada.
    situacion = models.CharField(max_length=100, blank=True, verbose_name="Situacion", db_index=True)  # Situación táctica.
    transicion = models.CharField(max_length=100, blank=True, verbose_name="Transicion", db_index=True)  # Tipo de transición.
    situacion_penal = models.CharField(max_length=100, blank=True, verbose_name="Situación Penal", db_index=True)  # Nuevo: detalle penal.
    nueva_categoria = models.CharField(max_length=100, blank=True, verbose_name="Nueva Categoría", db_index=True)  # Nuevo: clasificación complementaria.
    acercar = models.CharField(max_length=50, blank=True, verbose_name="Acercar")  # Flag / instrucción visual.
    alejar = models.CharField(max_length=50, blank=True, verbose_name="Alejar")  # Flag / instrucción visual.

    def __str__(self):  # Provee etiqueta rápida en listados.
        return f"{self.jugada} - {self.equipo}"

    class Meta:
        verbose_name = "Jugada"
        verbose_name_plural = "Jugadas"
        # Orden por defecto por inicio
        ordering = ['inicio']
        # Índices para acelerar consultas habituales
        indexes = [
            models.Index(fields=['match', 'inicio'], name='idx_play_match_inicio'),
            models.Index(fields=['evento'], name='idx_play_evento'),
            models.Index(fields=['equipo'], name='idx_play_equipo'),
            models.Index(fields=['zona_inicio'], name='idx_play_zona_inicio'),
            models.Index(fields=['zona_fin'], name='idx_play_zona_fin'),
            models.Index(fields=['inicia'], name='idx_play_inicia'),
            # Índices nuevos útiles
            models.Index(fields=['situacion'], name='idx_play_situacion'),
            models.Index(fields=['tipo'], name='idx_play_tipo'),
            models.Index(fields=['accion'], name='idx_play_accion'),
            models.Index(fields=['termina_en'], name='idx_play_termina_en'),
            models.Index(fields=['sancion'], name='idx_play_sancion'),
            models.Index(fields=['transicion'], name='idx_play_transicion'),
        ]
        # Reglas de integridad sobre tiempos
        constraints = [
            models.CheckConstraint(
                name='play_fin_gte_inicio',
                check=models.Q(fin__gte=models.F('inicio')),
            ),
            models.CheckConstraint(
                name='play_inicio_gte_0',
                check=models.Q(inicio__gte=0),
            ),
            models.CheckConstraint(
                name='play_fin_gte_0',
                check=models.Q(fin__gte=0),
            ),
        ]
        
class Team(models.Model):
    """Catálogo de equipos (clubes / selecciones).

    `alias` permite mostrar versiones abreviadas en tablas, overlays de video, etc.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Equipo")  # Nombre completo.
    alias = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="Alias/Nombre abreviado")  # Siglas opcionales.

    def __str__(self):  # Facilita visualización en admin.
        return self.name

    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        
class Profile(models.Model):
    """Extiende al usuario con rol y equipo principal.

    OneToOne para mantener una única ficha por usuario. `team` es opcional
    porque un entrenador puede gestionar múltiples equipos a través de
    `CoachTournamentTeamParticipation`.
    """
    class Role(models.TextChoices):
        ENTRENADOR = 'COACH', 'Entrenador'
        JUGADOR = 'PLAYER', 'Jugador'

    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Relación 1:1 fuerte.
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Equipo")  # Equipo principal (si aplica).
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.ENTRENADOR, verbose_name="Rol")  # Rol operativo.

    def __str__(self):  # Ayuda en listados admin.
        return f"Perfil de {self.user.username}"

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfiles"

# Crear perfil automáticamente al crear un usuario y mantenerlo sincronizado
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Crea el `Profile` automáticamente al generar un nuevo `User`.

    Se usa `get_or_create` para tolerar escenarios donde la creación pueda
    dispararse desde múltiples lugares (e.g., admin con inlines).
    """
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Garantiza que cambios en `User` propaguen persistencia en `Profile`.

    Evita estados inconsistentes si se modifican atributos relevantes en el usuario
    que deban reflejarse en el perfil (aunque por ahora no hay campos dependientes directos).
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()

class CoachTournamentTeamParticipation(models.Model):
    """Asignación de entrenador a equipo por temporada.

    Un entrenador dirige un único equipo en una temporada; ese equipo puede
    disputar múltiples torneos dentro de la misma temporada. Esta entidad se
    usa para filtrar la visibilidad de partidos según la temporada y el equipo.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coach_participations', verbose_name="Entrenador")
    season = models.CharField(max_length=20, db_index=True, verbose_name="Temporada")  # ej: 2024 o 2024/25
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='season_participations', verbose_name="Equipo")
    active = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Participación de Entrenador (Temporada)"
        verbose_name_plural = "Participaciones de Entrenadores (Temporada)"
        unique_together = ('user', 'season', 'team')
        ordering = ['user__username', 'season', 'team__name']

    def __str__(self):
        return f"{self.user.username} - {self.team.name} (Temp. {self.season})"

class SelectionPreset(models.Model):
    """Agrupa una selección personalizada de jugadas.

    Permite a un usuario guardar subconjuntos de `Play` para análisis repetido,
    presentaciones, clips o exportaciones. `play_ids` almacena una lista ordenada
    (intended) de IDs de jugadas para reconstruir rápidamente la selección.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='selection_presets')  # Propietario.
    match = models.ForeignKey('player.Match', on_delete=models.CASCADE, related_name='selection_presets')  # Partido origen.
    name = models.CharField(max_length=100)  # Nombre identificador único dentro del mismo usuario+partido.
    play_ids = models.JSONField(default=list)  # Lista de IDs de `Play` en orden significativo.
    created_at = models.DateTimeField(auto_now_add=True)  # Creación.
    updated_at = models.DateTimeField(auto_now=True)  # Última modificación.

    class Meta:
        unique_together = ('user', 'match', 'name')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.user.username} - match {self.match_id})"