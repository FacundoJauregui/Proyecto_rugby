# player/admin.py

from django.contrib import admin
from .models import Match, Play # Importamos el modelo unificado 'Play'

# Esto permite ver las jugadas directamente desde la vista del partido
class PlayInline(admin.TabularInline):
    model = Play
    extra = 0 # No mostramos formularios de jugadas nuevas vacíos por defecto
    readonly_fields = ('evento', 'equipo', 'inicia', 'termina') # Campos que no se editan a mano aquí
    can_delete = False
    max_num = 0

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin): # La corrección es admin.ModelAdmin
    list_display = ('__str__', 'video_id', 'created_at') # Usamos __str__ para mostrar "Equipo vs Equipo"
    inlines = [PlayInline]

@admin.register(Play)
class PlayAdmin(admin.ModelAdmin): # <-- Y aquí también
    list_display = ('evento', 'match', 'equipo', 'inicia', 'termina')
    list_filter = ('match', 'equipo')
    search_fields = ('evento', 'equipo') # Agrega una barra de búsqueda