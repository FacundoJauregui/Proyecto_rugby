from django.db import models

# Create your models here.
class Match(models.Model):
    # Usaremos un campo con opciones para saber qué tipo de partido es.
    class MatchType(models.TextChoices):
        RIVAL_ANALYSIS = 'RIVAL', 'Análisis de Rivales'
        TEAM_ANALYSIS = 'TEAM', 'Análisis Propio'

    video_id = models.CharField(max_length=20, unique=True, help_text="El ID único del video de YouTube (ej: 'dQw4w9WgXcQ')")
    title = models.CharField(max_length=200, help_text="Un título para identificar el partido")
    match_type = models.CharField(
        max_length=5,
        choices=MatchType.choices,
        default=MatchType.RIVAL_ANALYSIS,
        help_text="Define el tipo de análisis para este partido"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"({self.get_match_type_display()}) {self.title}"

    class Meta:
        verbose_name = "Partido"
        verbose_name_plural = "Partidos"
        
# Modelo EXACTO para las jugadas de ANÁLISIS DE RIVALES según tu CSV
class RivalPlay(models.Model):
    # Relación con el partido al que pertenece
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='rival_plays')

    # Mapeo de las columnas del CSV
    row_name = models.CharField(max_length=255, verbose_name="Row Name")
    clip_start = models.FloatField(verbose_name="Clip Start", help_text="Segundo de inicio del clip")
    clip_end = models.FloatField(verbose_name="Clip End", help_text="Segundo de fin del clip")
    jersey = models.IntegerField(verbose_name="JERSEY", null=True, blank=True)
    player_id = models.CharField(max_length=100, verbose_name="PlayerID", blank=True)
    nombre = models.CharField(max_length=255, verbose_name="NOMBRE", blank=True)
    equipo = models.CharField(max_length=255, verbose_name="EQUIPO", blank=True)
    team_id = models.CharField(max_length=100, verbose_name="TeamID", blank=True)
    fecha = models.CharField(max_length=100, verbose_name="FECHA", blank=True) # Usamos CharField por flexibilidad de formato
    tantos = models.IntegerField(verbose_name="TANTOS", null=True, blank=True)
    resultado = models.CharField(max_length=255, verbose_name="RESULTADO", blank=True)
    action = models.CharField(max_length=255, verbose_name="ACTION", blank=True)
    axis_tiempo = models.CharField(max_length=100, verbose_name="AXIS TIEMPO", blank=True)
    axis_x = models.FloatField(verbose_name="AXIS X", null=True, blank=True)
    axis_y = models.FloatField(verbose_name="AXIS Y", null=True, blank=True)
    end = models.CharField(max_length=255, verbose_name="END", blank=True)
    try_orig = models.CharField(max_length=255, verbose_name="TRYORIG", blank=True)
    li_for = models.CharField(max_length=255, verbose_name="LIFOR", blank=True)
    li_type = models.CharField(max_length=255, verbose_name="LITYPE", blank=True)
    li_place = models.CharField(max_length=255, verbose_name="LIPLACE", blank=True)
    li_jumper = models.CharField(max_length=255, verbose_name="LIJUMPER", blank=True)
    li_delivery = models.CharField(max_length=255, verbose_name="LIDELIVERY", blank=True)
    time = models.CharField(max_length=100, verbose_name="TIME", blank=True)
    mins = models.IntegerField(verbose_name="Mins", null=True, blank=True)
    ruck_start = models.FloatField(verbose_name="RUCKSTART", null=True, blank=True)
    ruck_end = models.FloatField(verbose_name="RUCKEND", null=True, blank=True)


    def __str__(self):
        return self.row_name

    class Meta:
        verbose_name = "Jugada de Rival"
        verbose_name_plural = "Jugadas de Rivales"