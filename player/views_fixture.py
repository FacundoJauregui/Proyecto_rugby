# player/views_fixture.py
"""Vistas para el módulo de Fixture / Calendario de partidos agendados."""

from datetime import datetime, date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.edit import CreateView, UpdateView

from .forms import FixtureMatchForm, FixtureExcelImportForm
from .models import Match, Tournament


class IsAdminMixin(UserPassesTestMixin):
    """Solo superusuarios o staff pueden administrar el fixture."""
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


# ─────────────────────────────────────────────
# Vista principal del calendario (todos los usuarios autenticados)
# ─────────────────────────────────────────────
class FixtureCalendarView(LoginRequiredMixin, TemplateView):
    template_name = 'player/fixture.html'
    login_url = reverse_lazy('player:login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_admin'] = self.request.user.is_staff or self.request.user.is_superuser
        ctx['form_excel'] = FixtureExcelImportForm()
        return ctx


# ─────────────────────────────────────────────
# API JSON para FullCalendar
# ─────────────────────────────────────────────
class FixtureEventsAPIView(LoginRequiredMixin, View):
    """Devuelve los partidos en formato JSON para FullCalendar."""
    login_url = reverse_lazy('player:login')

    def get(self, request):
        qs = Match.objects.select_related('tournament').all()

        # Filtro opcional por rango que FullCalendar envía
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        if start_str:
            try:
                start = datetime.fromisoformat(start_str[:10])
                qs = qs.filter(match_date__gte=start.date())
            except ValueError:
                pass
        if end_str:
            try:
                end = datetime.fromisoformat(end_str[:10])
                qs = qs.filter(match_date__lte=end.date())
            except ValueError:
                pass

        events = []
        today = date.today()
        for m in qs:
            # Solo incluir partidos con fecha asignada
            if not m.match_date:
                continue

            # Jugado = tiene resultado cargado O la fecha ya pasó (incluyendo hoy)
            played = (
                (m.home_score is not None and m.away_score is not None)
                or m.match_date <= today
            )

            if played:
                color = '#1e40af'          # azul oscuro → jugado
                result_str = (
                    f" ({m.home_score} - {m.away_score})"
                    if m.home_score is not None and m.away_score is not None
                    else ""
                )
            else:
                color = '#15803d'          # verde → pendiente
                result_str = ""

            start_dt = m.match_date.isoformat()
            if m.match_time:
                start_dt = f"{m.match_date.isoformat()}T{m.match_time.strftime('%H:%M:%S')}"

            title = f"{m.home_team} vs {m.away_team}{result_str}"
            events.append({
                'id': m.pk,
                'title': title,
                'start': start_dt,
                'color': color,
                'extendedProps': {
                    'home_team': m.home_team,
                    'away_team': m.away_team,
                    'tournament': str(m.tournament) if m.tournament else '',
                    'is_played': played,
                    'home_score': m.home_score,
                    'away_score': m.away_score,
                    'notes': m.match_notes,
                    'time': m.match_time.strftime('%H:%M') if m.match_time else '',
                    'has_video': bool(m.video_id),
                }
            })

        return JsonResponse(events, safe=False)


