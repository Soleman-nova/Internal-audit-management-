"""Give the three legacy demo departments their Amharic names.

``seed_data`` / ``seed_e2e_demo`` created FIN, PROC and DIST without ``name_am``,
so on an Amharic interface those three units fell back to English while every
other department rendered in Amharic. The seed commands now set the names, and
this backfills databases seeded before that change.

Only blank names are written, so a name edited through the admin or API is left
alone. A database without these legacy rows (a production tree, or one where
``retire_legacy_departments`` deleted them) is untouched.
"""
from django.db import migrations


# code -> Amharic name, matching the wording used in the EEU corporate export.
AMHARIC_NAMES = {
    'FIN': 'ፋይናንስ እና ሒሳብ',          # Finance and Accounts
    'PROC': 'ግዢ እና ሎጂስቲክስ',          # Procurement and Logistics
    'DIST': 'የኃይል ስርጭት',            # Power Distribution
}


def fill_blank_names(apps, schema_editor):
    Department = apps.get_model('accounts', 'Department')
    for code, name_am in AMHARIC_NAMES.items():
        Department.objects.filter(code=code, name_am='').update(name_am=name_am)


def clear_names(apps, schema_editor):
    Department = apps.get_model('accounts', 'Department')
    for code, name_am in AMHARIC_NAMES.items():
        Department.objects.filter(code=code, name_am=name_am).update(name_am='')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_alter_audittrail_action'),
    ]

    operations = [
        migrations.RunPython(fill_blank_names, clear_names),
    ]
