# player/views_dashboard.py
"""
Vistas del Dashboard de Estadísticas.

Incluye:
- DashboardIndexView: Vista principal del dashboard con estadísticas generales
- TeamStatsView: Estadísticas detalladas del equipo
- MatchStatsView: Estadísticas detalladas de un partido específico
- CompareView: Comparador de partidos
"""

import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Match, CoachTournamentTeamParticipation, Team, Profile
from .services.stats_service import StatsService


class DashboardAccessMixin(LoginRequiredMixin):
    """
    Mixin que verifica acceso al dashboard.
    
    Acceso permitido para cualquier usuario autenticado.
    Los datos mostrados dependerán de sus permisos/equipos.
    """
    
    def get_user_teams(self):
        """Retorna los nombres de equipos del usuario."""
        user = self.request.user
        
        if user.is_superuser or user.is_staff:
            # Staff/Admin puede elegir cualquier equipo del sistema
            all_teams = Team.objects.all().order_by('name')
            return [t.alias or t.name for t in all_teams if (t.alias or t.name)]
        
        teams = set()
        
        # 1. Desde Profile (equipo principal)
        try:
            profile = Profile.objects.select_related('team').get(user=user)
            if profile.team:
                name = (profile.team.alias or profile.team.name).strip()
                if name:
                    teams.add(name)
        except Profile.DoesNotExist:
            pass
        
        # 2. Desde CoachTournamentTeamParticipation
        participations = CoachTournamentTeamParticipation.objects.filter(
            user=user
        ).select_related('team')
        
        for p in participations:
            name = (p.team.alias or p.team.name).strip()
            if name:
                teams.add(name)
        
        return list(teams)
    
    def is_admin_user(self):
        """Verifica si el usuario es admin/staff."""
        return self.request.user.is_superuser or self.request.user.is_staff


class DashboardIndexView(DashboardAccessMixin, TemplateView):
    """Vista principal del dashboard con estadísticas generales."""
    
    template_name = 'player/dashboard/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Obtener parámetros de filtro
        selected_seasons = self.request.GET.getlist('season', [])
        selected_tournaments = [t for t in self.request.GET.getlist('tournament', []) if t]
        selected_team = self.request.GET.get('team', None)
        
        is_admin = self.is_admin_user()
        user_teams = self.get_user_teams()
        
        # Si es admin y no hay equipo seleccionado, pedir que seleccione
        if is_admin and not selected_team and user_teams:
            context['needs_team_selection'] = True
            context['user_teams'] = user_teams
            context['selected_team'] = selected_team
            context['is_admin'] = is_admin
            context['available_seasons'] = []
            context['available_tournaments'] = []
            context['selected_seasons'] = selected_seasons
            context['selected_tournaments'] = selected_tournaments
            return context
        
        # Para entrenadores: si tiene un solo equipo, usarlo automáticamente
        effective_team = selected_team
        if not is_admin and not selected_team and len(user_teams) == 1:
            effective_team = user_teams[0]
        
        # Si el entrenador no tiene equipos asignados, mostrar mensaje
        if not is_admin and not user_teams:
            context['no_teams_assigned'] = True
            context['user_teams'] = user_teams
            context['selected_team'] = None
            context['is_admin'] = is_admin
            context['available_seasons'] = []
            context['available_tournaments'] = []
            context['selected_seasons'] = selected_seasons
            context['selected_tournaments'] = selected_tournaments
            context['needs_team_selection'] = False
            return context
        
        # Crear servicio de estadísticas
        stats_service = StatsService(
            user=self.request.user,
            team_name=effective_team,
            seasons=selected_seasons if selected_seasons else None,
            tournaments=selected_tournaments if selected_tournaments else None
        )
        
        # Obtener temporadas disponibles
        available_seasons = stats_service.get_available_seasons()
        available_tournaments = stats_service.get_available_tournaments()
        
        # Obtener estadísticas
        context['summary'] = stats_service.get_summary_stats()
        context['recent_matches'] = stats_service.get_recent_matches(limit=5)
        context['plays_distribution'] = stats_service.get_plays_distribution()
        context['trend_data'] = stats_service.get_trend_data(last_n_matches=10)
        context['zone_data'] = stats_service.get_zone_heatmap_data()
        
        # Datos para filtros
        context['available_seasons'] = available_seasons
        context['available_tournaments'] = available_tournaments
        context['selected_seasons'] = selected_seasons
        context['selected_tournaments'] = selected_tournaments
        context['user_teams'] = user_teams
        context['selected_team'] = effective_team  # Usar el equipo efectivo
        context['is_admin'] = is_admin
        context['needs_team_selection'] = False
        context['no_teams_assigned'] = False
        
        # JSON para gráficos
        context['trend_data_json'] = json.dumps(context['trend_data'])
        context['plays_distribution_json'] = json.dumps(context['plays_distribution'])
        context['zone_data_json'] = json.dumps(context['zone_data'])
        
        return context


