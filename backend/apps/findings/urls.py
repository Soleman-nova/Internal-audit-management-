from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('findings', views.AuditFindingViewSet, basename='finding')
router.register('evidence', views.EvidenceViewSet, basename='evidence')

urlpatterns = [path('', include(router.urls))]
