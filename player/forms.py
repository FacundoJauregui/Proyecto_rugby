# player/forms.py
from django import forms

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
    
    # Los campos de siempre
    youtube_url = forms.URLField(
        label="URL del Video de YouTube",
        required=True,
        widget=forms.URLInput(attrs={'class': 'form-control'})
    )
    csv_file = forms.FileField(
        label="Archivo CSV de Análisis",
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )