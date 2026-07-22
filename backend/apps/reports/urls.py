from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('templates', views.ReportTemplateViewSet, basename='reporttemplate')
router.register('generated', views.GeneratedReportViewSet, basename='generatedreport')

urlpatterns = [path('', include(router.urls))]
