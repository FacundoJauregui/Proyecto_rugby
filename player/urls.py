# player/urls.py

from django.urls import path
from .views import (
    AnalysisUploadView, 
    MatchPlayerView, 
    MatchListView,
    UserLoginView, 
    UserLogoutView
)
app_name = 'player'

urlpatterns = [
    # La página de inicio ahora es la lista de partidos
    path('', MatchListView.as_view(), name='match_list'),
    
    # La página para subir un análisis ahora tiene su propia URL
    path('upload/', AnalysisUploadView.as_view(), name='upload_analysis'),
    
    # La página del reproductor se mantiene igual
    path('match/<int:pk>/', MatchPlayerView.as_view(), name='play_match'),
    
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
]