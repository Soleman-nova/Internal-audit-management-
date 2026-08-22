"""
URL configuration for EEU Internal Audit Management System
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/planning/', include('apps.audit_planning.urls')),
    path('api/execution/', include('apps.audit_execution.urls')),
    path('api/findings/', include('apps.findings.urls')),
    path('api/risk/', include('apps.risk_assessment.urls')),
    path('api/corrective/', include('apps.corrective_actions.urls')),
    path('api/reports/', include('apps.reports.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
]

# Media is served by Django only in development, and only for convenience —
# `static()` already returns [] when DEBUG is False, so the unconditional form
# was a silent no-op in production while still exposing every uploaded file
# without authentication in development. Audit evidence and working papers are
# reached through their permission-gated `download` actions instead
# (EvidenceViewSet.download, WorkingPaperViewSet.download).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
