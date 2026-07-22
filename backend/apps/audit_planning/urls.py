from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('universe', views.AuditUniverseViewSet, basename='universe')
router.register('plans', views.AuditPlanViewSet, basename='plan')
router.register('engagements', views.AuditEngagementViewSet, basename='engagement')

urlpatterns = [path('', include(router.urls))]
