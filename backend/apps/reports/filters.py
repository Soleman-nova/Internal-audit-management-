import django_filters
from django.db.models import Q
from .models import GeneratedReport


class GeneratedReportFilter(django_filters.FilterSet):
    """
    Rich filtering for generated audit reports archive and analytics.
    Supports filtering by date range, directorate, department, auditor,
    status, template, format, and search keywords.
    """
    date_from = django_filters.DateFilter(field_name='generated_at', lookup_expr='date__gte')
    date_to = django_filters.DateFilter(field_name='generated_at', lookup_expr='date__lte')
    directorate = django_filters.CharFilter(method='filter_directorate')
    department = django_filters.CharFilter(method='filter_department')
    auditor = django_filters.CharFilter(method='filter_auditor')
    status = django_filters.CharFilter(method='filter_status')
    format = django_filters.CharFilter(method='filter_format')
    template = django_filters.NumberFilter(field_name='template_id')
    engagement = django_filters.NumberFilter(field_name='engagement_id')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = GeneratedReport
        fields = ['template', 'engagement', 'format', 'status']

    def filter_directorate(self, queryset, name, value):
        if not value or value == 'all':
            return queryset
        if str(value).isdigit():
            return queryset.filter(engagement__directorate_id=int(value))
        return queryset.filter(engagement__directorate__directorate_type__iexact=value)

    def filter_department(self, queryset, name, value):
        if not value:
            return queryset
        if str(value).isdigit():
            return queryset.filter(engagement__department_id=int(value))
        return queryset.filter(engagement__department__name__icontains=value)

    def filter_auditor(self, queryset, name, value):
        if not value:
            return queryset
        if str(value).isdigit():
            val_id = int(value)
            return queryset.filter(
                Q(engagement__lead_auditor_id=val_id) |
                Q(generated_by_id=val_id)
            )
        return queryset.filter(
            Q(engagement__lead_auditor__first_name__icontains=value) |
            Q(engagement__lead_auditor__last_name__icontains=value) |
            Q(generated_by__first_name__icontains=value) |
            Q(generated_by__last_name__icontains=value)
        )

    def filter_status(self, queryset, name, value):
        if not value:
            return queryset
        statuses = [s.strip().lower() for s in value.split(',') if s.strip()]
        if statuses:
            return queryset.filter(status__in=statuses)
        return queryset

    def filter_format(self, queryset, name, value):
        if not value:
            return queryset
        formats = [f.strip().lower() for f in value.split(',') if f.strip()]
        if formats:
            return queryset.filter(format__in=formats)
        return queryset

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value) |
            Q(engagement__title__icontains=value) |
            Q(engagement__engagement_number__icontains=value) |
            Q(template__name__icontains=value)
        )
