from django.db.models import Q
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
        GET /api/matches/{pk}/plays/?jugada=&equipo=&zona_inicio=&zona_fin=&search=
        """
        match = self.get_object()
        qs = match.plays.all().order_by('inicio')

        # Filtros simples
        jugada = request.query_params.get('jugada')
        equipo = request.query_params.get('equipo')
        zona_inicio = request.query_params.get('zona_inicio')
        zona_fin = request.query_params.get('zona_fin')
        qtext = request.query_params.get('search') or request.query_params.get('search[value]')

        if jugada:
            qs = qs.filter(jugada__iexact=jugada)
        if equipo:
            qs = qs.filter(equipo__iexact=equipo)
        if zona_inicio:
            qs = qs.filter(zona_inicio__iexact=zona_inicio)
        if zona_fin:
            qs = qs.filter(zona_fin__iexact=zona_fin)
        if qtext:
            qs = qs.filter(
                Q(jugada__icontains=qtext) |
                Q(evento__icontains=qtext) |
                Q(jugadores__icontains=qtext)
            )

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(PlaySerializer(page, many=True).data)
        return Response(PlaySerializer(qs, many=True).data)