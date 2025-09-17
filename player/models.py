# player/models.py
from django.db import models

class Match(models.Model):
    # Quitamos 'title' y agregamos los equipos
    home_team = models.CharField(max_length=100, verbose_name="Equipo Local")
    away_team = models.CharField(max_length=100, verbose_name="Equipo Visitante")
    
    video_id = models.CharField(max_length=20, unique=True, help_text="El ID único del video de YouTube")
    created_at = models.DateTimeField(auto_now_add=True)

    # La función __str__ ahora combina los nombres de los equipos
    def __str__(self):
        return f"{self.home_team} vs. {self.away_team}"

    class Meta:
        verbose_name = "Partido"
        verbose_name_plural = "Partidos"

# Modelo de Jugada ÚNICO Y UNIFICADO
class Play(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='plays')

    # --- CAMPOS DE TIEMPO CORREGIDOS ---
    # Guardamos los segundos totales como un número flotante para máxima precisión.
    inicio = models.FloatField(verbose_name="INICIO (segundos)", help_text="Segundo exacto de inicio")
    fin = models.FloatField(verbose_name="FIN (segundos)", help_text="Segundo exacto de fin")
    
    # --- RESTO DE LOS CAMPOS ---
    arbitro = models.CharField(max_length=255, blank=True, verbose_name="Arbitro")
    canal_inicio = models.CharField(max_length=100, blank=True, verbose_name="CANAL INICIO")
    evento = models.CharField(max_length=255, blank=True, verbose_name="EVENTO")
    equipo = models.CharField(max_length=255, blank=True, verbose_name="Equipo")
    ficha = models.CharField(max_length=100, blank=True, verbose_name="Ficha")
    inicia = models.CharField(max_length=100, blank=True, verbose_name="INICIA")
    resultado = models.CharField(max_length=100, blank=True, verbose_name="Resultado")
    termina = models.CharField(max_length=100, blank=True, verbose_name="TERMINA")
    tiempo = models.CharField(max_length=50, blank=True, verbose_name="TIEMPO") # Este lo dejamos como texto por si tiene otro uso
    torneo = models.CharField(max_length=255, blank=True, verbose_name="Torneo")
    zona_fin = models.CharField(max_length=100, blank=True, verbose_name="ZONA FIN")
    zona_inicio = models.CharField(max_length=100, blank=True, verbose_name="ZONA INICIO")

    def __str__(self):
        return f"{self.evento} - {self.equipo}"

    class Meta:
        verbose_name = "Jugada"
        verbose_name_plural = "Jugadas"