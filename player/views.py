# player/views.py
import csv
import io
from urllib.parse import urlparse, parse_qs
from django.shortcuts import redirect, render
from django.contrib.auth import logout
from django.views.generic import FormView, DetailView, ListView,View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .forms import AnalysisUploadForm
from .models import Match, Play
from django.core.paginator import Paginator
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.db.models import Q, OuterRef, Subquery
import datetime
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP

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

# --- Utilidades CSV ---
def get_any(row, *keys, default=''):
    """Obtiene el primer valor no vacío buscando por múltiples claves (case-insensitive)."""
    # Acceso directo primero (respetar orden)
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() != '':
            return str(v).strip()
        # Probar variantes de capitalización comunes
        for alt in (k.upper(), k.lower(), k.title()):
            v = row.get(alt)
            if v is not None and str(v).strip() != '':
                return str(v).strip()
    # Búsqueda case-insensitive total
    row_ci = {str(k).strip().lower(): v for k, v in row.items()}
    for k in keys:
        v = row_ci.get(str(k).strip().lower())
        if v is not None and str(v).strip() != '':
            return str(v).strip()
    return default

# --- Conversor de Tiempo a Decimal con 3 decimales ---
def parse_time_to_seconds(time_str):
    """Convierte 'HH:MM:SS.micro' o 'MM:SS' a Decimal con 3 decimales."""
    if not time_str:
        return Decimal('0.000')
    try:
        s = str(time_str).strip()
        parts = s.split(':')
        if len(parts) == 2:
            h = 0
            m = int(parts[0])
            sec_part = parts[1]
        else:
            h = int(parts[0])
            m = int(parts[1])
            sec_part = parts[2]
        if '.' in sec_part:
            s_int, s_frac = sec_part.split('.', 1)
            secs = int(s_int)
            micro = int(s_frac[:6].ljust(6, '0'))  # microsegundos
        else:
            secs = int(sec_part)
            micro = 0
        total = (h * 3600) + (m * 60) + secs + (Decimal(micro) / Decimal(1_000_000))
        return (Decimal(total).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP))
    except Exception:
        return Decimal('0.000')


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

class WelcomeView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('player:match_list')
        return render(request, 'player/welcome.html')


# --- Vistas ---
class AnalysisUploadView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = 'player/match_form.html'
    form_class = AnalysisUploadForm
    login_url = reverse_lazy('player:login')
    redirect_field_name = 'next'
    # Usuarios autenticados sin permiso -> 403
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff
    
    def form_valid(self, form):
        # Recogemos los nuevos datos del formulario
        home_team_name = form.cleaned_data['home_team']
        away_team_name = form.cleaned_data['away_team']
        youtube_url = form.cleaned_data['youtube_url']
        csv_file = form.cleaned_data['csv_file']
        match_date = form.cleaned_data['match_date']
        
        video_id = get_youtube_video_id(youtube_url)
        if not video_id:
            form.add_error('youtube_url', 'La URL de YouTube no es válida.')
            return self.form_invalid(form)

        # Usamos get_or_create y pasamos los nuevos datos en 'defaults'
        match, created = Match.objects.get_or_create(
            video_id=video_id,
            defaults={
                'home_team': home_team_name,
                'away_team': away_team_name,
                'match_date': match_date,
            }
        )

        # Si el partido ya existía, actualizamos los nombres por si cambiaron
        if not created:
            match.home_team = home_team_name
            match.away_team = away_team_name
            match.match_date = match_date
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
                    inicio=parse_time_to_seconds(get_any(row, 'INICIO')),
                    fin=parse_time_to_seconds(get_any(row, 'FIN')),
                    
                    # El resto de los campos se quedan igual
                    arbitro=get_any(row, 'Arbitro'),
                    canal_inicio=get_any(row, 'CANAL INICIO'),
                    evento=get_any(row, 'EVENTO'),
                    equipo=get_any(row, 'Equipo', 'EQUIPO'),
                    ficha=get_any(row, 'Ficha'),
                    inicia=get_any(row, 'INICIA'),
                    resultado=get_any(row, 'Resultado', 'RESULTADO'),
                    termina=get_any(row, 'TERMINA'),
                    tiempo=get_any(row, 'TIEMPO'),
                    torneo=get_any(row, 'Torneo'),
                    zona_fin=get_any(row, 'ZONA FIN'),
                    zona_inicio=get_any(row, 'ZONA INICIO'),
                    # Nuevos campos
                    situacion=get_any(row, 'situacion', 'SITUACION'),
                    jugadores=get_any(row, 'JUGADORES'),
                    sigue_con=get_any(row, 'SIGUE CON'),
                    pos_tiro=get_any(row, 'POS TIRO'),
                    set_play=get_any(row, 'SET'),
                    tiro=get_any(row, 'TIRO'),
                    tipo=get_any(row, 'TIPO'),
                    accion=get_any(row, 'ACCION'),
                    termina_en=get_any(row, 'TERMINA EN'),
                    sancion=get_any(row, 'SANCION'),
                    transicion=get_any(row, 'TRANSICION'),
                )
        except Exception as e:
            form.add_error(None, f"Hubo un error al leer el archivo CSV: {e}")
            return self.form_invalid(form)
        
        return redirect('player:play_match', pk=match.pk)

