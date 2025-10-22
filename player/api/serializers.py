from rest_framework import serializers
from player.models import Match, Play

class PlaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Play
        fields = [
            'id', 'jugada', 'arbitro', 'canal_de_inicio', 'evento', 'equipo',
            'fin', 'ficha', 'inicia', 'inicio', 'marcador_final', 'termina',
            'tiempo', 'torneo', 'zona_fin', 'zona_inicio', 'resultado',
            'jugadores', 'sigue_con', 'pos_tiro', 'set', 'tiro', 'tipo',
            'accion', 'termina_en', 'sancion', 'situacion', 'transicion',
            'situacion_penal', 'nueva_categoria', 'acercar', 'alejar'
        ]

class MatchSerializer(serializers.ModelSerializer):
    match_result = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = ['id', 'home_team', 'away_team', 'match_date', 'video_id', 'match_result']

    def get_match_result(self, obj):
        return obj.plays.exclude(marcador_final='').values_list('marcador_final', flat=True).first() or ''