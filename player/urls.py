# player/urls.py

from django.urls import path, include
from django.views.generic import RedirectView
from .views import (
    AnalysisUploadView, 
    MatchPlayerView, 
    MatchListView,
    UserLoginView, 
    UserLogoutView,
    WelcomeView,
    MatchPlaysDataView,  # nuevo endpoint JSON
    MatchCSVUploadView,  # NUEVO: endpoint para subir CSV desde el reproductor
    MatchSelectionPresetListCreateView, 
    MatchSelectionPresetDetailView,
    MatchSelectionPresetUploadCSVView,
)
app_name = 'player'

urlpatterns = [
    # Home público de bienvenida (sin cambios)
    path('', WelcomeView.as_view(), name='welcome'),

    # Lista de partidos (requiere login)
    path('matches/', MatchListView.as_view(), name='match_list'),
    
    # Carga de análisis (canonical) y redirect legacy
    path('matches/upload/', AnalysisUploadView.as_view(), name='upload_analysis'),
    path('upload/', RedirectView.as_view(pattern_name='player:upload_analysis', permanent=False)),
    
    # Reproductor (canonical) y redirect legacy
    path('matches/<int:pk>/', MatchPlayerView.as_view(), name='play_match'),
    path('match/<int:pk>/', RedirectView.as_view(pattern_name='player:play_match', permanent=False)),
    
    # Auth: canonical /accounts/login/ y /accounts/logout/ + alias legacy
    path('accounts/login/', UserLoginView.as_view(), name='login'),
    path('accounts/logout/', UserLogoutView.as_view(), name='logout'),
    path('login/', RedirectView.as_view(pattern_name='player:login', permanent=False)),
    path('logout/', RedirectView.as_view(pattern_name='player:logout', permanent=False)),

    # Endpoint JSON para DataTables con las jugadas del partido
    path('matches/<int:pk>/plays-data/', MatchPlaysDataView.as_view(), name='plays_data'),

    # NUEVO: subir/actualizar CSV directamente en el reproductor
    path('matches/<int:pk>/upload-csv/', MatchCSVUploadView.as_view(), name='upload_csv_match'),

    # API read-only
    path('api/', include('player.api.urls')),  

    # NUEVO: presets de selección de partidos
    path('matches/<int:pk>/presets/', MatchSelectionPresetListCreateView.as_view(), name='match_presets'),
    path('matches/<int:pk>/presets/<int:preset_id>/', MatchSelectionPresetDetailView.as_view(), name='match_preset_detail'),
    path('matches/<int:pk>/presets/upload-csv/', MatchSelectionPresetUploadCSVView.as_view(), name='match_preset_upload_csv'),
]