"""
Seed Risk Assessment data for EEU heatmap
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.accounts.models import User, Department, Role
from apps.risk_assessment.models import RiskAssessment
from apps.audit_planning.models import AuditUniverse
import datetime

current_year = datetime.datetime.now().year

# Get departments
try:
    fin  = Department.objects.get(code='FIN')
    it   = Department.objects.get(code='IT')
    proc = Department.objects.get(code='PROC')
    hr   = Department.objects.get(code='HR')
    dist = Department.objects.get(code='DIST')
except Department.DoesNotExist as e:
    print(f"Error: {e}. Run seed_data first.")
    sys.exit(1)

# Get assessor
assessor = User.objects.filter(role=Role.AUDIT_MANAGER).first()
if not assessor:
    assessor = User.objects.filter(is_superuser=True).first()

def _get_universe(dept):
    """Resolve the active audit-universe entry for a department (Phase 3.1)."""
    return AuditUniverse.objects.filter(department=dept, status='active').first()


risk_data = [
    {"dept": proc, "likelihood": 4, "impact": 4, "ctrl": 2, "period": "Annual", "notes": "High-value procurement with weak controls"},
    {"dept": fin,  "likelihood": 3, "impact": 4, "ctrl": 3, "period": "Annual", "notes": "ERP financial controls — moderate risk"},
    {"dept": dist, "likelihood": 4, "impact": 3, "ctrl": 3, "period": "Annual", "notes": "Billing revenue integrity risk"},
    {"dept": it,   "likelihood": 2, "impact": 5, "ctrl": 3, "period": "Annual", "notes": "IT system catastrophic impact but unlikely"},
    {"dept": hr,   "likelihood": 2, "impact": 2, "ctrl": 4, "period": "Annual", "notes": "Payroll administration, well controlled"},
    {"dept": dist, "likelihood": 3, "impact": 3, "ctrl": 2, "period": "Q2",     "notes": "Substation security — in-quarter check"},
    {"dept": proc, "likelihood": 5, "impact": 4, "ctrl": 2, "period": "Q1",     "notes": "Emergency procurement CRITICAL"},
]

created = 0
for rd in risk_data:
    exists = RiskAssessment.objects.filter(
        department=rd["dept"], year=current_year, assessment_period=rd["period"]
    ).exists()
    if not exists:
        ra = RiskAssessment(
            department=rd["dept"],
            audit_universe=_get_universe(rd["dept"]),
            year=current_year,
            assessment_period=rd["period"],
            likelihood=rd["likelihood"],
            impact=rd["impact"],
            control_effectiveness=rd["ctrl"],
            notes=rd["notes"],
            assessed_by=assessor,
        )
        ra.save()
        print(f"  Created: {rd['dept'].name} | L{rd['likelihood']}×I{rd['impact']} = {ra.risk_score} ({ra.risk_rating})")
        created += 1
    else:
        print(f"  Skipped (exists): {rd['dept'].name} {current_year} {rd['period']}")

print(f"\nDone. Created {created} risk assessments.")
