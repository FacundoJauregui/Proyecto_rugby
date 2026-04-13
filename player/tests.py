from django.contrib.auth.models import User
from django.test import TestCase

from player.models import Match, Play
from player.services.stats_service import StatsService


class MatchStatsSetPiecesTotalsTests(TestCase):
    def test_set_piece_totals_only_count_displayed_bar_categories(self):
        user = User.objects.create_user(username='coach', password='secret')
        match = Match.objects.create(
            home_team='OURS',
            away_team='THEM',
            video_id='video-set-piece-1',
        )

        def create_play(**kwargs):
            defaults = {
                'match': match,
                'inicio': 0,
                'fin': 1,
                'equipo': 'OURS',
                'marcador_final': '10 - 7',
            }
            defaults.update(kwargs)
            return Play.objects.create(**defaults)

        # Lines mostrados en las barras: gana, gana sucio, pierde y recuperados.
        create_play(jugada='LINE', resultado='GANA')
        create_play(jugada='LINE', resultado='GANA SUCIO')
        create_play(jugada='LINE', resultado='PIERDE')
        create_play(jugada='LINE', resultado='PIERDE', equipo='THEM')  # recuperado
        create_play(jugada='LINE', resultado='GANA', equipo='THEM')  # rival, no debe sumar al total mostrado

        # Scrums mostrados en las barras: gana, gana sucio, pierde y recuperados.
        create_play(jugada='SCRUMS', resultado='GANA')
        create_play(jugada='SCRUMS', resultado='GANA SUCIO')
        create_play(jugada='SCRUMS', resultado='PIERDE')
        create_play(jugada='SCRUMS', resultado='PIERDE', equipo='THEM')  # recuperado
        create_play(jugada='SCRUMS', resultado='GANA', equipo='THEM')  # rival, no debe sumar al total mostrado

        stats = StatsService(user, team_name='OURS').get_match_detailed_stats(match.id)
        set_pieces = stats['set_pieces']

        self.assertEqual(set_pieces['line_total_match'], 4)
        self.assertEqual(set_pieces['scrum_total_match'], 4)