class TeamStatsView(DashboardAccessMixin, TemplateView):
    """Vista de estadísticas detalladas del equipo."""
    
    template_name = 'player/dashboard/team_stats.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        selected_seasons = self.request.GET.getlist('season', [])
        selected_tournaments = [t for t in self.request.GET.getlist('tournament', []) if t]
        selected_team = self.request.GET.get('team', None)
        
        stats_service = StatsService(
            user=self.request.user,
            team_name=selected_team,
            seasons=selected_seasons if selected_seasons else None,
            tournaments=selected_tournaments if selected_tournaments else None
        )
        
        context['summary'] = stats_service.get_summary_stats()
        context['plays_distribution'] = stats_service.get_plays_distribution()
        context['trend_data'] = stats_service.get_trend_data(last_n_matches=20)
        context['zone_data'] = stats_service.get_zone_heatmap_data()
        
        context['available_seasons'] = stats_service.get_available_seasons()
        context['available_tournaments'] = stats_service.get_available_tournaments()
        context['selected_seasons'] = selected_seasons
        context['selected_tournaments'] = selected_tournaments
        context['user_teams'] = self.get_user_teams()
        context['selected_team'] = selected_team
        
        # JSON para gráficos
        context['trend_data_json'] = json.dumps(context['trend_data'])
        context['plays_distribution_json'] = json.dumps(context['plays_distribution'])
        context['zone_data_json'] = json.dumps(context['zone_data'])
        
        return context


class MatchStatsView(DashboardAccessMixin, TemplateView):
    """Vista de estadísticas de un partido específico."""
    
    template_name = 'player/dashboard/match_stats.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        match_id = kwargs.get('pk')
        match = get_object_or_404(Match, pk=match_id)
        selected_team = self.request.GET.get('team')
        
        stats_service = StatsService(user=self.request.user, team_name=selected_team)
        
        context['match'] = match
        context['match_stats'] = stats_service.get_match_detailed_stats(match_id)
        context['selected_team'] = selected_team
        
        # JSON para gráficos
        context['match_stats_json'] = json.dumps(context['match_stats'], default=str)
        
        return context


class CompareMatchesView(DashboardAccessMixin, TemplateView):
    """Vista para comparar múltiples partidos."""
    
    template_name = 'player/dashboard/compare.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # IDs de partidos a comparar (pueden venir por GET o POST)
        match_ids = self.request.GET.getlist('match_id', [])
        match_ids = [int(mid) for mid in match_ids if mid.isdigit()]
        
        selected_seasons = self.request.GET.getlist('season', [])
        selected_team = self.request.GET.get('team', None)
        
        stats_service = StatsService(
            user=self.request.user,
            team_name=selected_team,
            seasons=selected_seasons if selected_seasons else None
        )
        
        # Obtener partidos disponibles para comparar
        context['available_matches'] = stats_service.get_recent_matches(limit=20)
        context['selected_match_ids'] = match_ids
        
        # Si hay partidos seleccionados, comparar
        if match_ids:
            context['comparison'] = stats_service.compare_matches(match_ids)
            context['comparison_json'] = json.dumps(context['comparison'], default=str)
        else:
            context['comparison'] = None
            context['comparison_json'] = 'null'
        
        context['available_seasons'] = stats_service.get_available_seasons()
        context['selected_seasons'] = selected_seasons
        context['user_teams'] = self.get_user_teams()
        context['selected_team'] = selected_team
        
        return context


# --- API Endpoints para datos dinámicos ---

class DashboardAPIView(DashboardAccessMixin, View):
    """API JSON para datos del dashboard (para AJAX/fetch)."""
    
    def get(self, request, *args, **kwargs):
        action = kwargs.get('action', 'summary')
        
        selected_seasons = request.GET.getlist('season', [])
        selected_team = request.GET.get('team', None)
        
        stats_service = StatsService(
            user=request.user,
            team_name=selected_team,
            seasons=selected_seasons if selected_seasons else None
        )
        
        if action == 'summary':
            data = stats_service.get_summary_stats()
        elif action == 'recent':
            limit = int(request.GET.get('limit', 5))
            data = stats_service.get_recent_matches(limit=limit)
        elif action == 'plays':
            data = stats_service.get_plays_distribution()
        elif action == 'trend':
            n = int(request.GET.get('n', 10))
            data = stats_service.get_trend_data(last_n_matches=n)
        elif action == 'zones':
            data = stats_service.get_zone_heatmap_data()
        elif action == 'match':
            match_id = int(request.GET.get('match_id', 0))
            if match_id:
                data = stats_service.get_match_detailed_stats(match_id)
            else:
                data = {'error': 'match_id required'}
        elif action == 'compare':
            match_ids = request.GET.getlist('match_id', [])
            match_ids = [int(mid) for mid in match_ids if mid.isdigit()]
            data = stats_service.compare_matches(match_ids)
        elif action == 'seasons':
            data = {'seasons': stats_service.get_available_seasons()}
        else:
            data = {'error': 'Unknown action'}
        
        return JsonResponse(data, safe=False)
