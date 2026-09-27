"""Read-scoping for the auditee role.

Reads are open to every authenticated user **by design** — `HasCapability` allows
all safe methods unconditionally (see `.permissions`) — so it is a ViewSet's
*queryset*, not its permission class, that decides what a role can list. For most
registers that is the right default: an auditor, supervisor or manager should see
the whole organisation.

The auditee is the exception. An auditee is the *audited* party — a department
representative, not an auditor — so an EEU-wide register hands them material that
is not theirs to read: other directorates' risk scores, which entities are next to
be audited, and the audit team's own working papers, including on engagements
they have nothing to do with.

Findings, evidence, corrective actions, engagements and self-assessments each
hand-wrote that narrowing. This factors the shared shape out, so a ViewSet opts in
by declaring which lookups identify a row as belonging to the viewer instead of
re-implementing it — and, more importantly, so a *new* org-wide ViewSet has
something obvious to reach for before it ships unscoped.
"""
from django.db.models import Q

# Matches `ROLE_CAPABILITIES`' string keys in `.permissions`, and the four
# hand-written viewsets this replaces.
AUDITEE = 'auditee'


class AuditeeScopeMixin:
    """Narrow an auditee's reads to their department, and to their own records.

    ``auditee_scope_fields``
        Lookups ending in ``department_id`` — the path from this model to the
        owning department. It differs per model, which is why it is declared
        rather than assumed: ``department_id``, ``engagement__department_id``,
        ``program__engagement__department_id``.

    ``auditee_scope_personal_fields``
        Fields naming the viewer directly (``assessed_by``, ``prepared_by``), so
        work an auditee is personally part of stays visible even when it falls
        outside their department.

    A user with **no** department matches on the personal fields only. That is the
    safer reading of a missing department — the alternative is showing them
    everything — and it is what the hand-written viewsets already do.

    Mix in **before** the DRF viewset so this ``get_queryset`` runs first and its
    ``super()`` call still reaches the base implementation::

        class AuditProgramViewSet(AuditeeScopeMixin, viewsets.ModelViewSet):
            auditee_scope_fields = ('engagement__department_id',)
            auditee_scope_personal_fields = ('prepared_by',)
    """

    auditee_scope_fields: tuple = ()
    auditee_scope_personal_fields: tuple = ()

    def get_queryset(self):
        qs = super().get_queryset()

        user = self.request.user
        if not (user.is_authenticated and user.role == AUDITEE):
            return qs

        # Built as an explicit union rather than starting from `Q()`: a bare
        # `Q()` is falsy, and relying on that to detect "no conditions" reads as
        # a bug to anyone who does not know it.
        scope = None
        for field in self.auditee_scope_personal_fields:
            condition = Q(**{field: user})
            scope = condition if scope is None else scope | condition
        if user.department_id:
            for field in self.auditee_scope_fields:
                condition = Q(**{field: user.department_id})
                scope = condition if scope is None else scope | condition

        if scope is None:
            # Nothing identifies a row as this auditee's, so nothing is theirs.
            # Showing the whole register would be the opposite of the intent.
            return qs.none()

        # `distinct()` because the department lookups traverse relations, and a
        # row reachable by more than one path would otherwise appear twice — once
        # per matching join.
        return qs.filter(scope).distinct()
