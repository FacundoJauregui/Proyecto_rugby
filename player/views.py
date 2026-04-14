# player/views.py
"""Vistas y utilidades de la app `player`.

Estructura general del módulo:
1. Helpers para ingestión y validación de CSV (lectura flexible de encoding,
    detección de delimitadores, normalización y validación robusta de cabeceras).
2. Parseo y normalización de tiempos hacia `Decimal` para precisión (3 decimales).
3. Vistas de autenticación mínimas (login/logout/bienvenida).
4. Flujo de carga inicial de un partido + jugadas (`AnalysisUploadView`).
5. Reproductor y exportación filtrada de jugadas (`MatchPlayerView`).
6. Listado de partidos con reglas de visibilidad avanzadas para entrenadores
    (`MatchListView`).
7. Endpoints JSON para proveer datos paginados a DataTables (`MatchPlaysDataView`).
8. Subida/actualización posterior de jugadas desde el reproductor (`MatchCSVUploadView`).
9. Gestión de presets de selección de jugadas para reusar clips (`MatchSelectionPreset*`).

Cada bloque incluye comentarios sobre decisiones de diseño, validaciones y
performance (uso de `bulk_create`, `Subquery`, `Exists`, índices y filtrado).
"""
import csv
import io
import os
import re
import unicodedata
import datetime
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from urllib.parse import urlparse, parse_qs

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, OuterRef, Subquery, Exists, F
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import FormView, DetailView, ListView, View, UpdateView
from django.core.files.uploadedfile import UploadedFile

from .forms import AnalysisUploadForm, MatchUpdateForm
from .models import Match, Play, Tournament, Country, CoachTournamentTeamParticipation, Team, SelectionPreset
# from django.views.decorators.cache import cache_page
# from django.utils.decorators import method_decorator

# --- Helper de lectura CSV con detección simple de encoding ---
def read_uploaded_csv_text(uploaded_file):
    """Lee un archivo subido (InMemory/Temporary) y devuelve texto decodificado.
    Intenta utf-8-sig, utf-8, cp1252 y latin-1 para evitar errores de decodificación.
    """
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    raw = uploaded_file.read()
    for enc in ('utf-8-sig', 'utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252', 'latin-1'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    # Si no se pudo decodificar, relanza error con mensaje claro
    raise UnicodeDecodeError('decode', raw, 0, 1, 'No se pudo decodificar el CSV. Guarde como UTF-8 y reintente.')

# --- Helper: crear DictReader detectando delimitador automáticamente ---
def make_dict_reader_from_text(text: str) -> csv.DictReader:
    """Crea un DictReader detectando delimitador (coma, punto y coma, tab o pipe)."""
    if not isinstance(text, str):
        text = str(text or '')
    # quitar BOM manual si quedó
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')
    sample = text[:8192]
    delimiters = [',', ';', '\t', '|']
    delim = ','
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=delimiters)
        delim = getattr(dialect, 'delimiter', ',') or ','
    except Exception:
        # Heurística por primera línea
        first = sample.splitlines()[0] if sample else ''
        counts = {d: first.count(d.replace('\\t', '\t')) for d in delimiters}
        delim = max(counts, key=counts.get)
        if counts.get(delim, 0) == 0:
            delim = ','
    # Construir el reader
    return csv.DictReader(io.StringIO(text), delimiter=('\t' if delim == '\\t' else delim))

# --- Helper: validar orden exacto de columnas ---
# Encabezados requeridos (orden no importa durante la validación flexible)
_BASE_REQUIRED_HEADERS_ORDER = [
    'JUGADA','ARBITRO','CANAL DE INICIO','EVENTO','EQUIPO','FIN','FICHA','INICIA','INICIO',
    'MARCADOR FINAL','TERMINA','TIEMPO','TORNEO','ZONA FIN','ZONA INICIO','RESULTADO','JUGADORES',
    'SIGUE CON','POS TIRO','SET','TIRO','TIPO','ACCION','TERMINA EN','SANCION','TRANSICION'
]

# Requeridas adicionales agregadas al final del CSV
REQUIRED_HEADERS = _BASE_REQUIRED_HEADERS_ORDER + ['DESDE','CANAL','FASES','OPCION','ZONA']

# Encabezados opcionales (si faltan, importamos en blanco)
OPTIONAL_HEADERS = ['SITUACION PENAL','NUEVA CATEGORIA','ACERCAR','ALEJAR','SITUACION','TERMINA EN']

# Orden recomendado para exportar (incluye opcionales y luego las nuevas al final)
EXPORT_HEADERS_ORDER = _BASE_REQUIRED_HEADERS_ORDER + OPTIONAL_HEADERS + ['DESDE','CANAL','FASES','OPCION','ZONA']

# Aceptar sinónimos/combinaciones para robustez al importar
HEADER_SYNONYMS = {
    'CANAL DE INICIO': ['CANAL DE INICIO', 'CANAL INICIO'],
    'DESDE': ['DESDE', 'FROM'],
    'CANAL': ['CANAL', 'CHANNEL'],
    'FASES': ['FASES', 'FASE'],
    'OPCION': ['OPCION', 'OPTION'],
    'ZONA': ['ZONA', 'ZONE'],
    'ZONA FIN': ['ZONA FIN', 'ZONA_FINAL', 'ZONA FINAL'],
    'ZONA INICIO': ['ZONA INICIO', 'ZONA_INICIO', 'ZONA DE INICIO'],
    'SIGUE CON': ['SIGUE CON', 'SIGUE_CON'],
    'POS TIRO': ['POS TIRO', 'POS_TIRO', 'POS. TIRO'],
    'TERMINA EN': ['TERMINA EN', 'TERMINA_EN', 'TERMINA'],
    'MARCADOR FINAL': ['MARCADOR FINAL', 'MARCADOR_FINAL'],
    'INICIA': ['INICIA', 'INICIA DESDE', 'INICIA_DESDE'],
    'SITUACION': ['SITUACION'],
    'SITUACION PENAL': ['SITUACION PENAL', 'SITUACION_PENAL', 'SIT PENAL', 'PENAL SITUACION'],
    'NUEVA CATEGORIA': ['NUEVA CATEGORIA', 'NUEVA_CATEGORIA', 'CATEGORIA NUEVA', 'CATEGORIA', 'NUEVA SUBCATEGORIA', 'NUEVA_SUBCATEGORIA', 'SUBCATEGORIA NUEVA'],
    'ACERCAR': ['ACERCAR', 'ZOOM IN', 'ZOOM_IN'],
    'ALEJAR': ['ALEJAR', 'ZOOM OUT', 'ZOOM_OUT'],
}

