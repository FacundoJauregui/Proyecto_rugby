from django.contrib import admin
from .models import Match, RivalPlay
# Register your models here.

# player/admin.py

# Esto permite agregar/editar jugadas de rivales directamente desde la vista del partido
class RivalPlayInline(admin.TabularInline):
    model = RivalPlay
    extra = 0 # Para no mostrar formularios de jugadas nuevas vacíos
    readonly_fields = ('row_name', 'action', 'nombre', 'clip_start', 'clip_end') # Campos que no se editan a mano
    can_delete = False # Evita que se puedan borrar desde esta vista
    max_num = 0 # No permite agregar nuevas desde aquí

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('title', 'match_type', 'video_id', 'created_at')
    list_filter = ('match_type',)
    inlines = [RivalPlayInline]

@admin.register(RivalPlay)
class RivalPlayAdmin(admin.ModelAdmin):
    # Elegimos los campos más representativos para mostrar en la lista
    list_display = ('row_name', 'match', 'action', 'nombre', 'equipo', 'clip_start', 'clip_end')
    list_filter = ('match', 'equipo', 'action')
    search_fields = ('row_name', 'nombre', 'action') # Agrega una barra de búsqueda