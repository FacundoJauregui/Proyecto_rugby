# player/forms.py
from django import forms
from .models import Tournament, Match

class AnalysisUploadForm(forms.Form):
    # Añadimos los campos para los equipos
    home_team = forms.CharField(
        label="Nombre del Equipo Local",
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    away_team = forms.CharField(
        label="Nombre del Equipo Visitante",
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    # Nueva fecha del partido
    match_date = forms.DateField(
        label="Fecha del Partido",
        required=True,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    # Nuevo: seleccionar Torneo (opcional por compatibilidad)
    tournament = forms.ModelChoiceField(
        label="Torneo",
        required=False,
        queryset=Tournament.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    # Nuevo: seleccionar División (opcional)
    division = forms.ChoiceField(
        label="División",
        required=False,
        choices=[('', '---------')] + list(Match.Division.choices),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Los campos de siempre
    youtube_url = forms.URLField(
        label="URL del Video de YouTube",
        required=True,
        widget=forms.URLInput(attrs={'class': 'form-control'})
    )
    csv_file = forms.FileField(
        label="Archivo CSV de Análisis (opcional)",
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cargar torneos ordenados por país y nombre
        self.fields['tournament'].queryset = Tournament.objects.select_related('country').order_by('country__name', 'name', 'season')