# ─────────────────────────────────────────────
# CRUD — solo admin
# ─────────────────────────────────────────────
class MatchFixtureCreateView(LoginRequiredMixin, IsAdminMixin, CreateView):
    model = Match
    form_class = FixtureMatchForm
    template_name = 'player/fixture_form.html'
    success_url = reverse_lazy('player:fixture')
    login_url = reverse_lazy('player:login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Agregar Partido al Fixture'
        ctx['action'] = 'Agregar'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Partido agregado al fixture.")
        return super().form_valid(form)


class MatchFixtureUpdateView(LoginRequiredMixin, IsAdminMixin, UpdateView):
    model = Match
    form_class = FixtureMatchForm
    template_name = 'player/fixture_form.html'
    success_url = reverse_lazy('player:fixture')
    login_url = reverse_lazy('player:login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Partido'
        ctx['action'] = 'Guardar Cambios'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Partido actualizado correctamente.")
        return super().form_valid(form)


class MatchFixtureDeleteView(LoginRequiredMixin, IsAdminMixin, View):
    login_url = reverse_lazy('player:login')

    def post(self, request, pk):
        obj = get_object_or_404(Match, pk=pk)
        obj.delete()
        messages.success(request, "Partido eliminado del fixture.")
        return redirect('player:fixture')


# ─────────────────────────────────────────────
# Importar desde Excel
# ─────────────────────────────────────────────
class FixtureExcelImportView(LoginRequiredMixin, IsAdminMixin, View):
    login_url = reverse_lazy('player:login')

    def post(self, request):
        import openpyxl
        form = FixtureExcelImportForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Archivo inválido.")
            return redirect('player:fixture')

        archivo = form.cleaned_data['archivo_excel']
        try:
            wb = openpyxl.load_workbook(archivo, data_only=True)
            hoja = wb.active
        except Exception as e:
            messages.error(request, f"Error abriendo el Excel: {e}")
            return redirect('player:fixture')

        # Leer encabezados de la primera fila (normalizados)
        headers = []
        for cell in hoja[1]:
            val = cell.value
            headers.append(str(val).strip().upper() if val is not None else '')

        def col(name):
            try:
                return headers.index(name)
            except ValueError:
                return None

        i_fecha    = col('FECHA')
        i_hora     = col('HORA')
        i_local    = col('LOCAL')
        i_visit    = col('VISITANTE')
        i_torneo   = col('TORNEO')
        i_g_local  = col('GOLES LOCAL')
        i_g_visit  = col('GOLES VISITANTE')
        i_notas    = col('NOTAS')
        i_division = col('DIVISION')

        if i_fecha is None or i_local is None or i_visit is None:
            messages.error(request, "El Excel debe tener columnas: FECHA, LOCAL, VISITANTE.")
            return redirect('player:fixture')

        created, updated_count, errors = 0, 0, []
        for row_num, row in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
            def get(idx):
                if idx is None:
                    return None
                try:
                    return row[idx]
                except IndexError:
                    return None

            raw_fecha = get(i_fecha)
            raw_local = get(i_local)
            raw_visit = get(i_visit)

            if not raw_fecha or not raw_local or not raw_visit:
                continue

            # Parsear fecha
            fecha = None
            if hasattr(raw_fecha, 'date'):
                fecha = raw_fecha.date()
            elif isinstance(raw_fecha, str):
                for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        fecha = datetime.strptime(raw_fecha.strip(), fmt).date()
                        break
                    except ValueError:
                        pass
            if fecha is None:
                errors.append(f"Fila {row_num}: fecha inválida '{raw_fecha}'.")
                continue

            # Parsear hora
            hora = None
            raw_hora = get(i_hora)
            if raw_hora:
                if hasattr(raw_hora, 'hour'):
                    hora = raw_hora.replace(tzinfo=None) if hasattr(raw_hora, 'tzinfo') else raw_hora
                    if hasattr(hora, 'date'):
                        hora = hora.time()
                elif isinstance(raw_hora, str):
                    for fmt in ('%H:%M', '%H:%M:%S'):
                        try:
                            hora = datetime.strptime(raw_hora.strip(), fmt).time()
                            break
                        except ValueError:
                            pass

            # Torneo
            torneo_obj = None
            raw_torneo = get(i_torneo)
            if raw_torneo:
                t = str(raw_torneo).strip()
                year_str = str(fecha.year) if fecha else None

                def _find_torneo(qs_filter):
                    """Dado un queryset filter kwargs, busca primero por año de temporada y
                    si no encuentra devuelve el primero disponible."""
                    qs = Tournament.objects.filter(**qs_filter)
                    if not qs.exists():
                        return None
                    if year_str:
                        by_season = qs.filter(season__icontains=year_str).first()
                        if by_season:
                            return by_season
                    return qs.first()

                # Primero buscar por siglas exactas, luego nombre exacto, luego parciales
                torneo_obj = (
                    _find_torneo({'short_name__iexact': t})
                    or _find_torneo({'name__iexact': t})
                    or _find_torneo({'short_name__icontains': t})
                    or _find_torneo({'name__icontains': t})
                )

            # División
            division_val = None
            raw_div = get(i_division)
            if raw_div:
                div_upper = str(raw_div).strip().upper()
                for choice_val, _ in Match.Division.choices:
                    if choice_val == div_upper:
                        division_val = choice_val
                        break

            def to_int(v):
                try:
                    return int(v) if v is not None else None
                except (ValueError, TypeError):
                    return None

            home_name = str(raw_local).strip().upper()
            away_name = str(raw_visit).strip().upper()

            _, was_created = Match.objects.update_or_create(
                home_team=home_name,
                away_team=away_name,
                match_date=fecha,
                defaults={
                    'match_time': hora,
                    'tournament': torneo_obj,
                    'division': division_val,
                    'home_score': to_int(get(i_g_local)),
                    'away_score': to_int(get(i_g_visit)),
                    'match_notes': str(get(i_notas) or '').strip(),
                }
            )
            if was_created:
                created += 1
            else:
                updated_count += 1

        parts = []
        if created:
            parts.append(f"{created} creados")
        if updated_count:
            parts.append(f"{updated_count} actualizados")
        summary = ", ".join(parts) or "0 partidos procesados"
        if errors:
            messages.warning(request, f"{summary} con {len(errors)} errores: " + " | ".join(errors[:5]))
        else:
            messages.success(request, f"Importación completada: {summary}.")

        return redirect('player:fixture')