# (Se removieron helpers de video agregados temporalmente)

def validate_headers_strict(fieldnames):
    headers = [h.strip().upper() for h in (fieldnames or [])]
    expected = EXPORT_HEADERS_ORDER
    if len(headers) != len(expected):
        return False, f"Cantidad de columnas inválida. Se esperaban {len(expected)} columnas en este orden: {', '.join(expected)}. Se recibieron {len(headers)}: {', '.join(headers)}"
    for idx, (h, e) in enumerate(zip(headers, expected), start=1):
        if h != e:
            return False, f"El orden de columnas no es el esperado en la posición {idx}. Esperado: '{e}', recibido: '{h}'. Orden completo esperado: {', '.join(expected)}"
    return True, ''

# NUEVO: validación flexible (acepta cualquier orden, ignora extras)
def _norm_key(s: str) -> str:
    """Normaliza cabeceras: minúsculas, sin tildes, espacios compactados y guiones bajos como espacios."""
    if s is None:
        return ''
    s = str(s).strip()
    s = s.replace('_', ' ')
    # quitar tildes/diacríticos
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    # colapsar espacios
    s = re.sub(r'\s+', ' ', s)
    return s.lower()

def validate_headers_flexible(fieldnames):
    """
    Verifica que el CSV contenga todas las columnas requeridas (case-insensitive),
    permite orden distinto y columnas extra. Devuelve (ok, msg, header_map).
    header_map: dict con clave UPPER -> nombre exacto tal como aparece en CSV.
    """
    if not fieldnames:
        return False, "CSV vacío o sin encabezados", {}
    incoming = {_norm_key(h): h for h in (fieldnames or [])}
    header_map = {}
    missing = []
    for req in REQUIRED_HEADERS:
        candidates = HEADER_SYNONYMS.get(req, [req])
        found_key = None
        for cand in candidates:
            key = _norm_key(cand)
            if key in incoming:
                found_key = key
                break
        if found_key is not None:
            header_map[req.upper()] = incoming[found_key]
        else:
            missing.append(req)
    # Mapear opcionales si existen
    for opt in OPTIONAL_HEADERS:
        candidates = HEADER_SYNONYMS.get(opt, [opt])
        for cand in candidates:
            key = _norm_key(cand)
            if key in incoming:
                header_map[opt.upper()] = incoming[key]
                break
    if missing:
        return False, f"Faltan columnas obligatorias en el CSV: {', '.join(missing)}", {}
    return True, '', header_map

