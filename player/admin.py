# player/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Match, Play, Team, Profile

# --- Configuración para el modelo User y Profile ---
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'perfiles'

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

# Re-registramos el modelo User para que muestre el Perfil adentro
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# --- Configuración para el resto de los modelos ---

# Para PlayInline, que se usa dentro de MatchAdmin
class PlayInline(admin.TabularInline):
    model = Play
    extra = 0
    readonly_fields = ('evento', 'equipo', 'inicia', 'termina')
    can_delete = False
    max_num = 0

# Registramos Match usando el decorador que ya tenías
@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'video_id', 'created_at')
    inlines = [PlayInline]

# Registramos Play usando el decorador
@admin.register(Play)
class PlayAdmin(admin.ModelAdmin):
    list_display = ('evento', 'match', 'equipo', 'inicia', 'termina')
    list_filter = ('match', 'equipo')
    search_fields = ('evento', 'equipo')

# Registramos Team de forma simple, ya que no tiene personalización
admin.site.register(Team)