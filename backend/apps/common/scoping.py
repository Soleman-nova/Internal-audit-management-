"""Read-scoping for the auditee role and for regional FPA auditors.

Reads are open to every authenticated user **by design** — `HasCapability` allows
all safe methods unconditionally (see `.permissions`) — so it is a ViewSet's
*queryset*, not its permission class, that decides what a role can list. For most
registers that is the right default: an auditor, supervisor or manager should see
the whole organisation.

**Auditee scoping** (``AuditeeScopeMixin``)
--------------------------------------------
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

**Region scoping** (``RegionScopeMixin``)
------------------------------------------
FPA regional auditors are scoped to the region their *department* (audit unit) is
tagged with. The trigger is structural, not role-based: any user whose department
carries a non-null ``region_id`` is confined to that region's records, whatever
their role. A directorate unit (FPA/TA/ITA/PP/IAEO) carries no ``region_id``, so
its staff — including the Regional Coordination Audit Manager — keep an EEU-wide
view.

The binding lives on the unit, not on the user, for two reasons:

1. One audit unit covers one region, so the constraint is a property of the
   unit, not of the individual. Adding a fifth Adama auditor is a user-create
   with nothing to get wrong; moving the unit to another region moves everyone
   in it.
2. ``User.region`` already means "the region this person is based in" (the
   Users page filters on it) and does not drive queryset scoping — there is
   one source of truth, not two.

**Known limitation**: a regional unit created without a ``region_id`` is
indistinguishable from an HQ unit and will not be scoped. The seed always sets
it. A ``DepartmentSerializer.validate`` guard could close the hole; not included
here because it would hard-code the node's code into validation.
"""
from django.db.models import Q

# Matches `ROLE_CAPABILITIES`' string keys in `.permissions`, and the four
# hand-written viewsets this replaces.
AUDITEE = 'auditee'


def region_for(user):
    """The region a viewer is confined to, or None for organisation-wide.

    Returns the ``region_id`` of the user's department if that department is a
    regional audit unit (i.e. its ``region_id`` is set), else ``None``.

    ``None`` means "no restriction" — everyone who is not in a regional unit
    keeps today's EEU-wide view.
    """
    if not user or not user.is_authenticated:
        return None
    dept = getattr(user, 'department', None)
    if dept is None:
        return None
    # dept.region_id is None for every non-regional-audit department (HQ,
    # directorate, corporate unit, or a regional audit unit that was created
    # without a region set).
    return dept.region_id or None


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


class RegionScopeMixin:
    """Narrow a regional audit-unit user's reads to their region.

    ``region_scope_fields``
        Lookups ending in ``region_id`` — the path from this model to a region
        FK. It differs per model: ``region_id``, ``engagement__region_id``,
        ``finding__engagement__region_id``, etc. Declared per ViewSet rather
        than assumed, for the same reason as ``AuditeeScopeMixin``.

    The trigger is structural: any user whose *department* carries a non-null
    ``region_id`` is confined to that region's records. HQ/directorate users
    — including the Regional Coordination Audit Manager whose unit is
    ``FPA-RAC`` (no ``region_id``) — keep the EEU-wide view.

    An auditee is not a regional auditor, so the two scopes never interact: the
    ``auditee`` role guard in ``AuditeeScopeMixin`` and the department check
    here are orthogonal, and a regional unit would need to be populated with
    auditee users for both to fire at once — which the org design does not do.

    Mix in **before** the DRF viewset so this ``get_queryset`` runs first::

        class AuditUniverseViewSet(RegionScopeMixin, AuditeeScopeMixin, viewsets.ModelViewSet):
            region_scope_fields = ('region_id',)
            auditee_scope_fields = ('department_id',)
            auditee_scope_personal_fields = ()
    """

    region_scope_fields: tuple = ()

    def get_queryset(self):
        qs = super().get_queryset()

        user = self.request.user
        region_id = region_for(user)
        if region_id is None:
            return qs

        # Built as an explicit union rather than starting from `Q()` — same
        # reasoning as AuditeeScopeMixin: a bare falsy Q() reads as a bug.
        scope = None
        for field in self.region_scope_fields:
            condition = Q(**{field: region_id})
            scope = condition if scope is None else scope | condition

        if scope is None:
            # No fields declared: the ViewSet opted in but forgot to configure
            # which path leads to the region. Treat as unscoped rather than
            # accidentally hiding everything.
            return qs

        # `distinct()` because dotted lookups traverse joins, and a row
        # reachable by more than one path would otherwise appear twice.
        return qs.filter(scope).distinct()
