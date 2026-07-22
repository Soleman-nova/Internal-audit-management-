from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('actions', views.CorrectiveActionViewSet, basename='correctiveaction')

urlpatterns = [path('', include(router.urls))]
