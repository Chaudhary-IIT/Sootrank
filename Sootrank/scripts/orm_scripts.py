from Registration.models import Department, Branch,Category
from django.db import transaction

CORE_ELECTIVE_CHOICES = [
    ("DC", "Disciplinary Core (DC)"),
    ("DE", "Disciplinary Elective (DE)"),
    ("IC", "Institute Core (IC)"),
    ("HSS","Humanities and Social Science (HSS)"),
    ("FE", "Free Elective (FE)"),
    ("IKS","Indian Knowledge System (IKS)"),
    ("ISTP","Interactive Socio-Technical Practicum (ISTP)"),
    ("MTP","Major Technical Project (MTP)"),
]


def run():
    # Ensure departments exist
    for code, name in Department.SCHOOL_CHOICES:
        Department.objects.get_or_create(code=code, defaults={'name': name})

    # Branch.code -> Department.code (align with your BRANCHES, including "MVLSI")
    mapping = {
        "CSE":   "SCEE",
        "DSE":   "SCEE",
        "ME":    "SMME",
        "CE":    "SCENE",
        "EE":    "SCEE",
        "MVLSI": "SCEE",
        "EP":    "SPS",
        "GE":    "SMME",
        "MnC":   "SMSS",
        "MSE":   "SMME",
        "BioEng":"SBB",
        "BS_CS": "SCS",
    }

    valid_codes = {c for c, _ in Branch.BRANCHES}
    created = updated = skipped = 0

    with transaction.atomic():
        for br_code, dept_code in mapping.items():
            if br_code not in valid_codes:
                print(f"Skip {br_code}: not in Branch.BRANCHES")
                skipped += 1
                continue
            dept = Department.objects.get(code=dept_code)
            br, is_new = Branch.objects.get_or_create(name=br_code, defaults={"department": dept})
            if is_new:
                created += 1
                print(f"Branch created: {br_code} -> {dept_code}")
            else:
                if br.department_id != dept.id:
                    br.department = dept
                    br.save()
                    updated += 1
                    print(f"Branch updated: {br_code} -> {dept_code}")
                else:
                    print(f"Branch exists (linked): {br_code} -> {dept_code}")
    print(f"Summary: created={created}, updated={updated}, skipped={skipped}")

    for b in Branch.objects.select_related("department").order_by("name"):
        print(f"{b.name:6s} -> {b.department.code if b.department else 'None'}")

    for code, label in CORE_ELECTIVE_CHOICES:
        obj, created = Category.objects.update_or_create(
            code=code, defaults={"label": label}
        )
        print(("Created" if created else "Updated"), obj)
