"""
Background report-generation jobs (Phase 3.4).

Report generation previously ran synchronously inside the request handler,
which blocked the worker and made the ``generating`` status unobservable.
This module runs the heavy compile step on a background thread so the API
can return immediately with ``status='generating'`` and the frontend polls
the existing report status until it flips to ``ready`` / ``failed``.
"""
import logging
import threading

logger = logging.getLogger(__name__)


def _generate_report_task(report_id, request_meta):
    """Worker body: compile the report file, persist it, and notify the user."""
    from apps.notifications.services import notify
    from apps.reports.models import GeneratedReport
    from apps.reports.views import GeneratedReportViewSet

    try:
        report = GeneratedReport.objects.select_related(
            'template', 'engagement', 'generated_by'
        ).get(pk=report_id)

        # Minimal request stand-in so the shared audit-log helper (which only
        # reads META / user) keeps working inside the generator.
        class _FakeRequest:
            META = request_meta or {}
            user = report.generated_by

        # The PDF/Excel/Word compile logic lives on the ViewSet to avoid
        # duplicating ~1000 lines. It saves the file and flips status to ready.
        GeneratedReportViewSet().generate_report_file(report, _FakeRequest())

        # Re-read so we observe the status the generator persisted.
        report.refresh_from_db()
        link = f'/reports?id={report.id}'
        if report.status == 'ready':
            notify(
                report.generated_by,
                'report_ready',
                f'Report ready: {report.title}',
                f'Your {report.get_format_display() if hasattr(report, "get_format_display") else report.format} '
                f'report "{report.title}" has been generated and is ready to download.',
                link,
            )
        elif report.status == 'failed':
            notify(
                report.generated_by,
                'system',
                f'Report generation failed: {report.title}',
                f'Your report "{report.title}" could not be generated. {report.error_message or ""}'.strip(),
                link,
            )
    except GeneratedReport.DoesNotExist:
        logger.exception('Background report task: report %s not found', report_id)
    except Exception as exc:  # noqa: BLE001 - failures are persisted, never raised
        try:
            report = GeneratedReport.objects.get(pk=report_id)
            report.status = 'failed'
            report.error_message = str(exc)
            report.save(update_fields=['status', 'error_message', 'generated_at'])
            # Notify the requester that the job failed.
            notify(
                report.generated_by,
                'system',
                f'Report generation failed: {report.title}',
                f'Your report "{report.title}" could not be generated. {report.error_message}'.strip(),
                f'/reports?id={report.id}',
            )
        except GeneratedReport.DoesNotExist:
            logger.exception('Background report task: failed report %s missing', report_id)
        logger.exception('Background report %s failed: %s', report_id, exc)


def enqueue_report_generation(report):
    """Kick off background compilation for a GeneratedReport.

    Returns immediately; the caller keeps the report status as ``generating``.
    Threading is sufficient for a single-worker dev/server deployment; swap for
    a Celery task later if queue durability is needed.
    """
    t = threading.Thread(
        target=_generate_report_task,
        args=(report.id, {}),
        name=f'report-gen-{report.id}',
        daemon=True,
    )
    t.start()
    logger.info('Queued background report generation for report %s', report.id)
    return t