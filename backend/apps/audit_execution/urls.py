from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('programs', views.AuditProgramViewSet, basename='program')
router.register('procedures', views.AuditProcedureViewSet, basename='procedure')
router.register('working-papers', views.WorkingPaperViewSet, basename='workingpaper')

urlpatterns = [path('', include(router.urls))]
