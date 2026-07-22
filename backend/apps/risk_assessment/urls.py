from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('parameters', views.RiskParameterViewSet, basename='riskparameter')
router.register('assessments', views.RiskAssessmentViewSet, basename='riskassessment')
router.register('self-assessments', views.SelfAssessmentViewSet, basename='selfassessment')

urlpatterns = [path('', include(router.urls))]
