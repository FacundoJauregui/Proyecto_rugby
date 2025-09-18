# player/models.py
from django.db import models
from django.contrib.auth.models import User 
from django.db.models.signals import post_save
from django.dispatch import receiver

class Match(models.Model):
    # Quitamos 'title' y agregamos los equipos
    home_team = models.CharField(max_length=100, verbose_name="Equipo Local", db_index=True)
    away_team = models.CharField(max_length=100, verbose_name="Equipo Visitante", db_index=True)
    
    video_id = models.CharField(max_length=20, unique=True, help_text="El ID único del video de YouTube")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Nueva fecha real del partido (opcional)
    match_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="Fecha del Partido")

    # La función __str__ ahora combina los nombres de los equipos
    def __str__(self):
        return f"{self.home_team} vs. {self.away_team}"

    class Meta:
        verbose_name = "Partido"
        verbose_name_plural = "Partidos"
        # Orden por defecto (recientes primero)
        ordering = ['-created_at']
        # Evitar que los equipos sean iguales
        constraints = [
            models.CheckConstraint(
                name='match_teams_distinct',
                check=~models.Q(home_team=models.F('away_team')),
            )
        ]

# Modelo de Jugada ÚNICO Y UNIFICADO
class Play(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='plays')

    # --- CAMPOS DE TIEMPO ---
    # Usamos Decimal con milisegundos para evitar errores de punto flotante.
    inicio = models.DecimalField(max_digits=9, decimal_places=3, verbose_name="INICIO (segundos)", help_text="Segundo exacto de inicio (ms)")
    fin = models.DecimalField(max_digits=9, decimal_places=3, verbose_name="FIN (segundos)", help_text="Segundo exacto de fin (ms)")
    
    # --- RESTO DE LOS CAMPOS ---
    arbitro = models.CharField(max_length=255, blank=True, verbose_name="Arbitro")
    canal_inicio = models.CharField(max_length=100, blank=True, verbose_name="CANAL INICIO")
    evento = models.CharField(max_length=255, blank=True, verbose_name="EVENTO", db_index=True)
    equipo = models.CharField(max_length=255, blank=True, verbose_name="Equipo", db_index=True)
    ficha = models.CharField(max_length=100, blank=True, verbose_name="Ficha")
    inicia = models.CharField(max_length=100, blank=True, verbose_name="INICIA", db_index=True)
    resultado = models.CharField(max_length=100, blank=True, verbose_name="Resultado")
    termina = models.CharField(max_length=100, blank=True, verbose_name="TERMINA")
    tiempo = models.CharField(max_length=50, blank=True, verbose_name="TIEMPO") # Este lo dejamos como texto por si tiene otro uso
    torneo = models.CharField(max_length=255, blank=True, verbose_name="Torneo")
    zona_fin = models.CharField(max_length=100, blank=True, verbose_name="ZONA FIN", db_index=True)
    zona_inicio = models.CharField(max_length=100, blank=True, verbose_name="ZONA INICIO", db_index=True)

    # --- NUEVOS CAMPOS SEGÚN CSV ---
    situacion = models.CharField(max_length=100, blank=True, verbose_name="SITUACION", db_index=True)
    jugadores = models.CharField(max_length=255, blank=True, verbose_name="JUGADORES")
    sigue_con = models.CharField(max_length=255, blank=True, verbose_name="SIGUE CON")
    pos_tiro = models.CharField(max_length=100, blank=True, verbose_name="POS TIRO")
    set_play = models.CharField(max_length=100, blank=True, verbose_name="SET", db_index=True)
    tiro = models.CharField(max_length=100, blank=True, verbose_name="TIRO")
    tipo = models.CharField(max_length=100, blank=True, verbose_name="TIPO", db_index=True)
    accion = models.CharField(max_length=100, blank=True, verbose_name="ACCION", db_index=True)
    termina_en = models.CharField(max_length=100, blank=True, verbose_name="TERMINA EN", db_index=True)
    sancion = models.CharField(max_length=100, blank=True, verbose_name="SANCION", db_index=True)
    transicion = models.CharField(max_length=100, blank=True, verbose_name="TRANSICION", db_index=True)

    def __str__(self):
        return f"{self.evento} - {self.equipo}"

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
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Equipo")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        
class Profile(models.Model):
    class Role(models.TextChoices):
        ENTRENADOR = 'COACH', 'Entrenador'
        JUGADOR = 'PLAYER', 'Jugador'

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Equipo")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.ENTRENADOR, verbose_name="Rol")

    def __str__(self):
        return f"Perfil de {self.user.username}"

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfiles"

# Crear perfil automáticamente al crear un usuario y mantenerlo sincronizado
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()