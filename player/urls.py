# player/urls.py

from django.urls import path
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
    # Home público de bienvenida
    path('', WelcomeView.as_view(), name='welcome'),

    # Lista de partidos (requiere login)
    path('matches/', MatchListView.as_view(), name='match_list'),
    
    # Carga de análisis (staff)
    path('upload/', AnalysisUploadView.as_view(), name='upload_analysis'),
    
    # Reproductor
    path('match/<int:pk>/', MatchPlayerView.as_view(), name='play_match'),
    
    # Auth
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
]