class MatchPlayerView(LoginRequiredMixin, DetailView):
    model = Match
    template_name = 'player/match_player.html'
    context_object_name = 'match'
    login_url = reverse_lazy('player:login')
    redirect_field_name = 'next'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.get_object()
        
        plays_list = match.plays.all().order_by('inicio')

        filter_params = {}
        evento_filter = self.request.GET.get('evento', '')
        equipo_filter = self.request.GET.get('equipo', '')
        zona_inicio_filter = self.request.GET.get('zona_inicio', '')
        zona_fin_filter = self.request.GET.get('zona_fin', '')
        inicia_filter = self.request.GET.get('inicia', '')
        situacion_filter = self.request.GET.get('situacion', '')

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
        if situacion_filter:
            plays_list = plays_list.filter(situacion=situacion_filter)
            filter_params['situacion'] = situacion_filter
        
        paginator = Paginator(plays_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['page_obj'] = page_obj
        context['filter_params'] = filter_params
        
        # Opciones únicas normalizadas (sin duplicados por mayúsculas/espacios)
        def unique_options(qs, field):
            values = qs.values_list(field, flat=True)
            seen = set()
            opts = []
            for v in values:
                if not v:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                key = s.lower()
                if key not in seen:
                    seen.add(key)
                    opts.append(s)
            return sorted(opts, key=lambda x: x.lower())

        base_plays = match.plays.all()
        context['equipo_options'] = unique_options(base_plays, 'equipo')
        context['situacion_options'] = unique_options(base_plays, 'situacion')
        context['zona_inicio_options'] = unique_options(base_plays, 'zona_inicio')
        context['zona_fin_options'] = unique_options(base_plays, 'zona_fin')
        context['inicia_options'] = unique_options(base_plays, 'inicia')
        context['evento_options'] = unique_options(base_plays, 'evento')

        return context
    
    
class MatchListView(LoginRequiredMixin, ListView):
    model = Match
    template_name = 'player/match_list.html'
    context_object_name = 'matches'
    paginate_by = 10 # Mostramos 12 partidos por página
    login_url = reverse_lazy('player:login')
    redirect_field_name = 'next'

    def get_queryset(self):
        user = self.request.user
        queryset = Match.objects.all()

        # --- Lógica de filtrado para usuarios normales (sin cambios) ---
        if user.is_authenticated and not user.is_staff and hasattr(user, 'profile') and user.profile.team:
            user_team_name = user.profile.team.name  # comparar por nombre, no por instancia
            filter_type = self.request.GET.get('filter', 'own')

            if filter_type == 'own':
                queryset = queryset.filter(Q(home_team__iexact=user_team_name) | Q(away_team__iexact=user_team_name))
            elif filter_type == 'rivals':
                queryset = queryset.exclude(Q(home_team__iexact=user_team_name) | Q(away_team__iexact=user_team_name))
        
        # --- Filtros de búsqueda ---
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(Q(home_team__icontains=q) | Q(away_team__icontains=q))
        
        # --- Fechas con validación y feedback ---
        date_from_str = self.request.GET.get('date_from', '').strip()
        date_to_str = self.request.GET.get('date_to', '').strip()
        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = datetime.date.fromisoformat(date_from_str)
            except ValueError:
                messages.warning(self.request, "Fecha 'Desde' inválida. Use AAAA-MM-DD.")
        if date_to_str:
            try:
                date_to = datetime.date.fromisoformat(date_to_str)
            except ValueError:
                messages.warning(self.request, "Fecha 'Hasta' inválida. Use AAAA-MM-DD.")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        # --- Anotar resultado del partido desde Play (primer valor no vacío) ---
        result_sq = Play.objects.filter(match=OuterRef('pk')).exclude(resultado='').values('resultado')[:1]
        queryset = queryset.annotate(match_result=Subquery(result_sq))

        # --- Devolver instancias del modelo (sin values) para evitar problemas en templates/regroup ---
        # Opcionalmente podríamos optimizar columnas con only(), pero mantenemos simpleza por claridad
        
        # --- LÓGICA DE ORDENAMIENTO SEGURA ---
        sort_by = self.request.GET.get('sort', '-match_date') # Por defecto, por fecha del partido
        valid_sort_options = ['home_team', 'away_team', 'created_at', '-created_at', 'match_date', '-match_date']
        if sort_by in valid_sort_options:
            if sort_by in ('match_date', '-match_date'):
                queryset = queryset.order_by(sort_by, '-created_at')
            else:
                queryset = queryset.order_by(sort_by)
        else:
            queryset = queryset.order_by('-match_date', '-created_at')
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_filter'] = self.request.GET.get('filter', 'own')
        # Pasamos el ordenamiento current_filter a la plantilla para mantener el estado del filtro
        context['current_sort'] = self.request.GET.get('sort', '-match_date')
        return context