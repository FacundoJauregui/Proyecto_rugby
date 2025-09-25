from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MatchViewSet

router = DefaultRouter()
router.register(r'matches', MatchViewSet, basename='api-matches')

urlpatterns = [
    path('', include(router.urls)),
]