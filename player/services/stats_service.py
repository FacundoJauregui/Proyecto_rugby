"""
Servicio de estadísticas para el dashboard.

Contiene toda la lógica de cálculo de métricas, tendencias y análisis
de partidos y jugadas para los dashboards de entrenadores.
"""
import logging

from django.db.models import Count, Q, F, Avg, Sum, Case, When, IntegerField, CharField, Value
from django.db.models.functions import Coalesce, Upper
from collections import defaultdict
from typing import Optional, List, Dict, Any
from datetime import date, timedelta

from player.models import Match, Play, Team, CoachTournamentTeamParticipation, Tournament, Profile

logger = logging.getLogger(__name__)


class StatsService:
    """Servicio centralizado para cálculos estadísticos."""

    def __init__(self, user, team_name: Optional[str] = None, seasons: Optional[List[str]] = None, tournaments: Optional[List[str]] = None):
        """
        Inicializa el servicio de estadísticas.
        
        Args:
            user: Usuario autenticado (entrenador/staff/admin)
            team_name: Nombre del equipo a analizar (opcional, se infiere del usuario si no se provee)
            seasons: Lista de temporadas a incluir (opcional, todas si no se especifica)
        """
        self.user = user
        self.team_name = team_name
        self.seasons = seasons or []
        self.tournament_ids = tournaments or []
        self._team_names = set()
        self._init_team_context()

    def _init_team_context(self):
        """Determina los equipos del usuario según su rol."""
        if self.user.is_superuser or self.user.is_staff:
            # Staff/Admin/Superuser pueden ver todo, pero si se especifica team_name, lo usan
            if self.team_name:
                self._team_names = {self.team_name.upper()}
            # Si no hay team_name, _team_names queda vacío = ver todos los partidos
        else:
            # Entrenadores: buscar equipos de múltiples fuentes
            
            # 1. Desde Profile (equipo principal)
            try:
                profile = Profile.objects.select_related('team').get(user=self.user)
                if profile.team:
                    name = (profile.team.alias or profile.team.name).strip().upper()
                    if name:
                        self._team_names.add(name)
            except Profile.DoesNotExist:
                pass
            
            # 2. Desde CoachTournamentTeamParticipation (todas las participaciones)
            participations = CoachTournamentTeamParticipation.objects.filter(
                user=self.user
            ).select_related('team')
            
            for p in participations:
                name = (p.team.alias or p.team.name).strip().upper()
                if name:
                    self._team_names.add(name)
            
            # Si se especificó team_name, filtrar solo ese (si el usuario tiene acceso)
            if self.team_name:
                specified = self.team_name.upper()
                if specified in self._team_names or not self._team_names:
                    self._team_names = {specified}

    def _get_base_matches_queryset(self, include_tournament_filter: bool = True):
        """Retorna el queryset base de partidos según contexto."""
        qs = Match.objects.select_related('tournament', 'tournament__country')
        
        # Filtrar por equipo
        if self._team_names:
            team_q = Q()
            for name in self._team_names:
                team_q |= Q(home_team__iexact=name) | Q(away_team__iexact=name)
            qs = qs.filter(team_q)
        
        # Filtrar por temporadas si se especificaron
        if self.seasons:
            season_q = Q()
            for s in self.seasons:
                season_q |= Q(tournament__season__iexact=s)
            qs = qs.filter(season_q)

        # Filtrar por torneos seleccionados (por nombre/short_name, sin importar temporada)
        if include_tournament_filter and self.tournament_ids:
            tournament_q = Q()
            for t in self.tournament_ids:
                t_norm = (t or '').strip()
                if not t_norm:
                    continue
                tournament_q |= Q(tournament__name__iexact=t_norm) | Q(tournament__short_name__iexact=t_norm)
            if tournament_q:
                qs = qs.filter(tournament_q)
        
        return qs

    def _get_base_plays_queryset(self, match_ids: Optional[List[int]] = None):
        """Retorna el queryset base de jugadas."""
        if match_ids:
            return Play.objects.filter(match_id__in=match_ids)
        matches = self._get_base_matches_queryset()
        return Play.objects.filter(match__in=matches)

    def _parse_marcador_final(self, match_id: int) -> tuple:
        """
        Parsea el marcador_final de un partido.
        
        El marcador_final tiene formato "X - Y" donde:
        - X = puntaje del equipo LOCAL
        - Y = puntaje del equipo VISITANTE
        
        Returns:
            tuple (home_score, away_score) o (None, None) si no hay marcador
        """
        # Obtener la última jugada con marcador_final del partido
        last_play = Play.objects.filter(
            match_id=match_id
        ).exclude(
            marcador_final=''
        ).order_by('-fin').first()
        
        if not last_play or not last_play.marcador_final:
            return None, None
        
        try:
            # Formato esperado: "13 - 25" o "13-25"
            marcador = last_play.marcador_final.strip()
            parts = marcador.split('-')
            if len(parts) == 2:
                home_score = int(parts[0].strip())
                away_score = int(parts[1].strip())
                return home_score, away_score
        except (ValueError, IndexError):
            pass
        
        return None, None

    def _get_match_result(self, match_id: int, home_team: str, away_team: str) -> dict:
        """
        Determina el resultado de un partido usando marcador_final.
        
        Returns:
            dict con: result ('W', 'L', 'D'), team_score, opp_score, is_home, score_str
        """
        home_score, away_score = self._parse_marcador_final(match_id)
        
        is_home = home_team.upper() in self._team_names
        is_away = away_team.upper() in self._team_names
        
        # Si no hay marcador, retornar valores por defecto
        if home_score is None or away_score is None:
            return {
                'result': 'D',
                'team_score': 0,
                'opp_score': 0,
                'is_home': is_home,
                'score_str': '-',
                'has_score': False
            }
        
        # Determinar puntajes según si somos local o visitante
        if is_home:
            team_score = home_score
            opp_score = away_score
        else:
            team_score = away_score
            opp_score = home_score
        
        # Determinar resultado
        if team_score > opp_score:
            result = 'W'
        elif team_score < opp_score:
            result = 'L'
        else:
            result = 'D'
        
        return {
            'result': result,
            'team_score': team_score,
            'opp_score': opp_score,
            'is_home': is_home,
            'score_str': f"{home_score} - {away_score}",
            'has_score': True
        }

    def get_available_seasons(self) -> List[str]:
        """Retorna las temporadas disponibles para el usuario."""
        matches = self._get_base_matches_queryset(include_tournament_filter=False)
        seasons = matches.exclude(
            tournament__season__isnull=True
        ).exclude(
            tournament__season=''
        ).values_list(
            'tournament__season', flat=True
        ).distinct().order_by('-tournament__season')
        return list(seasons)

    def get_available_tournaments(self) -> List[Dict[str, Any]]:
        """Retorna torneos disponibles (únicos por nombre), sin distinguir temporada."""
        matches = self._get_base_matches_queryset(include_tournament_filter=False)
        tournaments = matches.exclude(tournament__isnull=True).values(
            'tournament__name',
            'tournament__short_name'
        ).annotate(dummy=Value(1)).values('tournament__name', 'tournament__short_name').distinct().order_by('tournament__name')
        result = []
        for t in tournaments:
            result.append({
                'name': t['tournament__name'],
                'short_name': t['tournament__short_name'],
            })
        return result

    def _count_tries(self, match_id: int, team_name: str) -> int:
        """Cuenta tries de un equipo en un partido usando solo el campo jugada."""
        if not team_name:
            return 0
        normalized = team_name.strip().upper()
        return Play.objects.filter(
            match_id=match_id,
            equipo__iexact=normalized
        ).filter(
            Q(jugada__iexact='TRIES') | Q(jugada__icontains='TRY')
        ).count()

    def _count_penalties_conceded(self, match_id: int, team_name: str) -> int:
        """Cuenta penales concedidos por equipo en un partido (jugada=penales_concedidos)."""
        if not team_name:
            return 0
        normalized = team_name.strip().upper()
        return Play.objects.filter(
            match_id=match_id,
            equipo__iexact=normalized
        ).filter(
            Q(jugada__iexact='PENALES_CONCEDIDOS') | Q(jugada__icontains='PENALES_CONCEDIDOS')
        ).count()

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas resumidas generales.
        
        Returns:
            Dict con total_matches, wins, losses, draws, points_for, points_against, tries, etc.
        """
        matches = self._get_base_matches_queryset()
        match_list = list(matches.values('id', 'home_team', 'away_team', 'match_date'))
        
        total = len(match_list)
        wins = 0
        losses = 0
        draws = 0
        points_for = 0
        points_against = 0
        tries_for = 0
        tries_against = 0
        
        # Análisis por partido usando marcador_final
        for match_data in match_list:
            result_data = self._get_match_result(
                match_data['id'],
                match_data['home_team'],
                match_data['away_team']
            )
            
            if result_data['result'] == 'W':
                wins += 1
            elif result_data['result'] == 'L':
                losses += 1
            else:
                draws += 1
            
            if result_data['has_score']:
                points_for += result_data['team_score']
                points_against += result_data['opp_score']

            # Log de tries por partido (para debug)
            is_home = result_data['is_home']
            team_name = match_data['home_team'] if is_home else match_data['away_team']
            opp_name = match_data['away_team'] if is_home else match_data['home_team']
            team_tries_match = self._count_tries(match_data['id'], team_name)
            opp_tries_match = self._count_tries(match_data['id'], opp_name)
            logger.info(
                "[TRY_DEBUG] match=%s home=%s away=%s team=%s opp=%s team_tries=%s opp_tries=%s",
                match_data['id'], match_data['home_team'], match_data['away_team'],
                team_name, opp_name, team_tries_match, opp_tries_match
            )

            # Sumar tries por partido para el agregado final
            if self._team_names:
                tries_for += team_tries_match
                tries_against += opp_tries_match

        avg_points_per_match = round(points_for / total, 1) if total > 0 else 0
        avg_tries_per_match = round(tries_for / total, 1) if total > 0 else 0
        
        return {
            'total_matches': total,
            'wins': wins,
            'losses': losses,
            'draws': draws,
            'win_rate': round((wins / total * 100) if total > 0 else 0, 1),
            'points_for': points_for,
            'points_against': points_against,
            'point_difference': points_for - points_against,
            'tries_for': tries_for,
            'tries_against': tries_against,
            'try_difference': tries_for - tries_against,
            'avg_points_per_match': avg_points_per_match,
            'avg_tries_per_match': avg_tries_per_match,
        }

    def get_recent_matches(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Obtiene los últimos N partidos con sus resultados."""
        matches = self._get_base_matches_queryset().order_by('-match_date', '-created_at')[:limit]
        
        result = []
        for match in matches:
            # Obtener resultado usando marcador_final

            result_data = self._get_match_result(
                match.id,
                match.home_team,
                match.away_team
            )
            
            plays_count = Play.objects.filter(match=match).count()
            
            # Contar tries
            team_name = match.home_team if result_data['is_home'] else match.away_team
            opp_name = match.away_team if result_data['is_home'] else match.home_team
            team_tries = self._count_tries(match.id, team_name)
            opp_tries = self._count_tries(match.id, opp_name)
            
            result.append({
                'id': match.id,
                'home_team': match.home_team,
                'away_team': match.away_team,
                'team_name': team_name,
                'opp_name': opp_name,
                'match_date': match.match_date,
                'tournament': match.tournament.short_name if match.tournament else None,
                'season': match.tournament.season if match.tournament else None,
                'is_home': result_data['is_home'],
                'team_score': result_data['team_score'],
                'opp_score': result_data['opp_score'],
                'score_str': result_data['score_str'],
                'team_tries': team_tries,
                'opp_tries': opp_tries,
                'result': result_data['result'],
                'plays_count': plays_count,
            })
        
        return result

    def get_plays_distribution(self) -> Dict[str, Any]:
        """
        Obtiene distribución de tipos de jugadas.
        
        Returns:
            Dict con conteos por tipo de jugada, evento, etc.
        """
        plays = self._get_base_plays_queryset()

        # Filtro de equipo analizado (para métricas específicas)
        team_q = Q()
        for name in self._team_names:
            team_q |= Q(equipo__iexact=name)

        plays_for_team = plays.filter(team_q) if team_q else plays
        
        # Por tipo de jugada
        by_jugada = plays.exclude(jugada='').values('jugada').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Por evento
        by_evento = plays.exclude(evento='').values('evento').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Por resultado
        by_resultado = plays.exclude(resultado='').values('resultado').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Por zona de inicio
        by_zona_inicio = plays.exclude(zona_inicio='').values('zona_inicio').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Por zona de fin
        by_zona_fin = plays.exclude(zona_fin='').values('zona_fin').annotate(
            count=Count('id')
        ).order_by('-count')

        # Lines ganados / perdidos (jugada LINE/lines, resultado gana|gana sucio vs pierde)
        line_jugada_filter = Q(jugada__iexact='LINE') | Q(jugada__iexact='LINES') | Q(jugada__icontains='LINE')
        line_won_result_filter = Q(resultado__iexact='GANA') | Q(resultado__iexact='GANA SUCIO') | Q(resultado__icontains='GANA SUCIO')
        line_lost_result_filter = Q(resultado__iexact='PIERDE') | Q(resultado__icontains='PIERDE')

        lines_won = plays_for_team.filter(line_jugada_filter).filter(line_won_result_filter).count()
        lines_lost = plays_for_team.filter(line_jugada_filter).filter(line_lost_result_filter).count()

        # Scrums ganados / perdidos (jugada SCRUMS, resultado gana vs pierde)
        scrum_jugada_filter = Q(jugada__iexact='SCRUMS') | Q(jugada__icontains='SCRUM')
        scrum_won_result_filter = Q(resultado__iexact='GANA') | Q(resultado__iexact='GANA SUCIO') | Q(resultado__icontains='GANA SUCIO') | Q(resultado__icontains='GANA')
        scrum_lost_result_filter = Q(resultado__iexact='PIERDE') | Q(resultado__icontains='PIERDE')

        scrums_won = plays_for_team.filter(scrum_jugada_filter).filter(scrum_won_result_filter).count()
        scrums_lost = plays_for_team.filter(scrum_jugada_filter).filter(scrum_lost_result_filter).count()
        
        return {
            'by_jugada': list(by_jugada),
            'by_evento': list(by_evento),
            'by_resultado': list(by_resultado),
            'by_zona_inicio': list(by_zona_inicio),
            'by_zona_fin': list(by_zona_fin),
            'total_plays': plays.count(),
            'lineouts': {
                'won': lines_won,
                'lost': lines_lost,
                'total': lines_won + lines_lost,
            },
            'scrums': {
                'won': scrums_won,
                'lost': scrums_lost,
                'total': scrums_won + scrums_lost,
            },
        }

    def get_zone_heatmap_data(self) -> Dict[str, Any]:
        """
        Obtiene datos para el heatmap de zonas.
        
        Returns:
            Dict con matrices de frecuencias para zonas inicio y fin.
        """
        plays = self._get_base_plays_queryset()
        
        # Zonas típicas del rugby (22m, mitad, etc.)
        zone_map = {
            'TRY ZONE OPP': 0, 'TRY ZONE': 0,
            '22 OPP': 1, '22': 1,
            '10-22 OPP': 2, '10-22': 2,
            'HALF OPP': 3, 'HALF': 3, 'MITAD': 3,
            '10-22 OUR': 4,
            '22 OUR': 5,
            'TRY ZONE OUR': 6,
        }
        
        # Contar transiciones zona_inicio -> zona_fin
        transitions = defaultdict(int)
        zone_starts = defaultdict(int)
        zone_ends = defaultdict(int)
        
        for play in plays.values('zona_inicio', 'zona_fin'):
            zi = (play['zona_inicio'] or '').upper().strip()
            zf = (play['zona_fin'] or '').upper().strip()
            
            if zi:
                zone_starts[zi] += 1
            if zf:
                zone_ends[zf] += 1
            if zi and zf:
                transitions[(zi, zf)] += 1
        
        return {
            'zone_starts': dict(zone_starts),
            'zone_ends': dict(zone_ends),
            'transitions': {f"{k[0]}->{k[1]}": v for k, v in transitions.items()},
        }

    def get_trend_data(self, last_n_matches: int = 10) -> List[Dict[str, Any]]:
        """
        Obtiene datos de tendencia para gráfico de línea temporal.
        
        Args:
            last_n_matches: Cantidad de partidos a incluir
            
        Returns:
            Lista de dicts con fecha, puntajes, resultado por partido
        """
        matches = self._get_base_matches_queryset().order_by('match_date', 'created_at')
        
        # Tomar los últimos N
        match_list = list(matches)[-last_n_matches:]
        
        result = []
        cumulative_wins = 0
        
        for i, match in enumerate(match_list):
            # Usar el método que parsea marcador_final
            result_data = self._get_match_result(
                match.id,
                match.home_team,
                match.away_team
            )
            
            opp_name = match.away_team if result_data['is_home'] else match.home_team
            team_name = match.home_team if result_data['is_home'] else match.away_team
            opp_team_name = opp_name

            team_tries = self._count_tries(match.id, team_name)
            opp_tries = self._count_tries(match.id, opp_team_name)
            team_pen_conc = self._count_penalties_conceded(match.id, team_name)
            opp_pen_conc = self._count_penalties_conceded(match.id, opp_team_name)
            
            if result_data['result'] == 'W':
                cumulative_wins += 1
                res = 1
            elif result_data['result'] == 'L':
                res = -1
            else:
                res = 0
            
            result.append({
                'index': i + 1,
                'date': match.match_date.isoformat() if match.match_date else None,
                'opponent': opp_name,
                'team_score': result_data['team_score'],
                'opp_score': result_data['opp_score'],
                'team_tries': team_tries,
                'opp_tries': opp_tries,
                'team_penalties_conceded': team_pen_conc,
                'opp_penalties_conceded': opp_pen_conc,
                'result': res,  # 1=win, 0=draw, -1=loss
                'cumulative_wins': cumulative_wins,
            })
        
        return result

    def get_match_detailed_stats(self, match_id: int) -> Dict[str, Any]:
        """
        Obtiene estadísticas detalladas de un partido específico.
        
        Args:
            match_id: ID del partido
            
        Returns:
            Dict completo con todas las métricas del partido
        """
        try:
            match = Match.objects.select_related('tournament').get(id=match_id)
        except Match.DoesNotExist:
            return {}
        
        plays = Play.objects.filter(match=match)
        total_plays = plays.count()
        
        # Obtener resultado del partido usando marcador_final
        result_data = self._get_match_result(
            match.id,
            match.home_team,
            match.away_team
        )
        
        is_home = result_data['is_home']
        team_name = match.home_team if is_home else match.away_team
        opp_name = match.away_team if is_home else match.home_team
        
        # Jugadas solo del equipo analizado
        team_plays = plays.filter(equipo__iexact=team_name)
        opp_plays = plays.filter(equipo__iexact=opp_name)

        # Set pieces: lines y scrums por equipo
        line_filter = Q(jugada__iexact='LINE') | Q(jugada__iexact='LINES') | Q(jugada__icontains='LINE')
        line_total_filter = Q(jugada__iexact='LINE') | Q(jugada__iexact='LINES')
        scrum_filter = Q(jugada__iexact='SCRUMS') | Q(jugada__icontains='SCRUM')
        scrum_total_filter = Q(jugada__iexact='SCRUMS') & ~Q(resultado__iexact='RESET')
        win_clean_filter = Q(resultado__iexact='GANA')
        win_dirty_filter = Q(resultado__iexact='GANA SUCIO') | Q(resultado__icontains='GANA SUCIO')
        win_any_filter = win_clean_filter | win_dirty_filter | Q(resultado__icontains='GANA')
        lose_filter = Q(resultado__iexact='PIERDE') | Q(resultado__icontains='PIERDE')

        team_lines_won_clean = team_plays.filter(line_filter & win_clean_filter).count()
        team_lines_won_dirty = team_plays.filter(line_filter & win_dirty_filter).count()
        team_lines_lost = team_plays.filter(line_filter & lose_filter).count()
        opp_lines_lost = opp_plays.filter(line_filter & lose_filter).count()  # lines recuperados
        total_lines_match = plays.filter(line_total_filter).count()
        team_scrums_won_clean = team_plays.filter(scrum_filter & win_clean_filter).count()
        team_scrums_won_dirty = team_plays.filter(scrum_filter & win_dirty_filter).count()
        team_scrums_lost = team_plays.filter(scrum_filter & lose_filter).count()
        team_scrums_won_any = team_scrums_won_clean + team_scrums_won_dirty
        opp_scrums_recovered = opp_plays.filter(scrum_filter & lose_filter).count()
        total_scrums_match = plays.filter(scrum_total_filter).count()

        # Desglose por 'sigue_con' para lines y scrums del equipo
        def build_breakdown(play_values_qs, normalize_outcome):
            counts = defaultdict(int)
            labels_set = set()
            for row in play_values_qs:
                outcome = normalize_outcome((row.get('resultado') or '').strip())
                if not outcome:
                    continue
                follow_raw = (row.get('sigue_con') or 'Sin dato').strip() or 'Sin dato'
                # Normalizar variantes de "8" en sigue_con
                follow_key = follow_raw.replace('.', '').replace(' ', '').upper()
                if follow_key in ('8', '8VO'):
                    follow = '8.vo'
                else:
                    follow = follow_raw
                labels_set.add(follow)
                counts[(outcome, follow)] += 1
            labels = sorted(labels_set)
            outcomes = ['Gana', 'Gana sucio', 'Pierde']
            matrix = []
            for out in outcomes:
                row_counts = []
                for lab in labels:
                    row_counts.append(counts.get((out, lab), 0))
                matrix.append(row_counts)
            return {
                'labels': labels,
                'outcomes': outcomes,
                'matrix': matrix,
            }

        def normalize_line_outcome(res_upper: str):
            if res_upper.startswith('GANA SUCIO'):
                return 'Gana sucio'
            if res_upper.startswith('GANA'):
                return 'Gana'
            if res_upper.startswith('PIERDE'):
                return 'Pierde'
            return None

        def normalize_scrum_outcome(res_upper: str):
            if res_upper.startswith('GANA SUCIO'):
                return 'Gana sucio'
            if res_upper.startswith('GANA'):
                return 'Gana'
            if res_upper.startswith('PIERDE'):
                return 'Pierde'
            return None

        line_values = team_plays.filter(line_filter).values('resultado', 'sigue_con')
        scrum_values = team_plays.filter(scrum_filter).values('resultado', 'sigue_con')

        line_breakdown = build_breakdown(line_values, lambda r: normalize_line_outcome(r.upper()))
        scrum_breakdown = build_breakdown(scrum_values, lambda r: normalize_scrum_outcome(r.upper()))

        # Tries (para estadísticas adicionales)
        tries_filter = Q(jugada__iexact='TRIES') | Q(jugada__icontains='TRY')
        team_tries = team_plays.filter(tries_filter).count()
        tries_converted = team_plays.filter(tries_filter & Q(resultado__iexact='7')).count()
        tries_unconverted = team_plays.filter(tries_filter & Q(resultado__iexact='5')).count()
        
        # Sanciones
        team_penalties = team_plays.filter(
            Q(sancion__icontains='PENAL') | Q(resultado__icontains='PENAL')
        ).count()

        # Penales a los palos (goals)
        penales_goal_success = team_plays.filter(Q(jugada__iexact='GOALS') & Q(resultado__iexact='3')).count()
        penales_goal_missed = team_plays.filter(Q(jugada__iexact='GOAL_ERRADOS')).count()
        penales_goal_total = penales_goal_success + penales_goal_missed

        # Tarjetas
        yellow_cards = team_plays.filter(Q(jugada__iexact='TARJETAS') & Q(evento__icontains='AMARILLA')).count()
        red_cards = team_plays.filter(Q(jugada__iexact='TARJETAS') & Q(evento__icontains='ROJA')).count()
        
        # Distribución por zona
        team_by_zone = team_plays.exclude(zona_inicio='').values('zona_inicio').annotate(
            count=Count('id')
        )

        # Pelotas perdidas por zona de fin
        raw_lost_by_zone = list(team_plays.filter(
            Q(jugada__iexact='POSESION') & Q(termina__iexact='PELOTA_PERDIDA')
        ).exclude(zona_fin='').values('zona_fin').annotate(count=Count('id')))

        def normalize_zone_key(z: str) -> str:
            u = (z or '').strip().upper()
            if 'ROJA' in u:
                return 'ZONA ROJA'
            if 'NARANJA' in u:
                return 'ZONA NARANJA'
            if 'AMARILLA' in u:
                return 'ZONA AMARILLA'
            if 'VERDE' in u:
                return 'ZONA VERDE'
            return ''

        order_map = {
            'ZONA ROJA': 'Zona roja',
            'ZONA NARANJA': 'Zona naranja',
            'ZONA AMARILLA': 'Zona amarilla',
            'ZONA VERDE': 'Zona verde',
        }

        counts_by_norm = defaultdict(int)
        extras = []
        for row in raw_lost_by_zone:
            norm = normalize_zone_key(row['zona_fin'])
            if norm:
                counts_by_norm[norm] += row['count']
            else:
                extras.append({'zona_fin': row['zona_fin'], 'count': row['count']})

        team_lost_by_zone = []
        for key in ['ZONA ROJA', 'ZONA NARANJA', 'ZONA AMARILLA', 'ZONA VERDE']:
            team_lost_by_zone.append({
                'zona_fin': order_map[key],
                'count': counts_by_norm.get(key, 0)
            })

        team_lost_by_zone.extend(extras)
        
        # Distribución por tipo de jugada
        team_by_jugada = team_plays.exclude(jugada='').values('jugada').annotate(
            count=Count('id')
        ).order_by('-count')[:8]

        # Posesiones por resultado de 'termina'
        possession_raw = team_plays.filter(jugada__iexact='POSESION').values('termina').annotate(count=Count('id'))
        opp_possessions_total = opp_plays.filter(jugada__iexact='POSESION').count()
        penales_contra = team_plays.filter(jugada__iexact='PENALES_CONCEDIDOS').count()
        penales_favor = opp_plays.filter(jugada__iexact='PENALES_CONCEDIDOS').count()
        possession_buckets = {
            'ventaja': {'label': 'Ventaja', 'count': 0},
            'puntos': {'label': 'Puntos', 'count': 0},
            'penal/fk_ec': {'label': 'Penal en Contra', 'count': 0},
            'penal/fk_af': {'label': 'Penal a Favor', 'count': 0},
            'pelota_perdida': {'label': 'Pelota perdida', 'count': 0},
            'kick_touch': {'label': 'Kick al touch', 'count': 0},
            'kick _play': {'label': 'Kick play', 'count': 0},  # variante con espacio
        }
        total_possessions = 0
        for row in possession_raw:
            raw_key = (row['termina'] or '').strip().lower()
            key = raw_key.replace(' ', '_')
            # Aceptar tanto la versión normalizada como la literal
            if key in possession_buckets:
                bucket_key = key
            elif raw_key in possession_buckets:
                bucket_key = raw_key
            else:
                continue
            possession_buckets[bucket_key]['count'] += row['count']
            total_possessions += row['count']
        # Sobrescribir penales usando jugada=penales_concedidos
        possession_buckets['penal/fk_ec']['count'] = penales_contra
        possession_buckets['penal/fk_af']['count'] = penales_favor
        # Pelotas recuperadas: posesiones del rival que terminan en pelota_perdida
        balls_recovered = opp_plays.filter(
            Q(jugada__iexact='POSESION') & Q(termina__iexact='PELOTA_PERDIDA')
        ).count()

        # Salidas recuperadas/perdidas
        salidas_recuperadas = team_plays.filter(
            Q(jugada__iexact='SALIDAS') & (Q(resultado__iexact='RECUPERADA') | Q(resultado__iexact='RECUPERA'))
        ).count()
        salidas_perdidas = opp_plays.filter(
            Q(jugada__iexact='SALIDAS') & (Q(termina__iexact='RECUPERA') | Q(termina__iexact='RECUPERADA'))
        ).count()
        salidas_totales_opp = opp_plays.filter(Q(jugada__iexact='SALIDAS')).count()

        pelota_perdida_count = possession_buckets.get('pelota_perdida', {}).get('count', 0)
        total_non_lost_possessions = max(total_possessions - pelota_perdida_count, 0)

        # Rucks ganados/perdidos del equipo analizado
        rucks_won = team_plays.filter(Q(jugada__iexact='RUCKS_GANADOS') | Q(jugada__icontains='RUCKS_GANADOS')).count()
        rucks_lost = team_plays.filter(Q(jugada__iexact='RUCKS_PERDIDO') | Q(jugada__icontains='RUCKS_PERDIDO')).count()
        opp_rucks_won = opp_plays.filter(Q(jugada__iexact='RUCKS_GANADOS') | Q(jugada__icontains='RUCKS_GANADOS')).count()
        opp_rucks_lost = opp_plays.filter(Q(jugada__iexact='RUCKS_PERDIDO') | Q(jugada__icontains='RUCKS_PERDIDO')).count()

        # Armar lista de items incluyendo recuperadas; porcentajes sobre total general
        total_general = (
            total_possessions + balls_recovered + rucks_won + rucks_lost +
            salidas_recuperadas + salidas_perdidas + penales_contra + penales_favor
        )
        ordered_keys = [
            'penal/fk_ec', 'penal/fk_af',
            'pelota_perdida', 'pelotas_recuperadas',
            'salidas_recuperadas', 'salidas_perdidas',
            'rucks_ganados', 'rucks_perdidos'
        ]
        possession_items = []
        for key in ordered_keys:
            if key == 'pelotas_recuperadas':
                count = balls_recovered
                label = 'Pelotas recuperadas'
            elif key == 'salidas_recuperadas':
                count = salidas_recuperadas
                label = 'Salidas recuperadas'
            elif key == 'salidas_perdidas':
                count = salidas_perdidas
                label = 'Salidas perdidas'
            elif key == 'rucks_ganados':
                count = rucks_won
                label = 'Rucks ganados'
            elif key == 'rucks_perdidos':
                count = rucks_lost
                label = 'Rucks perdidos'
            else:
                data = possession_buckets.get(key, {'label': key, 'count': 0})
                count = data['count']
                label = data.get('label', key)
            pct = round((count / total_general * 100), 1) if total_general > 0 else 0
            possession_items.append({'key': key, 'label': label, 'count': count, 'pct': pct})
        possession_summary = {
            'total': total_possessions,
            'opp_total': opp_possessions_total,
            'total_general': total_general,
            'total_non_lost': total_non_lost_possessions,
            'pelota_perdida_count': pelota_perdida_count,
            'items': possession_items,
            'averages': []
        }

        # Promedios solicitados
        def pct(num: int, den: int) -> float:
            return round((num / den * 100), 1) if den > 0 else 0.0

        possession_summary['averages'] = [
            {
                'label': 'Pelotas perdidas',
                'value': pct(pelota_perdida_count, total_possessions),
                'num': pelota_perdida_count,
                'den': total_possessions,
            },
            {
                'label': 'Pelotas recuperadas',
                'value': pct(balls_recovered, opp_possessions_total),
                'num': balls_recovered,
                'den': opp_possessions_total,
            },
            {
                'label': 'Salidas perdidas',
                'value': pct(salidas_perdidas, salidas_totales_opp),
                'num': salidas_perdidas,
                'den': salidas_totales_opp,
            },
            {
                'label': 'Rucks ganados',
                'value': pct(rucks_won + opp_rucks_lost, rucks_won + rucks_lost + opp_rucks_won + opp_rucks_lost),
                'num': rucks_won + opp_rucks_lost,
                'den': rucks_won + rucks_lost + opp_rucks_won + opp_rucks_lost,
            }
        ]
        
        return {
            'match': {
                'id': match.id,
                'home_team': match.home_team,
                'away_team': match.away_team,
                'match_date': match.match_date,
                'tournament': match.tournament.name if match.tournament else None,
                'season': match.tournament.season if match.tournament else None,
            },
            'team_name': team_name,
            'opp_name': opp_name,
            'is_home': is_home,
            'total_plays': total_plays,
            'result': result_data['result'],
            'score_str': result_data['score_str'],
            'team_score': result_data['team_score'],
            'opp_score': result_data['opp_score'],
            'team_stats': {
                'plays': team_plays.count(),
                'tries': team_tries,
                'tries_converted': tries_converted,
                'tries_unconverted': tries_unconverted,
                'penalties': team_penalties,
                'penales_goal_success': penales_goal_success,
                'penales_goal_total': penales_goal_total,
                'yellow_cards': yellow_cards,
                'red_cards': red_cards,
                'by_zone': list(team_by_zone),
                'lost_by_zone': list(team_lost_by_zone),
                'by_jugada': list(team_by_jugada),
                'balls_recovered': balls_recovered,
            },
            'possession': possession_summary,
            'set_pieces': {
                'line_won_clean': team_lines_won_clean,
                'line_won_dirty': team_lines_won_dirty,
                'line_lost': team_lines_lost,
                'line_recovered': opp_lines_lost,
                'line_total_match': total_lines_match,
                'line_breakdown': line_breakdown,
                'scrum_won_clean': team_scrums_won_clean,
                'scrum_won_dirty': team_scrums_won_dirty,
                'scrum_won_any': team_scrums_won_any,
                'scrum_lost': team_scrums_lost,
                'scrum_recovered': opp_scrums_recovered,
                'scrum_total_match': total_scrums_match,
                'scrum_breakdown': scrum_breakdown,
            }
        }

    def compare_matches(self, match_ids: List[int]) -> Dict[str, Any]:
        """
        Compara estadísticas entre múltiples partidos.
        
        Args:
            match_ids: Lista de IDs de partidos a comparar
            
        Returns:
            Dict con estadísticas comparativas
        """
        comparison = []
        
        for mid in match_ids:
            stats = self.get_match_detailed_stats(mid)
            if stats:
                comparison.append(stats)
        
        return {
            'matches': comparison,
            'count': len(comparison),
        }
