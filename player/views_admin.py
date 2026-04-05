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
