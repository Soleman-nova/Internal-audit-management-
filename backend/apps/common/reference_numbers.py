"""Collision-free reference numbers for findings, engagements, and CAPAs.

Three viewsets used to build their identifiers from five random digits::

    num = ''.join(random.choices(string.digits, k=5))
    serializer.save(finding_number=f'FND-{num}')

Every one of those columns is ``unique=True``, so a repeat is not a duplicate
row — it is an ``IntegrityError`` that surfaces as a 500 and discards whatever
the auditor had just typed. On a 100,000-value namespace that is ordinary
birthday math rather than a remote edge case: by ~500 findings there is a ~71%
chance at least one create has already blown up.

The replacement is a year-scoped sequence — ``FND-2026-0001`` — which is also
what an audit function actually wants, since the number now says when the
record was raised and how many preceded it that year.
"""
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.db.models.functions import Length
from django.utils import timezone

# A create is only retried if a concurrent create took the number we picked.
# Three attempts is generous: each retry re-reads the sequence, so the only way
# to exhaust them is sustained simultaneous writes to the same model.
MAX_ATTEMPTS = 3

SEQUENCE_WIDTH = 4


def next_reference_number(model, field, prefix, year=None, width=SEQUENCE_WIDTH):
    """The next ``PREFIX-YYYY-NNNN`` for ``model.field``, scoped to one year.

    Ordering is by length first and then lexicographically, which for a fixed
    prefix is true numeric order. A plain ``Max()`` on the char column would
    read '9999' as greater than '10000' and hand out a duplicate on the
    ten-thousandth record of the year.
    """
    if year is None:
        year = timezone.now().year
    stem = f'{prefix}-{year}-'
    latest = (
        model.objects
        .filter(**{f'{field}__startswith': stem})
        .order_by(Length(field), field)
        .values_list(field, flat=True)
        .last()
    )
    sequence = 1
    if latest:
        try:
            sequence = int(latest[len(stem):]) + 1
        except (TypeError, ValueError):
            # A hand-seeded or imported number that does not parse. Fall back to
            # the count so we still move forward instead of restarting at 1.
            sequence = model.objects.filter(**{f'{field}__startswith': stem}).count() + 1
    return f'{stem}{sequence:0{width}d}'


def save_with_reference_number(serializer, field, prefix, **extra):
    """``serializer.save()`` with a freshly allocated reference number.

    Allocation and insert happen in one transaction, and an ``IntegrityError``
    from a concurrent create is retried with a new number rather than being
    returned to the user as a 500.
    """
    model = serializer.Meta.model
    for attempt in range(MAX_ATTEMPTS):
        try:
            with transaction.atomic():
                number = next_reference_number(model, field, prefix)
                return serializer.save(**{field: number}, **extra)
        except IntegrityError:
            # Retrying is safe: ModelSerializer.save() only assigns
            # self.instance once create() has returned, so a failed attempt
            # leaves the serializer untouched.
            if attempt == MAX_ATTEMPTS - 1:
                raise
    raise AssertionError('unreachable')  # pragma: no cover
