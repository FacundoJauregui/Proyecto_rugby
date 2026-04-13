from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Profile
from .forms import AdminUserCreationForm

class AdminUserCreateView(UserPassesTestMixin, CreateView):
    model = User
    form_class = AdminUserCreationForm
    template_name = 'player/admin_user_form.html'
    success_url = reverse_lazy('player:admin_user_add')

    def test_func(self):
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, f"Usuario '{form.cleaned_data['username']}' creado con éxito.")
        return super().form_valid(form)
from .forms import CoachPlayerCreationForm

class CoachPlayerCreateView(UserPassesTestMixin, CreateView):
    model = User
    form_class = CoachPlayerCreationForm
    template_name = 'player/coach_player_form.html'
    success_url = reverse_lazy('player:coach_player_add')

    def test_func(self):
        return hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'COACH'

    def form_valid(self, form):
        from django.http import HttpResponseRedirect
        
        coach_profile = getattr(self.request.user, 'profile', None)
        coach_team = coach_profile.team if coach_profile else None
        
        # El formulario ya trae la logica para asignar el equipo al jugador en el def save()
        self.object = form.save(commit=True, coach_team=coach_team)

        messages.success(self.request, f"Jugador '{self.object.username}' asociado a tu equipo con éxito.")
        return HttpResponseRedirect(self.get_success_url())

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.urls import reverse
from django.views.generic import FormView
from .models import Invitation
from .forms import InvitationForm, PlayerRegistrationForm

class CreateInvitationView(UserPassesTestMixin, CreateView):
    """Vista para que un Entrenador genere un link de invitación para su equipo."""
    model = Invitation
    form_class = InvitationForm
    template_name = 'player/create_invitation.html'
    
    def get_success_url(self):
        return reverse('player:coach_player_add')

    def test_func(self):
        # Entrenadores con equipo O Administradores
        is_coach = hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'COACH' and getattr(self.request.user.profile, 'team', None) is not None
        return self.request.user.is_superuser or is_coach

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        from django.http import HttpResponseRedirect
        from django.core.mail import send_mail
        from django.conf import settings
        import openpyxl
        
        # 1. Determinar el equipo
        if self.request.user.is_superuser:
            target_team = form.cleaned_data['team']
        else:
            target_team = self.request.user.profile.team

        emails_a_invitar = []
        
        # 2. Si hay email manual, lo agregamos
        if form.cleaned_data.get('email'):
            emails_a_invitar.append(form.cleaned_data['email'])
            
        # 3. Si hay archivo Excel, extraemos todos los mails de la columna A
        archivo_excel = form.cleaned_data.get('archivo_excel')
        if archivo_excel:
            try:
                wb = openpyxl.load_workbook(archivo_excel, data_only=True)
                hoja = wb.active
                # Recorrer filas de la columna A (usando valores limpios)
                for row in hoja.iter_rows(min_col=1, max_col=1, values_only=True):
                    celda_email = row[0]
                    if celda_email and isinstance(celda_email, str) and '@' in celda_email:
                        emails_a_invitar.append(celda_email.strip().lower())
            except Exception as e:
                messages.error(self.request, f"Ocurrió un error leyendo el Excel: {e}")
                return self.form_invalid(form)

        # 4. Limpiar duplicados y validar
        emails_a_invitar = list(set(emails_a_invitar))
        if not emails_a_invitar:
            messages.error(self.request, "No se encontró ningún correo válido.")
            return self.form_invalid(form)
            
        # 5. Procesar e iterar por la lista de emails
        invitaciones_creadas = 0
        remitente = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@sportframe.com')
        
        for email_dest in emails_a_invitar:
            # Crear o actualizar invitación
            invitation = Invitation.objects.create(
                email=email_dest,
                team=target_team,
                created_by=self.request.user
            )
            
            # Generar el link para compartir
            invite_link = self.request.build_absolute_uri(
                reverse('player:player_register', kwargs={'token': invitation.token})
            )
            
            # Enviar el email real
            asunto = f"Invitación para unirte al equipo {target_team.name}"
            mensaje = f"Hola!\n\nEl entrenador {self.request.user.first_name} {self.request.user.last_name} te ha invitado a unirte a su equipo \"{target_team.name}\" en LaDinastia.\n\nPor favor, haz clic en el siguiente enlace para crear tu cuenta y acceder a los contenidos de tu equipo:\n{invite_link}\n\n¡Te esperamos!"

            try:
                send_mail(asunto, mensaje, remitente, [email_dest], fail_silently=False)
                invitaciones_creadas += 1
            except Exception as e:
                messages.warning(self.request, f"No se pudo enviar el correo a {email_dest}.")
        
        if invitaciones_creadas > 1:
            messages.success(self.request, f"¡Éxito! Se han creado y enviado {invitaciones_creadas} invitaciones simultáneamente.")
        elif invitaciones_creadas == 1:
            messages.success(self.request, f"¡Invitación enviada por email a {emails_a_invitar[0]} con éxito!")
            
        return HttpResponseRedirect(self.get_success_url())

class PlayerRegistrationView(FormView):
    """Vista pública para que un jugador se registre usando el token."""
    template_name = 'player/player_register.html'
    form_class = PlayerRegistrationForm
    
    def dispatch(self, request, *args, **kwargs):
        self.token = kwargs.get('token')
        self.invitation = get_object_or_404(Invitation, token=self.token)
        
        if self.invitation.is_used:
            messages.error(request, "Este enlace de invitación ya fue utilizado o no es válido.")
            return redirect('player:welcome') # O login, dependiendo de tus URL
            
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['invitation'] = self.invitation
        return context

    def form_valid(self, form):
        # Crear usuario
        user = form.save(commit=False)
        user.email = self.invitation.email # Forzamos el email de la invitación
        user.save()
        
        # Crear perfil y asociarlo al equipo de la invitación
        from .models import Profile
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = self.invitation.role
        profile.team = self.invitation.team
        profile.save()
        
        # Marcar invitación como usada
        self.invitation.is_used = True
        self.invitation.save()
        
        messages.success(self.request, "Registro completado con éxito. Ya puedes iniciar sesión.")
        return redirect('player:welcome') # o login
