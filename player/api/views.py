from django.db.models import Q, Case, When  # <- asegurar import Q (ya lo usabas) y Case/When si ordenás por ids
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from player.models import Match, Play
from .serializers import MatchSerializer, PlaySerializer

class MatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Match.objects.all().order_by('-match_date')
    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['home_team', 'away_team']  # se puede extender
    search_fields = ['home_team', 'away_team']
    ordering_fields = ['match_date', 'id']

    @action(detail=True, methods=['get'])
    def plays(self, request, pk=None):
        """
        GET /api/matches/{pk}/plays/
        - Filtros: jugada, equipo, zona_inicio, zona_fin, search
        - Extra: ids=1,2,3 → devuelve exactamente esas jugadas (sin paginación)
        """
        match = self.get_object()
        qs = match.plays.all().order_by('inicio')

        # NUEVO: permitir traer por ids concretos
        ids_csv = request.query_params.get('ids')
        if ids_csv:
            try:
                ids = [int(x) for x in ids_csv.split(',') if x.strip().isdigit()]
            except Exception:
                ids = []
            if not ids:
                return Response([])
            qs = match.plays.filter(id__in=ids).order_by('inicio')
            serializer = PlaySerializer(qs, many=True)
            return Response(serializer.data)

        # Filtros multi-valor
        jugada_values = request.query_params.getlist('jugada')
        equipo_values = request.query_params.getlist('equipo')
        zona_inicio_values = request.query_params.getlist('zona_inicio')
        zona_fin_values = request.query_params.getlist('zona_fin')
        q = request.query_params.get('search') or request.query_params.get('search[value]')
        if jugada_values:
            qs = qs.filter(jugada__in=jugada_values)
        if equipo_values:
            qs = qs.filter(equipo__in=equipo_values)
        if zona_inicio_values:
            qs = qs.filter(zona_inicio__in=zona_inicio_values)
        if zona_fin_values:
            qs = qs.filter(zona_fin__in=zona_fin_values)
        if q:
            qs = qs.filter(Q(jugada__icontains=q) | Q(evento__icontains=q) | Q(jugadores__icontains=q))

        # Timeline mode: devuelve todas las jugadas con campos mínimos, sin paginar
        if request.query_params.get('timeline') == '1':
            data = list(qs.values('id', 'jugada', 'equipo', 'inicio', 'fin'))
            return Response(data)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = PlaySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = PlaySerializer(qs, many=True)
        return Response(serializer.data)