"""
EEU Audit Planning - End-to-End API Test
Tests the full audit planner workflow via the REST API.
"""
import requests
import json

BASE = "http://localhost:8000/api"

def sep(label):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print('='*50)

def ok(msg): print(f"  ✅  {msg}")
def fail(msg): print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️   {msg}")

sep("STEP 1: Login as Audit Manager")
r = requests.post(f"{BASE}/auth/login/", json={"email": "manager@eeu.com", "password": "user123"})
if r.status_code == 200:
    token = r.json().get("access") or r.json().get("token")
    ok(f"Logged in! Token: {str(token)[:40]}...")
else:
    fail(f"Login failed: {r.status_code} - {r.text[:200]}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

sep("STEP 2: Load Departments")
r = requests.get(f"{BASE}/auth/departments/", headers=headers)
depts = r.json().get("results", [])
info(f"Departments found: {len(depts)}")
dept_id = depts[0]["id"] if depts else None
for d in depts:
    info(f"  - [{d['id']}] {d['name']} ({d['code']})")

sep("STEP 3: Load Audit Universe")
r = requests.get(f"{BASE}/planning/universe/", headers=headers)
universe = r.json().get("results", [])
info(f"Universe items found: {len(universe)}")
for u in universe:
    info(f"  - [{u['id']}] {u['code']} | {u['name']} | Risk: {u['risk_score']}")

sep("STEP 4: Create New Audit Universe Entity")
payload = {
    "name": "Test Power Grid Monitoring System",
    "code": "UNIV-TEST-99",
    "category": "system",
    "risk_score": 4.2,
    "audit_frequency": "Annually",
    "owner": "Test Owner",
    "status": "active",
    "department": dept_id
}
r = requests.post(f"{BASE}/planning/universe/", json=payload, headers=headers)
if r.status_code == 201:
    new_univ = r.json()
    ok(f"Created universe entity: [{new_univ['id']}] {new_univ['name']}")
else:
    info(f"Universe create response: {r.status_code} - {r.text[:300]}")
    # Try to use existing
    new_univ = universe[0] if universe else None

sep("STEP 5: Load Existing Plans")
r = requests.get(f"{BASE}/planning/plans/", headers=headers)
plans = r.json().get("results", [])
info(f"Plans found: {len(plans)}")
for p in plans:
    info(f"  - [{p['id']}] {p['title']} | Status: {p['status']} | Year: {p['year']}")

sep("STEP 6: Create New Annual Audit Plan")
import datetime
year = datetime.datetime.now().year
payload = {
    "title": f"Test Audit Plan Q3 {year}",
    "year": year,
    "total_budget_days": 60,
    "start_date": f"{year}-07-01",
    "end_date": f"{year}-09-30",
    "description": "Test quarterly plan for end-to-end validation",
    "objectives": "Validate financial controls for Q3",
    "scope": "Finance and IT departments"
}
r = requests.post(f"{BASE}/planning/plans/", json=payload, headers=headers)
if r.status_code == 201:
    new_plan = r.json()
    ok(f"Created plan: [{new_plan['id']}] {new_plan['title']} | Status: {new_plan['status']}")
else:
    fail(f"Plan create failed: {r.status_code} - {r.text[:300]}")
    new_plan = plans[0] if plans else None

sep("STEP 7: Submit Plan for Approval")
if new_plan and new_plan.get("status") == "draft":
    r = requests.post(f"{BASE}/planning/plans/{new_plan['id']}/submit/", headers=headers)
    if r.status_code == 200:
        submitted = r.json()
        ok(f"Plan submitted! New status: {submitted.get('status')}")
    else:
        fail(f"Submit failed: {r.status_code} - {r.text[:300]}")
else:
    info("Skipping submit - plan not in draft state or not available")

sep("STEP 8: Load Existing Engagements")
r = requests.get(f"{BASE}/planning/engagements/", headers=headers)
engagements = r.json().get("results", [])
info(f"Engagements found: {len(engagements)}")
for e in engagements:
    info(f"  - [{e['id']}] {e['engagement_number']} | {e['title'][:40]}... | Status: {e['status']}")

sep("STEP 9: Schedule New Audit Engagement")
# Use any approved/active plan
target_plan = None
for p in plans:
    if p.get("status") in ["approved", "active"]:
        target_plan = p
        break
if not target_plan and plans:
    target_plan = plans[0]

if target_plan:
    payload = {
        "title": "Test Power Grid Infrastructure Audit",
        "plan": target_plan["id"],
        "audit_universe": new_univ["id"] if new_univ else None,
        "engagement_type": "operational",
        "risk_level": "high",
        "planned_start": f"{year}-07-15",
        "planned_end": f"{year}-08-15",
        "planned_days": 30,
        "department": dept_id
    }
    if not payload["audit_universe"]:
        del payload["audit_universe"]
    
    r = requests.post(f"{BASE}/planning/engagements/", json=payload, headers=headers)
    if r.status_code == 201:
        new_eng = r.json()
        ok(f"Created engagement: [{new_eng['id']}] {new_eng['engagement_number']} | {new_eng['title']}")
    else:
        fail(f"Engagement create failed: {r.status_code} - {r.text[:400]}")
else:
    fail("No plan available to attach engagement to")

sep("STEP 10: Verify Users in System")
r = requests.get(f"{BASE}/auth/users/", headers=headers)
if r.status_code == 200:
    users = r.json().get("results", [])
    info(f"Users found: {len(users)}")
    for u in users:
        info(f"  - [{u['id']}] {u['email']} | Role: {u['role']} | {u.get('full_name','')}")
else:
    fail(f"Could not load users: {r.status_code}")

sep("✅ END-TO-END TEST COMPLETE")
