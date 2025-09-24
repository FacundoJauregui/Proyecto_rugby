# player/urls.py

from django.urls import path
from django.views.generic import RedirectView
from .views import (
    AnalysisUploadView, 
    MatchPlayerView, 
    MatchListView,
    UserLoginView, 
    UserLogoutView,
    WelcomeView,
)
app_name = 'player'

urlpatterns = [
    # Home público de bienvenida (sin cambios)
    path('', WelcomeView.as_view(), name='welcome'),

    # Lista de partidos (requiere login)
    path('matches/', MatchListView.as_view(), name='match_list'),
    
    # Carga de análisis (canonical) y redirect legacy
    path('matches/upload/', AnalysisUploadView.as_view(), name='upload_analysis'),
    path('upload/', RedirectView.as_view(pattern_name='player:upload_analysis', permanent=True)),
    
    # Reproductor (canonical) y redirect legacy
    path('matches/<int:pk>/', MatchPlayerView.as_view(), name='play_match'),
    path('match/<int:pk>/', RedirectView.as_view(pattern_name='player:play_match', permanent=True)),
    
    # Auth: canonical /accounts/login/ y /accounts/logout/ + alias legacy
    path('accounts/login/', UserLoginView.as_view(), name='login'),
    path('accounts/logout/', UserLogoutView.as_view(), name='logout'),
    path('login/', RedirectView.as_view(pattern_name='player:login', permanent=True)),
    path('logout/', RedirectView.as_view(pattern_name='player:logout', permanent=True)),
]