# --- Helper: extraer marcador desde campo 'marcador_final' ---
def _parse_score_from_marcador(marcador: str):
    """Extrae (home_score, away_score) de un string tipo '24 - 17' o '24-17'.
    Devuelve (None, None) si no puede parsear."""
    if not marcador:
        return None, None
    m = re.match(r'^\s*(\d+)\s*-\s*(\d+)\s*$', marcador.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


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

# NUEVO: Versión rápida cuando ya tenemos el diccionario normalizado por fila
def get_any_ci(row_ci: dict, *keys, default=''):
    """Obtiene el primer valor no vacío desde un diccionario con claves en minúsculas y valores ya strippeados."""
    for k in keys:
        v = row_ci.get(str(k).strip().lower())
        if v:
            return v
    return default

# --- Conversor de Tiempo a Decimal con 3 decimales ---
def parse_time_to_seconds(time_str):
    """Convierte a Decimal segundos con 3 decimales.
    Acepta:
      - 'HH:MM:SS' o 'HH:MM:SS.micro'
      - 'MM:SS' o 'MM:SS.micro'
      - 'YYYY-MM-DD HH:MM:SS[.micro]' (usa la parte de la hora)
      - Valor único en segundos (p.ej. '1044.360')
    """
    if not time_str:
        return Decimal('0.000')
    try:
        s = str(time_str).strip()
        # Si viene datetime completo, tomar la parte de hora al final
        if ' ' in s:
            s = s.split()[-1]
        # Normalizar separador decimal con punto
        if ',' in s and '.' not in s:
            s = s.replace(',', '.')
        parts = s.split(':')
        if len(parts) == 1:
            # Solo segundos (con o sin decimales)
            secs = float(parts[0])
            total = Decimal(secs).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            return total
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
            micro = int(s_frac[:6].ljust(6, '0'))
        else:
            secs = int(sec_part)
            micro = 0
        total = (h * 3600) + (m * 60) + secs + (Decimal(micro) / Decimal(1_000_000))
        return Decimal(total).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.000')


# --- VISTAS DE AUTENTICACIÓN ---
class UserLoginView(LoginView):
    template_name = 'player/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('player:match_list')

class UserLogoutView(View):
    """Cierra la sesión actual y redirige al formulario de login.

    Solo implementa GET por simplicidad; en caso de necesitar seguridad reforzada
    se podría migrar a POST + CSRF.
    """
    def get(self, request, *args, **kwargs):
        logout(request)  # Invalida la sesión.
        return redirect('player:login')  # Regresa a pantalla de autenticación.

class WelcomeView(View):
    """Página inicial pública.

    Si el usuario ya está autenticado lo lleva directamente al listado de
    partidos evitando mostrar la pantalla de bienvenida.
    """
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
        home_team_name = form.cleaned_data['home_team'].strip()
        away_team_name = form.cleaned_data['away_team'].strip()
        youtube_url = form.cleaned_data['youtube_url']
        csv_file = form.cleaned_data['csv_file']
        match_date = form.cleaned_data['match_date']
        tournament = form.cleaned_data.get('tournament')
        division = form.cleaned_data.get('division') or None

        # Validación temprana: equipos no pueden ser iguales
        if home_team_name.lower() == away_team_name.lower():
            messages.warning(self.request, "No pueden ser los 2 equipos iguales.")
            return self.render_to_response(self.get_context_data(form=form))

        video_id = get_youtube_video_id(youtube_url)
        if not video_id:
            form.add_error('youtube_url', 'La URL de YouTube no es válida.')
            return self.form_invalid(form)

        # NUEVO: Evitar duplicados por (home_team, away_team, match_date)
        if Match.objects.filter(
            home_team__iexact=home_team_name,
            away_team__iexact=away_team_name,
            match_date=match_date
        ).exists():
            messages.warning(self.request, "Ese partido ya se encuentra cargado.")
            return self.render_to_response(self.get_context_data(form=form))

        match_pk = None
        with transaction.atomic():
            match, created = Match.objects.get_or_create(
                video_id=video_id,
                defaults={
                    'home_team': home_team_name,
                    'away_team': away_team_name,
                    'match_date': match_date,
                    'tournament': tournament,
                    'division': division,
                }
            )
            match_pk = match.pk
            if not created:
                match.home_team = home_team_name
                match.away_team = away_team_name
                match.match_date = match_date
                match.tournament = tournament
                match.division = division
                match.save()
                match.plays.all().delete()

            # Procesar CSV con validación de cabeceras (opcional)
            if csv_file:
                try:
                    data_set = read_uploaded_csv_text(csv_file)
                    reader = make_dict_reader_from_text(data_set)
                    ok, msg, header_map = validate_headers_flexible(reader.fieldnames)
                    if not ok:
                        messages.error(self.request, msg)
                        return self.render_to_response(self.get_context_data(form=form))
                    plays_to_create = []
                    count = 0
                    for row in reader:
                        plays_to_create.append(Play(
                            match=match,
                            jugada=(row.get(header_map['JUGADA']) or '').strip(),
                            arbitro=(row.get(header_map['ARBITRO']) or '').strip(),
                            canal_de_inicio=(row.get(header_map['CANAL DE INICIO']) or '').strip(),
                            desde=(row.get(header_map['DESDE']) or '').strip(),
                            canal=(row.get(header_map['CANAL']) or '').strip(),
                            fases=(row.get(header_map['FASES']) or '').strip(),
                            opcion=(row.get(header_map['OPCION']) or '').strip(),
                            zona=(row.get(header_map['ZONA']) or '').strip(),
                            evento=(row.get(header_map['EVENTO']) or '').strip(),
                            equipo=(row.get(header_map['EQUIPO']) or '').strip(),
                            fin=parse_time_to_seconds(row.get(header_map['FIN']) or ''),
                            ficha=(row.get(header_map['FICHA']) or '').strip(),
                            inicia=(row.get(header_map['INICIA']) or '').strip(),
                            inicio=parse_time_to_seconds(row.get(header_map['INICIO']) or ''),
                            marcador_final=(row.get(header_map['MARCADOR FINAL']) or '').strip(),
                            termina=(row.get(header_map['TERMINA']) or '').strip(),
                            tiempo=(row.get(header_map['TIEMPO']) or '').strip(),
                            torneo=(row.get(header_map['TORNEO']) or '').strip(),
                            zona_fin=(row.get(header_map['ZONA FIN']) or '').strip(),
                            zona_inicio=(row.get(header_map['ZONA INICIO']) or '').strip(),
                            resultado=(row.get(header_map['RESULTADO']) or '').strip(),
                            jugadores=(row.get(header_map['JUGADORES']) or '').strip(),
                            sigue_con=(row.get(header_map['SIGUE CON']) or '').strip(),
                            pos_tiro=(row.get(header_map['POS TIRO']) or '').strip(),
                            set=(row.get(header_map['SET']) or '').strip(),
                            tiro=(row.get(header_map['TIRO']) or '').strip(),
                            tipo=(row.get(header_map['TIPO']) or '').strip(),
                            accion=(row.get(header_map['ACCION']) or '').strip(),
                            termina_en=(row.get(header_map.get('TERMINA EN','')) or '').strip(),
                            sancion=(row.get(header_map['SANCION']) or '').strip(),
                            situacion=(row.get(header_map.get('SITUACION','')) or '').strip(),
                            transicion=(row.get(header_map['TRANSICION']) or '').strip(),
                            situacion_penal=(row.get(header_map.get('SITUACION PENAL','')) or '').strip(),
                            nueva_categoria=(row.get(header_map.get('NUEVA CATEGORIA','')) or '').strip(),
                            acercar=(row.get(header_map.get('ACERCAR','')) or '').strip(),
                            alejar=(row.get(header_map.get('ALEJAR','')) or '').strip(),
                        ))
                        count += 1
                    if plays_to_create:
                        Play.objects.bulk_create(plays_to_create, batch_size=1000)
                        # Intentar extraer marcador final del último play para guardar el resultado
                        last_marcador = next(
                            (p.marcador_final for p in reversed(plays_to_create) if p.marcador_final),
                            None
                        )
                        home, away = _parse_score_from_marcador(last_marcador)
                        if home is not None and match.home_score is None and match.away_score is None:
                            match.home_score = home
                            match.away_score = away
                            match.save(update_fields=['home_score', 'away_score'])
                        messages.success(self.request, f"Se cargaron {count} jugadas al partido.")
                    else:
                        messages.warning(self.request, "El archivo CSV no contenía jugadas válidas.")
                except Exception as e:
                    messages.error(self.request, f"Error al procesar el archivo CSV: {e}")
                    return self.render_to_response(self.get_context_data(form=form))

        # En vez de redirigir, renderizamos la misma vista para mostrar el mensaje y opciones
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Si el formulario fue enviado y existe el partido, pasamos el match_pk
        form = context.get('form')
        if form and hasattr(form, 'cleaned_data'):
            youtube_url = form.cleaned_data.get('youtube_url')
            if youtube_url:
                video_id = get_youtube_video_id(youtube_url)
                match = Match.objects.filter(video_id=video_id).first()
                if match:
                    context['match_pk'] = match.pk
        # Si no, intentamos obtener el último partido creado por el usuario (fallback)
        if 'match_pk' not in context:
            last_match = Match.objects.order_by('-id').first()
            if last_match:
                context['match_pk'] = last_match.pk

        # Determinar si mostrar el bloque de subir CSV en el reproductor del partido
        user = self.request.user
        can_upload = False
        if user.is_authenticated:
            if user.is_staff:
                can_upload = True
            else:
                profile = getattr(user, 'profile', None)
                if profile and profile.role == 'COACH':
                    can_upload = True

        has_plays = False
        match_pk = context.get('match_pk')
        if match_pk:
            try:
                match_obj = Match.objects.get(pk=match_pk)
                has_plays = match_obj.plays.exists()
            except Match.DoesNotExist:
                has_plays = False

        context['can_upload_csv_on_match'] = (not has_plays) and can_upload

        return context
    
# @method_decorator(cache_page(60*5), name='dispatch')
class MatchPlayerView(LoginRequiredMixin, DetailView):
    # Reproductor del partido y exportación CSV del conjunto filtrado/seleccionado.
    model = Match
    template_name = 'player/match_player.html'
    context_object_name = 'match'
    login_url = reverse_lazy('player:login')
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        # Guard: si el partido no tiene video, redirigir al listado con mensaje
        match_obj = self.get_object()
        if not match_obj.video_id:
            messages.warning(request, "Este partido aún no tiene video de análisis cargado.")
            return redirect('player:match_list')

        # Exportación CSV del conjunto filtrado (sin paginar) o por selección
        if request.GET.get('export') == 'csv':
            self.object = self.get_object()
            match = self.object
            plays_list = match.plays.all().order_by('inicio')

            # Copiamos filtros actuales
            evento_filter = request.GET.get('evento', '')
            equipo_filter = request.GET.get('equipo', '')
            zona_inicio_filter = request.GET.get('zona_inicio', '')
            zona_fin_filter = request.GET.get('zona_fin', '')
            inicia_filter = request.GET.get('inicia', '')
            jugada_filter = request.GET.get('jugada', '')  # reemplaza a situacion en UI

            if evento_filter:
                plays_list = plays_list.filter(evento=evento_filter)
            if equipo_filter:
                plays_list = plays_list.filter(equipo=equipo_filter)
            if zona_inicio_filter:
                plays_list = plays_list.filter(zona_inicio=zona_inicio_filter)
            if zona_fin_filter:
                plays_list = plays_list.filter(zona_fin=zona_fin_filter)
            if inicia_filter:
                plays_list = plays_list.filter(inicia=inicia_filter)
            if jugada_filter:
                plays_list = plays_list.filter(jugada=jugada_filter)

            # Si vienen ids seleccionados, filtramos por ellos y cambiamos el nombre del archivo
            ids_param = request.GET.get('ids')
            if ids_param:
                try:
                    ids = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
                except Exception:
                    ids = []
                if ids:
                    plays_list = plays_list.filter(pk__in=ids)
                    filename_base = f"{match.home_team} vs {match.away_team}_jugadas_destacadas"
                else:
                    filename_base = f"plays_match_{match.pk}"
            else:
                filename_base = f"plays_match_{match.pk}"

            # Sanitizar nombre de archivo
            safe_name = re.sub(r'[^A-Za-z0-9_\-]+', '_', filename_base)

            # Preparar CSV
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{safe_name}.csv"'
            writer = csv.writer(response)
            writer.writerow(EXPORT_HEADERS_ORDER)
            for p in plays_list:
                writer.writerow([
                    p.jugada, p.arbitro, p.canal_de_inicio, p.evento, p.equipo, p.fin, p.ficha, p.inicia, p.inicio,
                    p.marcador_final, p.termina, p.tiempo, p.torneo, p.zona_fin, p.zona_inicio, p.resultado, p.jugadores,
                    p.sigue_con, p.pos_tiro, p.set, p.tiro, p.tipo, p.accion, p.termina_en, p.sancion, p.situacion, p.transicion,
                    getattr(p, 'situacion_penal', ''), getattr(p, 'nueva_categoria', ''), getattr(p, 'acercar', ''), getattr(p, 'alejar', ''),
                    p.desde, p.canal, p.fases, p.opcion, p.zona
                ])
            return response
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.get_object()
        
        plays_list = match.plays.select_related('match').all().order_by('inicio')
        context['plays_total'] = match.plays.count()

        # Determinar si mostrar acceso a estadísticas y con qué equipo enfocar
        user = self.request.user
        profile = getattr(user, 'profile', None)
        allowed_roles = {'COACH', 'PLAYER'}
        show_stats_button = False
        stats_team = None

        if user.is_authenticated and profile and profile.role in allowed_roles:
            team_names = []
            if profile.team:
                name = (profile.team.alias or profile.team.name or '').strip()
                if name:
                    team_names.append(name)

            participations = CoachTournamentTeamParticipation.objects.filter(user=user, active=True).select_related('team')
            for p in participations:
                name = (p.team.alias or p.team.name or '').strip()
                if name:
                    team_names.append(name)

            match_teams = { (match.home_team or '').strip().lower(), (match.away_team or '').strip().lower() }
            for name in team_names:
                if name and name.strip().lower() in match_teams:
                    stats_team = name.strip()
                    break

            show_stats_button = stats_team is not None

        context['show_stats_button'] = show_stats_button
        context['stats_team'] = stats_team

        filter_params = {}
        evento_filter = self.request.GET.get('evento', '')
        equipo_filter = self.request.GET.get('equipo', '')
        zona_inicio_filter = self.request.GET.get('zona_inicio', '')
        zona_fin_filter = self.request.GET.get('zona_fin', '')
        inicia_filter = self.request.GET.get('inicia', '')
        jugada_filter = self.request.GET.get('jugada', '')

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
        if jugada_filter:
            plays_list = plays_list.filter(jugada=jugada_filter)
            filter_params['jugada'] = jugada_filter
        
        paginator = Paginator(plays_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['page_obj'] = page_obj
        context['filter_params'] = filter_params
        
        # Opciones únicas normalizadas (sin duplicados por mayúsculas/espacios)
        def unique_options(qs, field):
            values_qs = qs.exclude(**{f"{field}__isnull": True}).exclude(**{field: ''}) \
                          .values_list(field, flat=True).order_by(field).distinct()
            seen = set()
            opts = []
            for v in values_qs:
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

        base_plays = match.plays.only('equipo', 'jugada', 'zona_inicio', 'zona_fin', 'inicia', 'evento')
        context['equipo_options'] = unique_options(base_plays, 'equipo')
        context['jugada_options'] = unique_options(base_plays, 'jugada')
        context['zona_inicio_options'] = unique_options(base_plays, 'zona_inicio')
        context['zona_fin_options'] = unique_options(base_plays, 'zona_fin')
        context['inicia_options'] = unique_options(base_plays, 'inicia')
        context['evento_options'] = unique_options(base_plays, 'evento')

        return context
    
class MatchUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Match
    form_class = MatchUpdateForm
    template_name = 'player/match_update_form.html'
    
    def test_func(self):
        return self.request.user.is_staff
        
    def get_success_url(self):
        messages.success(self.request, "Partido actualizado exitosamente.")
        return reverse_lazy('player:match_list')

class MatchListView(LoginRequiredMixin, ListView):
    # Listado de partidos con visibilidad condicional y múltiples filtros.
    model = Match
    template_name = 'player/match_list.html'
    context_object_name = 'matches'
    paginate_by = 20
    login_url = reverse_lazy('player:login')
    redirect_field_name = 'next'

    def _normalize_team_name(self, value):
        return (value or '').strip().upper()

    def _get_team_variants(self, team=None, team_name=None):
        variants = set()

        if team is not None:
            for raw_value in (team.name, team.alias):
                normalized = self._normalize_team_name(raw_value)
                if normalized:
                    variants.add(normalized)

        normalized_name = self._normalize_team_name(team_name)
        if normalized_name:
            variants.add(normalized_name)

        if team is None and normalized_name:
            matched_team = Team.objects.filter(
                Q(name__iexact=team_name) | Q(alias__iexact=team_name)
            ).only('name', 'alias').first()
            if matched_team:
                variants.update(self._get_team_variants(team=matched_team))

        return variants

    def _build_match_team_query(self, team_names):
        query = Q()
        for name in team_names:
            query |= Q(home_team__iexact=name) | Q(away_team__iexact=name)
        return query

    def get_queryset(self):
        user = self.request.user
        queryset = Match.objects.all().select_related('tournament', 'tournament__country')

        if user.is_authenticated and not user.is_staff:
            participations = CoachTournamentTeamParticipation.objects.filter(user=user, active=True).select_related('team')
            filter_type = self.request.GET.get('filter', 'own')
            profile_team = getattr(getattr(user, 'profile', None), 'team', None)
            profile_team_variants = self._get_team_variants(team=profile_team) if profile_team else set()
            if participations.exists():
                user_team_names = set()
                seasons = set()
                for p in participations:
                    if p.season:
                        seasons.add(p.season.strip())
                    user_team_names.update(self._get_team_variants(team=p.team))

                user_team_names.update(profile_team_variants)
                team_query = self._build_match_team_query(user_team_names)
                season_q = Q()
                for s in seasons:
                    season_q |= Q(tournament__season__iexact=s)

                if filter_type == 'rivals':
                    if season_q:
                        season_limited_rivals = queryset.filter(season_q).exclude(team_query)
                        if season_limited_rivals.exists():
                            queryset = season_limited_rivals
                        else:
                            queryset = queryset.exclude(team_query)
                    else:
                        queryset = queryset.exclude(team_query)
                else:  # 'own' por defecto
                    visibility_q = Q()
                    for p in participations:
                        team_variants = self._get_team_variants(team=p.team)
                        if team_variants:
                            visibility_q |= (
                                self._build_match_team_query(team_variants)
                                & Q(tournament__season__iexact=p.season)
                            )

                    if profile_team_variants:
                        visibility_q |= self._build_match_team_query(profile_team_variants)

                    season_limited_own = queryset.filter(visibility_q) if visibility_q else queryset.none()
                    if visibility_q and season_limited_own.exists():
                        queryset = season_limited_own
                    elif team_query:
                        queryset = queryset.filter(team_query)
            else:
                if profile_team:
                    team_variants = profile_team_variants
                    team_query = self._build_match_team_query(team_variants)
                    if filter_type == 'rivals':
                        team_tournaments = Match.objects.filter(team_query).values_list('tournament_id', flat=True).distinct()
                        if team_tournaments.exists():
                            queryset = queryset.filter(tournament_id__in=team_tournaments).exclude(team_query)
                        else:
                            queryset = queryset.exclude(team_query)
                    else:
                        queryset = queryset.filter(team_query)

        tournament_id = self.request.GET.get('tournament')
        if tournament_id and str(tournament_id).isdigit():
            queryset = queryset.filter(tournament__id=int(tournament_id))

        division_code = self.request.GET.get('division')
        if division_code:
            queryset = queryset.filter(division=division_code)

        country_id = self.request.GET.get('country')
        if country_id:
            try:
                queryset = queryset.filter(tournament__country_id=int(country_id))
            except (TypeError, ValueError):
                pass

        season = (self.request.GET.get('season') or '').strip()
        if season:
            queryset = queryset.filter(tournament__season__iexact=season)

        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(Q(home_team__icontains=q) | Q(away_team__icontains=q))

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
            queryset = queryset.filter(match_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(match_date__lte=date_to)

        result_sq = Play.objects.filter(match=OuterRef('pk')).exclude(marcador_final='').values('marcador_final')[:1]
        queryset = queryset.annotate(match_result=Subquery(result_sq))

        has_plays_exists = Play.objects.filter(match=OuterRef('pk'))
        queryset = queryset.annotate(has_plays=Exists(has_plays_exists))

        sort_by = self.request.GET.get('sort', '-match_date')
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
        context['current_sort'] = self.request.GET.get('sort', '-match_date')
        context['current_tournament'] = self.request.GET.get('tournament', '')
        context['current_division'] = self.request.GET.get('division', '')
        context['current_country'] = self.request.GET.get('country', '')
        context['current_season'] = self.request.GET.get('season', '')
        context['current_q'] = self.request.GET.get('q', '')
        context['current_date_from'] = self.request.GET.get('date_from', '')
        context['current_date_to'] = self.request.GET.get('date_to', '')
        qs = self.request.GET.copy()
        qs.pop('page', None)
        context['querystring'] = qs.urlencode()

        context['tournament_options'] = Tournament.objects.select_related('country').order_by('country__name', 'name', 'season')
        context['division_options'] = Match.Division.choices
        context['country_options'] = Country.objects.order_by('name')
        context['season_options'] = (
            Tournament.objects.exclude(season='').values_list('season', flat=True).order_by('season').distinct()
        )
        user = self.request.user
        has_filters = any([
            bool(context['current_q'].strip()),
            bool(context['current_date_from'].strip()),
            bool(context['current_date_to'].strip()),
            bool(context['current_tournament']),
            bool(context['current_division']),
            bool(context['current_country']),
            bool(context['current_season']),
            (not user.is_staff and context['current_filter'] != 'own')
        ])
        context['has_filters'] = has_filters
        return context
    
class MatchPlaysDataView(LoginRequiredMixin, View):
    # Endpoint JSON para DataTables con filtros, búsqueda, orden y paginación.
    def get(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        base_qs = Play.objects.filter(match=match).select_related('match')
        plays = base_qs

        # Aplicar filtros (situacion -> jugada)
        filters = {
            'equipo': request.GET.get('equipo'),
            'jugada': request.GET.get('jugada'),
            'zona_inicio': request.GET.get('zona_inicio'),
            'zona_fin': request.GET.get('zona_fin'),
        }
        for field, value in filters.items():
            if value:
                plays = plays.filter(**{field: value})

        # Búsqueda global (DataTables search[value])
        search_value = request.GET.get('search[value]') or request.GET.get('search')
        if search_value:
            sv = search_value.strip()
            if sv:
                plays = plays.filter(
                    Q(jugada__icontains=sv)
                    | Q(evento__icontains=sv)
                    | Q(equipo__icontains=sv)
                    | Q(zona_inicio__icontains=sv)
                    | Q(zona_fin__icontains=sv)
                    | Q(resultado__icontains=sv)
                    | Q(sancion__icontains=sv)
                )

        # Ordenar según DataTables columnas visibles en el front
        # Columnas front (índices): 0 checkbox, 1 Jugada, 2 Canal Inicio, 3 Equipo, 4 Fin, 5 Inicia,
        # 6 Inicio, 7 Termina, 8 Tiempo, 9 Zona Fin, 10 Zona Inicio, 11 Resultado, 12 Sigue Con,
        # 13 Pos Tiro, 14 Set, 15 Tiro, 16 Tipo, 17 Accion, 18 Termina En, 19 Sancion, 20 Situacion,
        # 21 Transicion, 22 Situacion Penal, 23 Desde, 24 Canal, 25 Fases, 26 Opcion, 27 Zona
        order_column_map = {
            1: 'jugada',
            2: 'canal_de_inicio',
            3: 'equipo',
            4: 'fin',
            5: 'inicia',
            6: 'inicio',
            7: 'termina',
            8: 'tiempo',
            9: 'zona_fin',
            10: 'zona_inicio',
            11: 'resultado',
            12: 'sigue_con',
            13: 'pos_tiro',
            14: 'set',
            15: 'tiro',
            16: 'tipo',
            17: 'accion',
            18: 'termina_en',
            19: 'sancion',
            20: 'situacion',
            21: 'transicion',
            22: 'situacion_penal',
            23: 'desde',
            24: 'canal',
            25: 'fases',
            26: 'opcion',
            27: 'zona',
        }
        try:
            order_col_index = int(request.GET.get('order[0][column]', 6))
        except (TypeError, ValueError):
            order_col_index = 6
        order_dir = request.GET.get('order[0][dir]', 'asc')
        order_field = order_column_map.get(order_col_index, 'fin')
        if order_dir == 'desc':
            order_field = f'-{order_field}'
        plays = plays.order_by(order_field)

        # Paginación
        start = int(request.GET.get('start', 0))
        length = int(request.GET.get('length', 10))
        plays_page = plays[start:start + length]

        # Construir respuesta JSON con columnas visibles/permisibles
        data = [
            [
                play.id,
                play.jugada,
                play.canal_de_inicio,
                play.equipo,
                play.fin,
                play.inicia,
                play.inicio,
                play.termina,
                play.tiempo,
                play.zona_fin,
                play.zona_inicio,
                play.resultado,
                play.sigue_con,
                play.pos_tiro,
                play.set,
                play.tiro,
                play.tipo,
                play.accion,
                play.termina_en,
                play.sancion,
                play.situacion,
                play.transicion,
                getattr(play, 'situacion_penal', ''),
                play.desde,
                play.canal,
                play.fases,
                play.opcion,
                play.zona,
            ]
            for play in plays_page
        ]

        # Totales para DataTables
        try:
            draw = int(request.GET.get('draw', 0))
        except (TypeError, ValueError):
            draw = 0
        records_total = base_qs.count()
        records_filtered = plays.count()

        response = {
            'draw': draw,
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'data': data,
        }
        return JsonResponse(response)

# --- Nueva vista: subir/actualizar CSV desde el reproductor ---
class MatchCSVUploadView(LoginRequiredMixin, UserPassesTestMixin, View):
    # Actualiza jugadas de un partido desde el reproductor, reemplazando las anteriores.
    login_url = reverse_lazy('player:login')
    redirect_field_name = 'next'
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        uploaded = request.FILES.get('csv_file')
        if not uploaded:
            messages.error(request, 'Debes seleccionar un archivo CSV.')
            return redirect('player:play_match', pk=pk)
        try:
            text = read_uploaded_csv_text(uploaded)
            reader = make_dict_reader_from_text(text)
            ok, msg, header_map = validate_headers_flexible(reader.fieldnames)
            if not ok:
                messages.error(request, msg)
                return redirect('player:play_match', pk=pk)

            plays_to_create = []
            count = 0
            for row in reader:
                plays_to_create.append(Play(
                    match=match,
                    jugada=(row.get(header_map['JUGADA']) or '').strip(),
                    arbitro=(row.get(header_map['ARBITRO']) or '').strip(),
                    canal_de_inicio=(row.get(header_map['CANAL DE INICIO']) or '').strip(),
                    desde=(row.get(header_map['DESDE']) or '').strip(),
                    canal=(row.get(header_map['CANAL']) or '').strip(),
                    fases=(row.get(header_map['FASES']) or '').strip(),
                    opcion=(row.get(header_map['OPCION']) or '').strip(),
                    zona=(row.get(header_map['ZONA']) or '').strip(),
                    evento=(row.get(header_map['EVENTO']) or '').strip(),
                    equipo=(row.get(header_map['EQUIPO']) or '').strip(),
                    fin=parse_time_to_seconds(row.get(header_map['FIN']) or ''),
                    ficha=(row.get(header_map['FICHA']) or '').strip(),
                    inicia=(row.get(header_map['INICIA']) or '').strip(),
                    inicio=parse_time_to_seconds(row.get(header_map['INICIO']) or ''),
                    marcador_final=(row.get(header_map['MARCADOR FINAL']) or '').strip(),
                    termina=(row.get(header_map['TERMINA']) or '').strip(),
                    tiempo=(row.get(header_map['TIEMPO']) or '').strip(),
                    torneo=(row.get(header_map['TORNEO']) or '').strip(),
                    zona_fin=(row.get(header_map['ZONA FIN']) or '').strip(),
                    zona_inicio=(row.get(header_map['ZONA INICIO']) or '').strip(),
                    resultado=(row.get(header_map['RESULTADO']) or '').strip(),
                    jugadores=(row.get(header_map['JUGADORES']) or '').strip(),
                    sigue_con=(row.get(header_map['SIGUE CON']) or '').strip(),
                    pos_tiro=(row.get(header_map['POS TIRO']) or '').strip(),
                    set=(row.get(header_map['SET']) or '').strip(),
                    tiro=(row.get(header_map['TIRO']) or '').strip(),
                    tipo=(row.get(header_map['TIPO']) or '').strip(),
                    accion=(row.get(header_map['ACCION']) or '').strip(),
                    termina_en=(row.get(header_map.get('TERMINA EN','')) or '').strip(),
                    sancion=(row.get(header_map['SANCION']) or '').strip(),
                    situacion=(row.get(header_map.get('SITUACION','')) or '').strip(),
                    transicion=(row.get(header_map['TRANSICION']) or '').strip(),
                    situacion_penal=(row.get(header_map.get('SITUACION PENAL','')) or '').strip(),
                    nueva_categoria=(row.get(header_map.get('NUEVA CATEGORIA','')) or '').strip(),
                    acercar=(row.get(header_map.get('ACERCAR','')) or '').strip(),
                    alejar=(row.get(header_map.get('ALEJAR','')) or '').strip(),
                ))
                count += 1

            with transaction.atomic():
                match.plays.all().delete()  # Reemplazar jugadas existentes
                if plays_to_create:
                    Play.objects.bulk_create(plays_to_create, batch_size=1000)
                    # Extraer marcador final del último play para actualizar el resultado
                    last_marcador = next(
                        (p.marcador_final for p in reversed(plays_to_create) if p.marcador_final),
                        None
                    )
                    home, away = _parse_score_from_marcador(last_marcador)
                    if home is not None:
                        match.home_score = home
                        match.away_score = away
                        match.save(update_fields=['home_score', 'away_score'])
            if count:
                messages.success(request, f"Se actualizaron {count} jugadas para el partido.")
            else:
                messages.warning(request, 'El CSV no contenía jugadas válidas.')
        except Exception as e:
            messages.error(request, f"Error al procesar el archivo CSV: {e}")
        return redirect('player:play_match', pk=pk)

class MatchSelectionPresetListCreateView(LoginRequiredMixin, View):
    # Listar/crear presets de selección de jugadas asociados a un usuario y partido.
    def get(self, request, pk):
        # lista presets del usuario para el partido
        presets = SelectionPreset.objects.filter(user=request.user, match_id=pk)\
                    .values('id', 'name', 'created_at', 'updated_at')
        return JsonResponse({'presets': list(presets)})

    def post(self, request, pk):
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            return HttpResponseBadRequest('JSON inválido')

        name = (data.get('name') or '').strip()
        play_ids = data.get('play_ids') or []

        if not name:
            return HttpResponseBadRequest('El nombre es requerido')
        if not isinstance(play_ids, list) or any(not isinstance(x, int) for x in play_ids):
            return HttpResponseBadRequest('play_ids debe ser una lista de enteros')

        # validar que las jugadas pertenezcan al partido
        valid_ids = set(Play.objects.filter(match_id=pk, id__in=play_ids).values_list('id', flat=True))
        if len(valid_ids) != len(set(play_ids)):
            return HttpResponseBadRequest('Algunas jugadas no pertenecen al partido')

        preset, created = SelectionPreset.objects.get_or_create(
            user=request.user, match_id=pk, name=name,
            defaults={'play_ids': list(valid_ids)}
        )
        if not created:
            preset.play_ids = list(valid_ids)
            preset.save(update_fields=['play_ids', 'updated_at'])

        return JsonResponse({'id': preset.id, 'name': preset.name, 'updated_at': preset.updated_at})

class MatchSelectionPresetDetailView(LoginRequiredMixin, View):
    # Detalle/eliminación de un preset. Sólo propietario o staff tienen acceso.
    def get(self, request, pk, preset_id):
        preset = get_object_or_404(SelectionPreset, id=preset_id, match_id=pk)
        if preset.user_id != request.user.id and not request.user.is_staff:
            return HttpResponseForbidden('Sin permisos')
        return JsonResponse({'id': preset.id, 'name': preset.name, 'play_ids': preset.play_ids})

    def delete(self, request, pk, preset_id):
        preset = get_object_or_404(SelectionPreset, id=preset_id, match_id=pk)
        if preset.user_id != request.user.id and not request.user.is_staff:
            return HttpResponseForbidden('Sin permisos')
        preset.delete()
        return JsonResponse({'deleted': True})


class MatchSelectionPresetUploadCSVView(LoginRequiredMixin, View):
    """Crea un preset a partir de un CSV exportado.

    Acepta:
      - Columna ID/Play_Id para usar los IDs directos de jugadas.
      - O CSV exportado estándar: intenta emparejar por INICIO+FIN (+JUGADA/EQUIPO si vienen).
    """

    def post(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        file: Optional[UploadedFile] = request.FILES.get('csv_preset_file')
        name = (request.POST.get('csv_preset_name') or '').strip()

        if not file:
            messages.error(request, 'Debes seleccionar un CSV para importar el preset.')
            return redirect('player:play_match', pk=pk)

        try:
            text = read_uploaded_csv_text(file)
            reader = make_dict_reader_from_text(text)
            # Validamos cabeceras estándar, pero permitimos columna ID opcional
            ok, msg, header_map = validate_headers_flexible(reader.fieldnames)
            if not ok:
                messages.error(request, msg)
                return redirect('player:play_match', pk=pk)

            fieldnames_lower = { (fn or '').strip().lower(): (fn or '').strip() for fn in (reader.fieldnames or []) }
            id_col = None
            for candidate in ('id', 'play_id', 'playid'):
                if candidate in fieldnames_lower:
                    id_col = fieldnames_lower[candidate]
                    break

            play_ids = []
            rows_ci = []
            for row in reader:
                row_ci = { (k or '').strip().lower(): (v or '').strip() for k, v in row.items() if k }
                rows_ci.append(row_ci)

            if id_col:
                for row_ci in rows_ci:
                    raw = row_ci.get(id_col.lower())
                    if raw and str(raw).strip().isdigit():
                        play_ids.append(int(str(raw).strip()))
            else:
                # Emparejar por tiempos y jugada/equipo
                for row_ci in rows_ci:
                    inicio = parse_time_to_seconds(row_ci.get('inicio', ''))
                    fin = parse_time_to_seconds(row_ci.get('fin', ''))
                    jugada = row_ci.get('jugada', '')
                    equipo = row_ci.get('equipo', '')

                    qs = Play.objects.filter(match=match)
                    if inicio is not None:
                        qs = qs.filter(inicio=inicio)
                    if fin is not None:
                        qs = qs.filter(fin=fin)
                    if jugada:
                        qs = qs.filter(jugada=jugada)
                    if equipo:
                        qs = qs.filter(equipo=equipo)
                    pid = qs.values_list('id', flat=True).first()
                    if pid is None and jugada:
                        pid = Play.objects.filter(match=match, jugada=jugada, inicio=inicio).values_list('id', flat=True).first()
                    if pid is not None:
                        play_ids.append(int(pid))

            if not play_ids:
                messages.warning(request, 'No se pudieron asociar jugadas del CSV con este partido.')
                return redirect('player:play_match', pk=pk)

            # Validar pertenencia al partido y conservar orden/dedupe
            valid_ids = []
            seen = set()
            allowed = set(Play.objects.filter(match=match, id__in=play_ids).values_list('id', flat=True))
            for pid in play_ids:
                if pid in allowed and pid not in seen:
                    seen.add(pid)
                    valid_ids.append(pid)

            if not valid_ids:
                messages.warning(request, 'Las jugadas del CSV no pertenecen a este partido.')
                return redirect('player:play_match', pk=pk)

            if not name:
                base = (file.name or 'preset').rsplit('.', 1)[0]
                name = base[:100] or 'Preset CSV'

            preset, created = SelectionPreset.objects.get_or_create(
                user=request.user, match=match, name=name,
                defaults={'play_ids': valid_ids}
            )
            if not created:
                preset.play_ids = valid_ids
                preset.save(update_fields=['play_ids', 'updated_at'])

            messages.success(request, f"Preset '{preset.name}' importado con {len(valid_ids)} jugadas.")
            return redirect('player:play_match', pk=pk)

        except Exception as e:
            messages.error(request, f'No se pudo importar el preset: {e}')
            return redirect('player:play_match', pk=pk)