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

from urllib.parse import urlparse, parse_qs

def get_youtube_video_id(url):
    if not url:
        return None
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            if 'v' in p:
                return p['v'][0]
        if query.path.startswith('/embed/'):
            return query.path.split('/')[2]
        if query.path.startswith('/v/'):
            return query.path.split('/')[2]
    return None

class MatchUpdateForm(forms.ModelForm):
    youtube_url = forms.URLField(
        label="URL del Video de YouTube",
        required=True,
        widget=forms.URLInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )

    class Meta:
        model = Match
        fields = ['home_team', 'away_team', 'match_date', 'tournament', 'division', 'youtube_url']
        widgets = {
            'home_team': forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'}),
            'away_team': forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'}),
            'match_date': forms.DateInput(attrs={'type': 'date', 'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'}),
            'tournament': forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white'}),
            'division': forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tournament'].queryset = Tournament.objects.select_related('country').order_by('country__name', 'name', 'season')
        if self.instance and self.instance.video_id:
            # Set initial value for youtube_url based on video_id
            self.initial['youtube_url'] = f"https://www.youtube.com/watch?v={self.instance.video_id}"

    def clean_youtube_url(self):
        url = self.cleaned_data.get('youtube_url')
        video_id = get_youtube_video_id(url)
        if not video_id:
            raise forms.ValidationError("URL de YouTube no es válida.")
        
        # Check uniqueness excluding self
        if Match.objects.filter(video_id=video_id).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este video ya está asignado a otro partido.")
            
        return url

    def clean(self):
        cleaned_data = super().clean()
        home = cleaned_data.get('home_team')
        away = cleaned_data.get('away_team')
        if home and away and home.lower() == away.lower():
            raise forms.ValidationError("No pueden ser los 2 equipos iguales.")
        return cleaned_data

    def save(self, commit=True):
        m = super().save(commit=False)
        url = self.cleaned_data.get('youtube_url')
        m.video_id = get_youtube_video_id(url)
        if commit:
            m.save()
        return m
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile, Team

class AdminUserCreationForm(UserCreationForm):
    first_name = forms.CharField(
        label="Nombre", 
        max_length=30, 
        required=False, 
        widget=forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    last_name = forms.CharField(
        label="Apellido", 
        max_length=30, 
        required=False, 
        widget=forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    email = forms.EmailField(
        label="Correo electrónico", 
        required=False, 
        widget=forms.EmailInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    role = forms.ChoiceField(
        label="Rol", 
        choices=Profile.Role.choices, 
        required=True,
        widget=forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white'})
    )
    team = forms.ModelChoiceField(
        label="Equipo Principal", 
        queryset=Team.objects.all(), 
        required=False, 
        empty_label="Ninguno", 
        widget=forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'last_name') + UserCreationForm.Meta.fields + ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if 'class' not in self.fields[field].widget.attrs:
                self.fields[field].widget.attrs['class'] = 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'
            
            # Ocultar todos los help_text nativos
            if hasattr(self.fields[field], 'help_text'):
                self.fields[field].help_text = ''

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            profile, created = Profile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.team = self.cleaned_data['team']
            profile.save()
        return user

class CoachPlayerCreationForm(UserCreationForm):
    first_name = forms.CharField(
        label="Nombre", 
        max_length=30, 
        required=True, 
        widget=forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    last_name = forms.CharField(
        label="Apellido", 
        max_length=30, 
        required=True, 
        widget=forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    email = forms.EmailField(
        label="Correo electrónico", 
        required=True, 
        widget=forms.EmailInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'last_name') + UserCreationForm.Meta.fields + ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if 'class' not in self.fields[field].widget.attrs:
                self.fields[field].widget.attrs['class'] = 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'
            
            # Ocultar todos los help_text nativos
            if hasattr(self.fields[field], 'help_text'):
                self.fields[field].help_text = ''

    def save(self, commit=True, coach_team=None):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            profile, created = Profile.objects.get_or_create(user=user)
            profile.role = Profile.Role.JUGADOR
            profile.team = coach_team
            profile.save()
        return user


from .models import Invitation, Team

class InvitationForm(forms.ModelForm):
    archivo_excel = forms.FileField(
        label="Opción Masiva: Archivo Excel con correos en Columna A",
        required=False,
        widget=forms.FileInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white', 'accept': '.xlsx'})
    )
    
    team = forms.ModelChoiceField(
        label="Equipo al que se invita (Sólo Admin)",
        queryset=Team.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white'})
    )

    class Meta:
        model = Invitation
        fields = ['team', 'role', 'email']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white', 'placeholder': 'usuario@ejemplo.com'}),
            'role': forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:text-white'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        self.fields['email'].required = False
        
        # Si NO es superuser, ocultamos el selector de equipo porque usaremos el del perfil
        if self.user and not getattr(self.user, 'is_superuser', False):
            self.fields['team'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        archivo_excel = cleaned_data.get('archivo_excel')
        team = cleaned_data.get('team')

        if not email and not archivo_excel:
            raise forms.ValidationError("Debes ingresar un email mano a mano O subir un archivo Excel.")
            
        if getattr(self.user, 'is_superuser', False) and not team:
             self.add_error('team', "Como administrador, debes seleccionar a qué equipo vas a invitar.")
             
        return cleaned_data

class PlayerRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        label="Nombre", 
        max_length=30, 
        required=True, 
        widget=forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )
    last_name = forms.CharField(
        label="Apellido", 
        max_length=30, 
        required=True, 
        widget=forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'last_name', 'username')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if 'class' not in self.fields[field].widget.attrs:
                self.fields[field].widget.attrs['class'] = 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white'
            if hasattr(self.fields[field], 'help_text'):
                self.fields[field].help_text = ''
