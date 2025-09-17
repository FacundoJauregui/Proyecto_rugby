# player/views.py
import csv
import io
from urllib.parse import urlparse, parse_qs
from django.shortcuts import redirect
from django.contrib.auth import logout
from django.views.generic import FormView, DetailView, ListView,View
from .forms import AnalysisUploadForm
from .models import Match, Play
from django.core.paginator import Paginator
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

# --- Función Auxiliar para la URL de YouTube (la dejamos como está) ---
def get_youtube_video_id(url):
    # ... (código de la función sin cambios)
    if url is None:
        return None
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[2]
    return None

# --- NUEVA FUNCIÓN MÁGICA: El Conversor de Tiempo ---
def parse_time_to_seconds(time_str):
    """
    Convierte un string de tiempo 'HH:MM:SS.ms' a segundos totales.
    Ej: '00:01:24.080000' -> 84.08
    """
    if not time_str:
        return 0.0
    try:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        # La parte de los segundos puede tener decimales
        s_parts = parts[2].split('.')
        s = int(s_parts[0])
        ms = int(s_parts[1]) if len(s_parts) > 1 else 0
        
        total_seconds = (h * 3600) + (m * 60) + s + (ms / 1000000)
        return total_seconds
    except (ValueError, IndexError):
        # Si el formato es incorrecto, devolvemos 0.0 para no romper la carga
        return 0.0


# --- VISTAS DE AUTENTICACIÓN ---
class UserLoginView(LoginView):
    template_name = 'player/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('player:match_list')

class UserLogoutView(View):
    def get(self, request, *args, **kwargs):
        # Cerramos la sesión del usuario
        logout(request)
        # Redirigimos a la página de login
        return redirect('player:login')


# --- Vistas ---
class AnalysisUploadView(FormView):
    template_name = 'player/match_form.html'
    form_class = AnalysisUploadForm
    
    def form_valid(self, form):
        # Recogemos los nuevos datos del formulario
        home_team_name = form.cleaned_data['home_team']
        away_team_name = form.cleaned_data['away_team']
        youtube_url = form.cleaned_data['youtube_url']
        csv_file = form.cleaned_data['csv_file']
        
        video_id = get_youtube_video_id(youtube_url)
        if not video_id:
            form.add_error('youtube_url', 'La URL de YouTube no es válida.')
            return self.form_invalid(form)

        # Usamos get_or_create y pasamos los nuevos datos en 'defaults'
        match, created = Match.objects.get_or_create(
            video_id=video_id,
            defaults={
                'home_team': home_team_name,
                'away_team': away_team_name
            }
        )

        # Si el partido ya existía, actualizamos los nombres por si cambiaron
        if not created:
            match.home_team = home_team_name
            match.away_team = away_team_name
            match.save()
            match.plays.all().delete()

        # ... (el resto de la lógica para procesar el CSV se queda exactamente igual) ...
        try:
            data_set = csv_file.read().decode('UTF-8')
            io_string = io.StringIO(data_set)
            reader = csv.DictReader(io_string)
            for row in reader:
                Play.objects.create(
                    match=match,
                    # Usamos nuestra nueva función para convertir los tiempos
                    inicio=parse_time_to_seconds(row.get('INICIO')),
                    fin=parse_time_to_seconds(row.get('FIN')),
                    
                    # El resto de los campos se quedan igual
                    arbitro=row.get('Arbitro', ''),
                    canal_inicio=row.get('CANAL INICIO', ''),
                    evento=row.get('EVENTO', ''),
                    equipo=row.get('Equipo', ''),
                    ficha=row.get('Ficha', ''),
                    inicia=row.get('INICIA', ''),
                    resultado=row.get('Resultado', ''),
                    termina=row.get('TERMINA', ''),
                    tiempo=row.get('TIEMPO', ''),
                    torneo=row.get('Torneo', ''),
                    zona_fin=row.get('ZONA FIN', ''),
                    zona_inicio=row.get('ZONA INICIO', ''),
                )
        except Exception as e:
            form.add_error(None, f"Hubo un error al leer el archivo CSV: {e}")
            return self.form_invalid(form)
        
        return redirect('player:play_match', pk=match.pk)

class MatchPlayerView(DetailView):
    model = Match
    template_name = 'player/match_player.html'
    context_object_name = 'match'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.get_object()
        
        # Obtenemos todas las jugadas del partido para empezar
        plays_list = match.plays.all().order_by('inicio') # Ordenamos por tiempo de inicio

        # --- Lógica de Filtros ---
        filter_params = {}
        # Recogemos los valores de los filtros desde la URL (GET request)
        evento_filter = self.request.GET.get('evento', '')
        equipo_filter = self.request.GET.get('equipo', '')
        zona_inicio_filter = self.request.GET.get('zona_inicio', '')
        zona_fin_filter = self.request.GET.get('zona_fin', '')
        inicia_filter = self.request.GET.get('inicia', '')

        # Aplicamos los filtros si tienen algún valor
        if evento_filter:
            plays_list = plays_list.filter(evento=evento_filter)
            filter_params['evento'] = evento_filter
        if equipo_filter:
            plays_list = plays_list.filter(equipo=equipo_filter)
            filter_params['equipo'] = equipo_filter
        if zona_inicio_filter:
            plays_list = plays_list.filter(zona_inicio=zona_inicio_filter)
            filter_params['zona_inicio'] = zona_inicio_filter
        if zona_fin_filter:
            plays_list = plays_list.filter(zona_fin=zona_fin_filter)
            filter_params['zona_fin'] = zona_fin_filter
        if inicia_filter:
            plays_list = plays_list.filter(inicia=inicia_filter)
            filter_params['inicia'] = inicia_filter
        
        # --- Lógica de Paginación ---
        # Partimos la lista de jugadas (ya filtrada) en páginas de 10 jugadas cada una
        paginator = Paginator(plays_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Enviamos los datos al template
        context['page_obj'] = page_obj  # Las jugadas paginadas
        context['filter_params'] = filter_params # Los filtros aplicados, para mantenerlos al cambiar de página
        
        # --- Opciones para los dropdowns de los filtros ---
        # Obtenemos los valores únicos para que el usuario pueda elegir
        base_plays = match.plays.all()
        context['evento_options'] = base_plays.values_list('evento', flat=True).distinct()
        context['equipo_options'] = base_plays.values_list('equipo', flat=True).distinct()
        context['zona_inicio_options'] = base_plays.values_list('zona_inicio', flat=True).distinct()
        context['zona_fin_options'] = base_plays.values_list('zona_fin', flat=True).distinct()
        context['inicia_options'] = base_plays.values_list('inicia', flat=True).distinct()

        return context
    
    
class MatchListView(ListView):
    model = Match
    template_name = 'player/match_list.html'
    context_object_name = 'matches'
    paginate_by = 12 # Mostramos 12 partidos por página

    def get_queryset(self):
        # Ordenamos los partidos del más nuevo al más viejo
        return Match.objects.all().order_by('-created_at')