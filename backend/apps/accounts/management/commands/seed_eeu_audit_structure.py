"""Seed the official EEU Internal Audit Executive Office organizational structure.

Creates the Internal Audit Executive Office (IAEO) parent node and its four
core directorates, each with a Head account, directorate-specific audit
universe items, risk assessments, audit plans, and engagements (including
specialized Technical Audit parameters and the Planning & Performance
consolidated master plan).
"""
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import User, Department, Role
from apps.audit_planning.models import AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember
from apps.risk_assessment.models import RiskParameter, RiskAssessment


class Command(BaseCommand):
    help = 'Seeds the EEU Internal Audit Executive Office organizational structure with directorates, heads, universe items, plans, and engagements.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding EEU Internal Audit organizational structure...')

        current_year = datetime.datetime.now().year

        # ── 1. Create the Internal Audit Executive Office hierarchy ──────────
        iaeo, _ = Department.objects.get_or_create(
            code='IAEO',
            defaults={
                'name': 'Internal Audit Executive Office',
                'directorate_type': 'IAEO',
                'head': 'Martha Hailu',
                'staff_count': 4,
                'description': 'Executive office overseeing all EEU internal audit directorates.',
            },
        )
        self.stdout.write(f'  Created/verified: {iaeo.name}')

        directorates = [
            {
                'code': 'FPA',
                'name': 'Financial & Performance Audit Directorate',
                'directorate_type': 'FPA',
                'head': 'Abebe Kebede',
                'staff_count': 12,
                'description': 'Audits financial statements, budget execution, and performance of EEU programs.',
            },
            {
                'code': 'TA',
                'name': 'Technical Audit Directorate',
                'directorate_type': 'TA',
                'head': 'Dawit Tesfaye',
                'staff_count': 10,
                'description': 'Technical & engineering audits of substations, distribution grids, loss reduction, and transmission assets.',
            },
            {
                'code': 'ITA',
                'name': 'Information Technology Audit Directorate',
                'directorate_type': 'ITA',
                'head': 'Sarah Mohammed',
                'staff_count': 8,
                'description': 'IT audits of ERP, CIS billing, cybersecurity, and infrastructure.',
            },
            {
                'code': 'PP',
                'name': 'Planning & Performance Directorate',
                'directorate_type': 'PP',
                'head': 'Tigist Assefa',
                'staff_count': 6,
                'description': 'Central oversight: consolidates directorate plans, enterprise risk matrix, and QA/KPI monitoring.',
            },
        ]

        dept_map = {'IAEO': iaeo}
        for d in directorates:
            dept, created = Department.objects.get_or_create(
                code=d['code'],
                defaults={
                    'name': d['name'],
                    'directorate_type': d['directorate_type'],
                    'head': d['head'],
                    'staff_count': d['staff_count'],
                    'description': d['description'],
                    'parent': iaeo,
                },
            )
            dept_map[d['code']] = dept
            if created:
                self.stdout.write(f'  Created directorate: {dept.name}')

        # ── 2. Create Directorate Head user accounts ─────────────────────────
        head_accounts = [
            {
                'email': 'fpa.head@eeu.com',
                'username': 'fpa_head',
                'first_name': 'Abebe',
                'last_name': 'Kebede',
                'role': Role.AUDIT_MANAGER,
                'department': dept_map['FPA'],
                'employee_id': 'EEU-20001',
            },
            {
                'email': 'ta.head@eeu.com',
                'username': 'ta_head',
                'first_name': 'Dawit',
                'last_name': 'Tesfaye',
                'role': Role.AUDIT_MANAGER,
                'department': dept_map['TA'],
                'employee_id': 'EEU-20002',
            },
            {
                'email': 'ita.head@eeu.com',
                'username': 'ita_head',
                'first_name': 'Sarah',
                'last_name': 'Mohammed',
                'role': Role.AUDIT_MANAGER,
                'department': dept_map['ITA'],
                'employee_id': 'EEU-20003',
            },
            {
                'email': 'pp.head@eeu.com',
                'username': 'pp_head',
                'first_name': 'Tigist',
                'last_name': 'Assefa',
                'role': Role.AUDIT_MANAGER,
                'department': dept_map['PP'],
                'employee_id': 'EEU-20004',
            },
        ]

        heads = {}
        for h in head_accounts:
            user = User.objects.filter(email=h['email']).first()
            if not user:
                user = User.objects.create_user(
                    email=h['email'],
                    username=h['username'],
                    first_name=h['first_name'],
                    last_name=h['last_name'],
                    role=h['role'],
                    department=h['department'],
                    employee_id=h['employee_id'],
                )
                user.set_password('head123')
                user.save()
                self.stdout.write(f'  Created head account: {user.email}')
            heads[h['department'].code] = user

        # ── 3. Ensure Risk Parameters exist ──────────────────────────────────
        risk_params = [
            {'name': 'Financial Impact', 'description': 'Potential direct or indirect monetary loss to EEU', 'weight': 0.3, 'category': 'financial'},
            {'name': 'Operational Disruption', 'description': 'Degree of interruption to power supply or utility services', 'weight': 0.25, 'category': 'operational'},
            {'name': 'Compliance Violations', 'description': 'Exposure to regulatory penalties or audits exceptions', 'weight': 0.2, 'category': 'compliance'},
            {'name': 'Process Complexity', 'description': 'Internal controls complexity and number of actors', 'weight': 0.15, 'category': 'operational'},
            {'name': 'System Automation', 'description': 'Lack of automated reconciliation or reliance on manual work', 'weight': 0.1, 'category': 'it'},
            {'name': 'Technical Asset Criticality', 'description': 'Criticality of substations, feeders, and transmission assets', 'weight': 0.2, 'category': 'operational'},
            {'name': 'Energy Loss Exposure', 'description': 'Exposure to technical and commercial energy losses', 'weight': 0.15, 'category': 'operational'},
        ]
        for rp in risk_params:
            RiskParameter.objects.get_or_create(
                name=rp['name'],
                defaults={'description': rp['description'], 'weight': rp['weight'], 'category': rp['category']},
            )

        # ── 4. Directorate-specific Audit Universe items ─────────────────────
        universe_data = [
            # Financial & Performance Audit
            {
                'code': 'UNIV-FPA-01', 'name': 'EEU Budget Execution & Treasury Management',
                'category': 'process', 'dept': dept_map['FPA'], 'risk': 4.5, 'freq': 'Annually',
                'tech': {},
            },
            {
                'code': 'UNIV-FPA-02', 'name': 'Revenue Collection & Billing Reconciliation',
                'category': 'process', 'dept': dept_map['FPA'], 'risk': 4.7, 'freq': 'Annually',
                'tech': {},
            },
            {
                'code': 'UNIV-FPA-03', 'name': 'Procurement & Contract Management Performance',
                'category': 'process', 'dept': dept_map['FPA'], 'risk': 4.2, 'freq': 'Bi-annually',
                'tech': {},
            },
            # Technical Audit
            {
                'code': 'UNIV-TA-01', 'name': 'High Voltage Substation Assets (132kV & 230kV)',
                'category': 'department', 'dept': dept_map['TA'], 'risk': 4.8, 'freq': 'Annually',
                'tech': {
                    'asset_type': 'Substation',
                    'voltage_level': 'HV',
                    'feeder_id': 'SUB-HV-001',
                    'energy_loss_score': 8.5,
                    'engineering_compliance_rating': 'B',
                    'technical_risk_parameters': {'transformer_health': 'fair', 'protection_system': 'good'},
                },
            },
            {
                'code': 'UNIV-TA-02', 'name': 'Medium Voltage Distribution Grids (15kV & 33kV)',
                'category': 'department', 'dept': dept_map['TA'], 'risk': 4.4, 'freq': 'Annually',
                'tech': {
                    'asset_type': 'Distribution Grid',
                    'voltage_level': 'MV',
                    'feeder_id': 'DIST-MV-014',
                    'energy_loss_score': 12.3,
                    'engineering_compliance_rating': 'C',
                    'technical_risk_parameters': {'conductor_condition': 'aging', 'load_balance': 'poor'},
                },
            },
            {
                'code': 'UNIV-TA-03', 'name': 'Transmission Lines & Energy Loss Reduction Program',
                'category': 'project', 'dept': dept_map['TA'], 'risk': 4.6, 'freq': 'Annually',
                'tech': {
                    'asset_type': 'Transmission Line',
                    'voltage_level': 'HV',
                    'feeder_id': 'TRANS-HV-007',
                    'energy_loss_score': 9.8,
                    'engineering_compliance_rating': 'B',
                    'technical_risk_parameters': {'line_inspection': 'overdue', 'corridor_clearance': 'partial'},
                },
            },
            # Information Technology Audit
            {
                'code': 'UNIV-ITA-01', 'name': 'ERP Financials & Enterprise Resource Planning System',
                'category': 'system', 'dept': dept_map['ITA'], 'risk': 4.9, 'freq': 'Annually',
                'tech': {
                    'asset_type': 'Enterprise System',
                    'voltage_level': 'N/A',
                    'feeder_id': 'N/A',
                    'energy_loss_score': 0,
                    'engineering_compliance_rating': 'N/A',
                    'technical_risk_parameters': {'system_criticality': 'mission_critical', 'data_center': 'primary'},
                },
            },
            {
                'code': 'UNIV-ITA-02', 'name': 'CIS Billing & Customer Information System',
                'category': 'system', 'dept': dept_map['ITA'], 'risk': 4.6, 'freq': 'Annually',
                'tech': {
                    'asset_type': 'Billing System',
                    'voltage_level': 'N/A',
                    'feeder_id': 'N/A',
                    'energy_loss_score': 0,
                    'engineering_compliance_rating': 'N/A',
                    'technical_risk_parameters': {'customer_base': '2.5M', 'billing_cycle': 'monthly'},
                },
            },
            {
                'code': 'UNIV-ITA-03', 'name': 'Cybersecurity & Network Infrastructure',
                'category': 'system', 'dept': dept_map['ITA'], 'risk': 4.8, 'freq': 'Bi-annually',
                'tech': {
                    'asset_type': 'Network Infrastructure',
                    'voltage_level': 'N/A',
                    'feeder_id': 'N/A',
                    'energy_loss_score': 0,
                    'engineering_compliance_rating': 'N/A',
                    'technical_risk_parameters': {'perimeter': 'firewall', 'ids': 'deployed'},
                },
            },
            # Planning & Performance
            {
                'code': 'UNIV-PP-01', 'name': 'Enterprise-Wide Audit Universe & Consolidated Risk Matrix',
                'category': 'process', 'dept': dept_map['PP'], 'risk': 4.3, 'freq': 'Annually',
                'tech': {},
            },
            {
                'code': 'UNIV-PP-02', 'name': 'Quality Assurance & Audit KPI Monitoring Program',
                'category': 'process', 'dept': dept_map['PP'], 'risk': 3.8, 'freq': 'Annually',
                'tech': {},
            },
        ]

        universe_items = {}
        for uni in universe_data:
            entry, created = AuditUniverse.objects.get_or_create(
                code=uni['code'],
                defaults={
                    'name': uni['name'],
                    'category': uni['category'],
                    'department': uni['dept'],
                    'directorate': uni['dept'],
                    'risk_score': uni['risk'],
                    'audit_frequency': uni['freq'],
                    'owner': uni['dept'].head,
                    'status': 'active',
                    'technical_metadata': uni['tech'],
                },
            )
            universe_items[uni['code']] = entry
            if created:
                self.stdout.write(f'  Created universe item: {entry.name}')

        # ── 5. Directorate Risk Assessments ──────────────────────────────────
        risk_assessments = [
            {'dept': dept_map['FPA'], 'universe': universe_items['UNIV-FPA-01'], 'likelihood': 4, 'impact': 4, 'ce': 3},
            {'dept': dept_map['FPA'], 'universe': universe_items['UNIV-FPA-02'], 'likelihood': 5, 'impact': 4, 'ce': 2},
            {'dept': dept_map['TA'], 'universe': universe_items['UNIV-TA-01'], 'likelihood': 4, 'impact': 5, 'ce': 3},
            {'dept': dept_map['TA'], 'universe': universe_items['UNIV-TA-02'], 'likelihood': 4, 'impact': 4, 'ce': 2},
            {'dept': dept_map['ITA'], 'universe': universe_items['UNIV-ITA-01'], 'likelihood': 5, 'impact': 5, 'ce': 3},
            {'dept': dept_map['ITA'], 'universe': universe_items['UNIV-ITA-03'], 'likelihood': 4, 'impact': 5, 'ce': 2},
            {'dept': dept_map['PP'], 'universe': universe_items['UNIV-PP-01'], 'likelihood': 3, 'impact': 4, 'ce': 3},
        ]
        for ra in risk_assessments:
            _, created = RiskAssessment.objects.get_or_create(
                department=ra['dept'],
                year=current_year,
                assessment_period='Annual',
                audit_universe=ra['universe'],
                defaults={
                    'likelihood': ra['likelihood'],
                    'impact': ra['impact'],
                    'control_effectiveness': ra['ce'],
                    'notes': f'Annual risk assessment for {ra["dept"].name}.',
                    'assessed_by': heads[ra['dept'].code],
                },
            )
            if created:
                self.stdout.write(f'  Created risk assessment for {ra["dept"].name}')

        # ── 6. Directorate Audit Plans ───────────────────────────────────────
        # Consolidated master plan (Planning & Performance umbrella)
        master_plan, created = AuditPlan.objects.get_or_create(
            year=current_year,
            title=f'EEU Consolidated Annual Audit Plan {current_year}',
            defaults={
                'description': 'Master consolidated annual audit plan aggregating all directorate plan segments.',
                'objectives': 'Enterprise-wide risk-based audit coverage across financial, technical, IT, and performance domains.',
                'scope': 'All EEU directorates, substations, distribution grids, transmission assets, and information systems.',
                'methodology': 'COSO Internal Control Framework, risk-based sampling, and consolidated risk heatmaps.',
                'status': 'approved',
                'plan_scope': 'consolidated',
                'directorate': dept_map['PP'],
                'created_by': heads['PP'],
                'approved_by': heads['PP'],
                'approved_at': timezone.now(),
                'start_date': datetime.date(current_year, 1, 1),
                'end_date': datetime.date(current_year, 12, 31),
                'total_budget_days': 400,
            },
        )
        if created:
            self.stdout.write(f'  Created consolidated master plan: {master_plan.title}')

        directorate_plans = [
            {
                'dept': dept_map['FPA'], 'title': f'Financial & Performance Audit Plan {current_year}',
                'desc': 'Directorate plan for financial statement audits, budget execution, and performance reviews.',
                'days': 120,
            },
            {
                'dept': dept_map['TA'], 'title': f'Technical Audit Plan {current_year}',
                'desc': 'Directorate plan for substation, distribution grid, transmission, and energy loss audits.',
                'days': 110,
            },
            {
                'dept': dept_map['ITA'], 'title': f'Information Technology Audit Plan {current_year}',
                'desc': 'Directorate plan for ERP, CIS billing, cybersecurity, and infrastructure audits.',
                'days': 90,
            },
            {
                'dept': dept_map['PP'], 'title': f'Planning & Performance Oversight Plan {current_year}',
                'desc': 'Directorate plan for QA reviews, KPI monitoring, and consolidated risk matrix updates.',
                'days': 80,
            },
        ]

        plan_map = {'master': master_plan}
        for dp in directorate_plans:
            plan, created = AuditPlan.objects.get_or_create(
                year=current_year,
                title=dp['title'],
                defaults={
                    'description': dp['desc'],
                    'objectives': f'Execute the {dp["dept"].name} segment of the EEU consolidated annual audit plan.',
                    'scope': dp['dept'].name,
                    'methodology': 'Risk-based sampling aligned with the consolidated risk matrix.',
                    'status': 'approved',
                    'plan_scope': 'directorate',
                    'directorate': dp['dept'],
                    'parent_plan': master_plan,
                    'created_by': heads[dp['dept'].code],
                    'approved_by': heads['PP'],
                    'approved_at': timezone.now(),
                    'start_date': datetime.date(current_year, 1, 1),
                    'end_date': datetime.date(current_year, 12, 31),
                    'total_budget_days': dp['days'],
                },
            )
            plan_map[dp['dept'].code] = plan
            if created:
                self.stdout.write(f'  Created directorate plan: {plan.title}')

        # ── 7. Directorate Engagements ───────────────────────────────────────
        engagement_data = [
            {
                'number': f'ENG-{current_year}-FPA-001',
                'title': 'EEU Budget Execution & Treasury Management Audit',
                'type': 'financial',
                'dept': dept_map['FPA'],
                'plan': plan_map['FPA'],
                'universe': universe_items['UNIV-FPA-01'],
                'status': 'in_progress',
                'risk': 'high',
                'tech': {},
            },
            {
                'number': f'ENG-{current_year}-FPA-002',
                'title': 'Revenue Collection & Billing Reconciliation Performance Audit',
                'type': 'performance',
                'dept': dept_map['FPA'],
                'plan': plan_map['FPA'],
                'universe': universe_items['UNIV-FPA-02'],
                'status': 'planned',
                'risk': 'critical',
                'tech': {},
            },
            {
                'number': f'ENG-{current_year}-TA-001',
                'title': 'High Voltage Substation Assets Technical Audit (132kV & 230kV)',
                'type': 'technical',
                'dept': dept_map['TA'],
                'plan': plan_map['TA'],
                'universe': universe_items['UNIV-TA-01'],
                'status': 'fieldwork',
                'risk': 'critical',
                'tech': {
                    'asset_type': 'Substation',
                    'voltage_level': 'HV',
                    'feeder_id': 'SUB-HV-001',
                    'energy_loss_score': 8.5,
                    'engineering_compliance_rating': 'B',
                    'technical_risk_parameters': {'transformer_health': 'fair', 'protection_system': 'good'},
                },
            },
            {
                'number': f'ENG-{current_year}-TA-002',
                'title': 'Medium Voltage Distribution Grids Technical Audit (15kV & 33kV)',
                'type': 'technical',
                'dept': dept_map['TA'],
                'plan': plan_map['TA'],
                'universe': universe_items['UNIV-TA-02'],
                'status': 'planned',
                'risk': 'high',
                'tech': {
                    'asset_type': 'Distribution Grid',
                    'voltage_level': 'MV',
                    'feeder_id': 'DIST-MV-014',
                    'energy_loss_score': 12.3,
                    'engineering_compliance_rating': 'C',
                    'technical_risk_parameters': {'conductor_condition': 'aging', 'load_balance': 'poor'},
                },
            },
            {
                'number': f'ENG-{current_year}-ITA-001',
                'title': 'ERP Financials & Enterprise Resource Planning System IT Audit',
                'type': 'it',
                'dept': dept_map['ITA'],
                'plan': plan_map['ITA'],
                'universe': universe_items['UNIV-ITA-01'],
                'status': 'in_progress',
                'risk': 'critical',
                'tech': {
                    'asset_type': 'Enterprise System',
                    'voltage_level': 'N/A',
                    'feeder_id': 'N/A',
                    'energy_loss_score': 0,
                    'engineering_compliance_rating': 'N/A',
                    'technical_risk_parameters': {'system_criticality': 'mission_critical', 'data_center': 'primary'},
                },
            },
            {
                'number': f'ENG-{current_year}-ITA-002',
                'title': 'Cybersecurity & Network Infrastructure IT Audit',
                'type': 'it',
                'dept': dept_map['ITA'],
                'plan': plan_map['ITA'],
                'universe': universe_items['UNIV-ITA-03'],
                'status': 'planned',
                'risk': 'high',
                'tech': {
                    'asset_type': 'Network Infrastructure',
                    'voltage_level': 'N/A',
                    'feeder_id': 'N/A',
                    'energy_loss_score': 0,
                    'engineering_compliance_rating': 'N/A',
                    'technical_risk_parameters': {'perimeter': 'firewall', 'ids': 'deployed'},
                },
            },
            {
                'number': f'ENG-{current_year}-PP-001',
                'title': 'Enterprise-Wide Consolidated Risk Matrix & QA Review',
                'type': 'special',
                'dept': dept_map['PP'],
                'plan': plan_map['PP'],
                'universe': universe_items['UNIV-PP-01'],
                'status': 'planned',
                'risk': 'medium',
                'tech': {},
            },
        ]

        for ed in engagement_data:
            eng, created = AuditEngagement.objects.get_or_create(
                engagement_number=ed['number'],
                defaults={
                    'plan': ed['plan'],
                    'audit_universe': ed['universe'],
                    'title': ed['title'],
                    'engagement_type': ed['type'],
                    'department': ed['dept'],
                    'directorate': ed['dept'],
                    'status': ed['status'],
                    'lead_auditor': heads[ed['dept'].code],
                    'supervisor': heads[ed['dept'].code],
                    'planned_start': datetime.date(current_year, 4, 1),
                    'planned_end': datetime.date(current_year, 7, 30),
                    'planned_days': 30,
                    'risk_level': ed['risk'],
                    'technical_metadata': ed['tech'],
                },
            )
            if created:
                self.stdout.write(f'  Created engagement: {eng.title}')
                AuditTeamMember.objects.get_or_create(
                    engagement=eng,
                    user=heads[ed['dept'].code],
                    defaults={'role': 'lead', 'allocated_days': 20},
                )

        self.stdout.write(self.style.SUCCESS('EEU Internal Audit organizational structure seeded successfully!'))