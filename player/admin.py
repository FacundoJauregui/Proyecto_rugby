# player/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html
from urllib.parse import urlencode
from django.contrib import messages

from .models import Match, Play, Team, Profile

# --- Configuración para el modelo User y Profile ---
class ProfileInline(admin.StackedInline):
    model = Profile
    fk_name = 'user'
    can_delete = False
    verbose_name_plural = 'perfiles'
    extra = 0
    max_num = 1

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

# Re-registramos el modelo User para que muestre el Perfil adentro
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# --- Configuración para el resto de los modelos ---

# Eliminamos el inline pesado de Play para mejorar la UX y evitar TooManyFieldsSent
# class PlayInline(admin.TabularInline):
#     model = Play
#     extra = 0
#     readonly_fields = ('evento', 'equipo', 'inicia', 'termina')
#     can_delete = False
#     max_num = 0

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'video_id', 'match_date', 'created_at', 'plays_count', 'ver_jugadas', 'eliminar')
    search_fields = ('home_team', 'away_team', 'video_id')
    list_filter = ('match_date', 'created_at')
    fields = ('home_team', 'away_team', 'video_id', 'match_date')
    actions = ['delete_matches_and_plays']

    def plays_count(self, obj):
        return obj.plays.count()
    plays_count.short_description = 'Jugadas'

    def ver_jugadas(self, obj):
        url = reverse('admin:player_play_changelist')
        params = urlencode({'match__id__exact': obj.pk})
        return format_html('<a href="{}?{}">Ver jugadas</a>', url, params)
    ver_jugadas.short_description = 'Ver jugadas'

    def eliminar(self, obj):
        url = reverse('admin:player_match_delete', args=[obj.pk])
        return format_html('<a class="text-red-600" href="{}">Eliminar</a>', url)
    eliminar.short_description = 'Eliminar'

    def delete_matches_and_plays(self, request, queryset):
        # Contar jugadas a eliminar (para feedback)
        plays_total = sum(m.plays.count() for m in queryset)
        count = queryset.count()
        # Eliminar en cascada (on_delete=CASCADE se encarga de las jugadas)
        queryset.delete()
        self.message_user(
            request,
            f"Eliminados {count} partido(s) y {plays_total} jugada(s) asociadas.",
            level=messages.SUCCESS
        )
    delete_matches_and_plays.short_description = 'Eliminar partidos seleccionados y sus jugadas'

@admin.register(Play)
class PlayAdmin(admin.ModelAdmin):
    list_display = ('evento', 'match', 'equipo', 'inicio', 'fin', 'inicia', 'zona_inicio', 'zona_fin')
    list_filter = ('match', 'equipo', 'evento', 'zona_inicio', 'zona_fin', 'inicia')
    search_fields = ('evento', 'equipo', 'zona_inicio', 'zona_fin', 'inicia')

# Registramos Team de forma simple, ya que no tiene personalización
admin.site.register(Team)