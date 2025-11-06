from collections import defaultdict
from io import TextIOWrapper
import json
from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Sum
from django.utils.text import slugify
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from openpyxl import Workbook
from Registration.models import Branch, Category, Course, CourseBranch, Department, ProgramRequirement, Student, Faculty, Admins, StudentCourse, AssessmentComponent,AssessmentScore
from django.contrib.auth import authenticate , login as auth_login
from django.contrib.auth.hashers import make_password,check_password
from django.db.models import Count, Q, OuterRef, Exists 
from django.views.decorators.http import require_POST,require_http_methods
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from urllib.parse import urlencode
from django.core.files.storage import default_storage
import re
from Registration.forms import FacultyEditForm, StudentEditForm
import csv
from django.http import JsonResponse
import pandas as pd
from dataclasses import dataclass
from datetime import datetime


EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@iitmandi\.ac\.in$')
SLOTS = ["A","B","C","D","E","F","G","H","FS"]
CATEGORY_MAP = {
    "DC": "DC",
    "DE": "DE",
    "IC": "IC",
    "HSS": "HSS",
    "FE": "FE",
    "IKS": "IKS",
    "ISTP": "ISTP",
    "MTP": "MTP",
}

CATEGORIES = [
    {"code": "DC", "label": "Disciplinary Core (DC)"},
    {"code": "DE", "label": "Disciplinary Elective (DE)"},
    {"code": "IC", "label": "Institute Core (IC)"},
    {"code": "HSS", "label": "Humanities and Social Science (HSS)"},
    {"code": "FE", "label": "Free Elective (FE)"},
    {"code": "IKS", "label": "Indian Knowledge System (IKS)"},
    {"code": "ISTP", "label": "Interactive Socio-Technical Practicum (ISTP)"},
    {"code": "MTP", "label": "Major Technical Project (MTP)"},
]
CATEGORY_HEADERS = ["DC", "DE", "IC", "HSS", "FE", "IKS", "ISTP", "MTP"]
HEADER_TO_CATEGORY = {h: h for h in CATEGORY_HEADERS}

GRADE_BOUNDARIES = [
    ("A", 85),
    ("B", 75),
    ("C", 65),
    ("D", 55),
    ("E", 45),
    ("F", 0),
]
PASS_MIN_PERCENT = 45  # for letter-graded; PF handled by is_pass_fail

GRADE_POINTS = {
    "A": 10,
    "A-": 9,
    "B": 8,
    "B-": 7,
    "C": 6,
    "C-": 5,
    "D": 4,
    "F": 0,
    "FS": 0,
}

def _compute_semester_from_roll_and_today(roll_no: str, today=None) -> int:
    if today is None:
        today = timezone.now().date()
    try:
        yr2 = int(roll_no[1:3])
        admit_year = 2000 + yr2
    except Exception:
        # Fallback to student.semester or 1
        return 1
    years_delta = max(0, today.year - admit_year)
    term_index = 1 if today.month >= 7 else 2
    sem = years_delta * 2 + term_index
    return max(1, sem)


# settings flag name
TEMP_PREREG_OPEN_FLAG = "PREREG_TEMP_OPEN"

def _deadline_open() -> bool:
    # Temporary override has highest priority
    temp = getattr(settings, TEMP_PREREG_OPEN_FLAG, None)
    if temp is True:
        return True
    if temp is False:
        return False

    # Date-based logic (existing)
    deadline = getattr(settings, "PREREG_DEADLINE", None)
    if not deadline:
        return True
    now = timezone.now()
    if timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
    return now <= deadline


def _safe_str(v):
    return "" if v is None else str(v).strip()

def _is_blank_or_nan(v):
    s = _safe_str(v)
    return s == "" or s.lower() in ("nan", "none", "null")

def _split_codes(cell):
    if _is_blank_or_nan(cell):
        return []
    s = str(cell)
    for sep in ["|", ";"]:
        s = s.replace(sep, ",")
    if "," in s:
        tokens = s.split(",")
    else:
        tokens = s.split()
    return [t.strip().upper() for t in tokens if t.strip()]

@dataclass
class FacultyMini:
    first_name: str
    last_name: str | None
    email_id: str
    department: str

#---------------------------------------------------------------------------------------------------------------

def login(request):
    if request.method == "POST":
        identifier = request.POST['identifier'].lower()
        password = request.POST['password']

        try:
            if Admins.objects.filter(email_id=identifier).exists():
                Admin = Admins.objects.get(email_id=identifier)
                if check_password(password, Admin.password):
                    return redirect("/custom-admin/")
                else:
                    messages.error(request, "Invalid Admin Credentials")
                    return render(request, "login.html")
        except Admin.DoesNotExist:
            pass

        # 🔹 Case 1: Faculty
        try:
            if Faculty.objects.filter(email_id=identifier).exists():
                faculty = Faculty.objects.get(email_id=identifier)
                if check_password(password, faculty.password):
                    request.session["email_id"] = faculty.email_id  # stable across reloads
                    request.session["flash_ctx"] = {
                        "full_name": f"{faculty.first_name}",
                        "role_label": "Faculty",
                    }  # optional one-time
                    return render(request, "auth_successful.html", {"redirect_url": "/faculty_dashboard/"})
                else:
                    messages.error(request, "Invalid Faculty Credentials")
                    return render(request, "login.html")
        except Faculty.DoesNotExist:
            pass

        # 🔹 Case 2: Student
        try:
            if Student.objects.filter(roll_no=identifier).exists():
                student = Student.objects.get(roll_no=identifier)
            elif Student.objects.filter(email_id=identifier).exists():
                student = Student.objects.get(email_id=identifier)
            else:
                messages.error(request, "User Not Found")
                return render(request, "login.html")

            if check_password(password, student.password):
                request.session["roll_no"] = student.roll_no  # stable across reloads
                request.session["flash_ctx"] = {
                    "full_name": f"{student.first_name}",
                    "role_label": "Student",
                }  # optional one-time
                return render(request, "auth_successful.html", {"redirect_url": "/students_dashboard/"})
            else:
                messages.error(request, "Invalid Student Credentials")
        except Student.DoesNotExist:
            messages.error(request, "First Register Yourself")

    return render(request, "login.html")



def register(request):
    if request.method=='POST':
        firstname=request.POST['firstname']
        lastname=request.POST['lastname']
        roll_no=request.POST['roll_no']
        email=request.POST['email']
        department=request.POST['department']
        branch=request.POST['branch']
        password1=request.POST['password1']
        password2=request.POST['password2']
        hashed_password = make_password(password1)

        pattern1=re.compile(r'^(?:B|b|V|v|D|d|IM|im|MB|mb)\d{5}$')
        pattern2=re.compile(r'^(?:B|b|V|v|D|d|IM|im|MB|mb)\d{5}@students\.iitmandi\.ac\.in$')


        if(pattern1.match(roll_no) and pattern2.match(email) and (email[:len(roll_no)].lower()==roll_no.lower())):
            
            try:
                Student.objects.create(
                    first_name=firstname,
                    last_name=lastname,
                    email_id=email.lower(),
                    roll_no=roll_no.lower(),
                    password=hashed_password,
                    department=department,
                    branch=branch
                )
                messages.success(request, 'Registration successful! Please log in.')
                return redirect('/')  # Redirect to login page or another page
            except IntegrityError:
                messages.error(request, "Student with this email or roll number already exists.")
        else:
            messages.error(request, "Invalid Roll No. or Institute Email")

    return render(request, 'register.html')

def students_dashboard(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        # not logged in or session expired
        return redirect("/")
    student = get_object_or_404(Student, roll_no=roll_no)

    flash = request.session.pop("flash_ctx", {})  # optional, disappears after first load
    semesters = StudentCourse.objects.filter(student=student).order_by('semester').values_list('semester', flat=True).distinct()
    results_visible = False
    admin = Admins.objects.first()
    if admin:
        results_visible = admin.is_results_visible()

    context = {
        "student": student,
        "full_name": flash.get("full_name"),
        "role_label": flash.get("role_label", "Student"),
        "results_visible": results_visible,
        "semesters": semesters,
    }
    return render(request, "students_dashboard.html", context)

def faculty_dashboard(request):
    email_id = request.session.get("email_id")
    if not email_id:
        # not logged in or session expired
        return redirect("/")
    faculty = get_object_or_404(Faculty, email_id=email_id)

    flash = request.session.pop("flash_ctx", {})  # optional, disappears after first load
    context = {
        "faculty": faculty,
        "full_name": flash.get("full_name"),
        "role_label": flash.get("role_label", "Faculty"),
    }
    return render(request,'faculty_dashboard.html',context)

def pre_registration(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    student = get_object_or_404(Student, roll_no=roll_no)
    branch = student.branch
    current_sem = _compute_semester_from_roll_and_today(student.roll_no)
    window_open = _deadline_open()

    if request.method == "POST":
        if not window_open:
            messages.error(request, "Pre‑registration window is closed.")
            return redirect("prereg_page")

        raw = request.POST.get("payload", "")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            messages.error(request, "Invalid submission payload.")
            return redirect("prereg_page")

        selections = payload.get("selections") or []
        if not isinstance(selections, list):
            messages.error(request, "Invalid selections.")
            return redirect("prereg_page")

        # Build course cache and process per slot
        # Expect each selection: { slot, course_code, category, credits }
        codes = [ (s.get("course_code") or "").strip().upper() for s in selections if s.get("course_code") ]
        course_map = {c.code.upper(): c for c in Course.objects.filter(code__in=codes)}

        created, updated, skipped_locked = 0, 0, 0
        with transaction.atomic():
            for sel in selections:
                slot = (sel.get("slot") or "").strip().upper()
                code = (sel.get("course_code") or "").strip().upper()
                if not slot or not code:
                    continue
                course = course_map.get(code)
                if not course or course.slot != slot:
                    continue

                # If slot already has an enrolled course, lock it
                # Remove any non-enrolled existing rows in this slot
                StudentCourse.objects.filter(
                    student=student, semester=current_sem, course__slot=slot
                ).exclude(status="ENR").delete()

                obj, created_now = StudentCourse.objects.get_or_create(
                    student=student, course=course, semester=current_sem,
                    defaults={
                        "status": "PND",
                        "is_pass_fail": bool(sel.get("is_pass_fail") or False),
                        "type": chosen_cat or None,
                    }
                )


                # Remove any non-enrolled existing rows in this slot
                StudentCourse.objects.filter(
                    student=student, semester=current_sem, course__slot=slot
                ).exclude(status="ENR").delete()

                chosen_cat = (sel.get("category") or "").upper()
                if chosen_cat == "ALL":
                    primary_cat = (
                        CourseBranch.objects
                        .filter(course=course, branch=branch)
                        .values_list("categories__code", flat=True)
                        .first()
                    )
                    chosen_cat = (primary_cat or "").upper()

                obj, created_now = StudentCourse.objects.get_or_create(
                    student=student, course=course, semester=current_sem,
                    defaults={
                        "status": "PND",
                        "is_pass_fail": bool(sel.get("is_pass_fail") or False),
                        "type": chosen_cat or None,
                    }
                )
                if created_now:
                    created += 1
                else:
                    if obj.status != "ENR":
                        obj.status = "PND"
                        obj.type = chosen_cat or obj.type
                        obj.is_pass_fail = bool(sel.get("is_pass_fail") or False)
                        obj.save(update_fields=["status","type","is_pass_fail"])
                        updated += 1

        if created:
            messages.success(request, f"Submitted {created} request(s).")
        if updated:
            messages.info(request, f"Updated {updated} request(s).")
        if skipped_locked:
            messages.warning(request, f"{skipped_locked} slot(s) are already approved and were not changed.")
        return redirect("check_status_page")

    # GET: build options and prefill
    base_cb = CourseBranch.objects.filter(branch=branch)
    slot_map = {}
    # categories is a list of dicts like: [{"code":"IC","label":"Institute Core"}, ...]
    CATEGORIES = getattr(settings, "COURSE_CATEGORIES", [
        {"code": "DC", "label": "Disciplinary Core (DC)"},
        {"code": "DE", "label": "Disciplinary Elective (DE)"},
        {"code": "IC", "label": "Institute Core (IC)"},
        {"code": "HSS", "label": "Humanities and Social Science (HSS)"},
        {"code": "FE", "label": "Free Elective (FE)"},
        {"code": "IKS", "label": "Indian Knowledge System (IKS)"},
        {"code": "ISTP", "label": "Interactive Socio-Technical Practicum (ISTP)"},
        {"code": "MTP", "label": "Major Technical Project (MTP)"},
    ])

    for slot in SLOTS:
        cat_map = {}
        for cat in [c["code"] for c in CATEGORIES]:
            qs = (
                Course.objects.filter(
                    slot=slot,
                    coursebranch__branch=branch,
                    coursebranch__categories__code=cat,
                )
                .prefetch_related(
                    Prefetch(
                        "coursebranch_set",
                        queryset=base_cb.prefetch_related("categories"),
                        to_attr="cb_for_branch",
                    )
                ).distinct()
            )
            cat_map[cat] = qs
        slot_map[slot] = cat_map

    existing = (
        StudentCourse.objects
        .filter(student=student, semester=current_sem)
        .select_related("course")
    )
    preselected_by_slot = {}
    locked_slots = set()
    for sc in existing:
        if sc.course and sc.course.slot:
            preselected_by_slot[sc.course.slot] = sc.course.code
            if sc.status == "ENR":
                locked_slots.add(sc.course.slot)
    slot_map_json = {}
    for slot, cat_map in slot_map.items():
        slot_map_json[slot] = {}
        for cat, qs in cat_map.items():
            # qs is a QuerySet of Course
            slot_map_json[slot][cat] = list(
                qs.values("code", "name", "credits")  # only JSON-safe fields
            )

    context = {
        "student": student,
        "categories": CATEGORIES,
        "slot_map": slot_map,
        "slot_map_json": slot_map_json,
        "slots": SLOTS,
        "min_credit": 12,
        "max_credit": 22,
        "computed_semester": current_sem,
        "window_open": window_open,
        "preselected_by_slot": preselected_by_slot,
        "locked_slots": list(locked_slots),
    }
    return render(request, "registration/pre_registration.html", context)


def check_status(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    student = get_object_or_404(Student, roll_no=roll_no)
    current_sem = _compute_semester_from_roll_and_today(student.roll_no)

    enrollments = (
        StudentCourse.objects
        .filter(student=student, semester=current_sem)
        .select_related("course")
        .prefetch_related(Prefetch("course__faculties"))
        .order_by("course__slot","course__code")
    )
    pf_total = (
        StudentCourse.objects
        .filter(student=student, is_pass_fail=True)
        .aggregate(total=Sum("course__credits"))
        .get("total") or 0
    )
    context = {
        "student": student,
        "enrollments": enrollments,
        "pf_total": pf_total,
        "sem_display": current_sem,
    }
    return render(request, "registration/check_status.html", context)

@require_POST
def apply_pf_changes(request):
    # Auth: student session
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    student = get_object_or_404(Student, roll_no=roll_no)

    raw = request.POST.get("payload") or ""
    try:
        data = json.loads(raw)
        changes = data.get("changes") or []
    except Exception:
        messages.error(request, "Invalid update payload.")
        return redirect("check_status_page")

    # Current PF total
    pf_total = (
        StudentCourse.objects
        .filter(student=student, is_pass_fail=True)
        .aggregate(total=Sum("course__credits"))
        .get("total") or 0
    )

    applied, blocked = 0, 0
    for item in changes:
        sc_id = item.get("sc_id")
        to_pf = bool(item.get("to_pf"))
        sc = StudentCourse.objects.select_related("course","student").filter(id=sc_id, student=student).first()
        if not sc:
            continue

        # Skip approved courses entirely
        if sc.status == "ENR":
            blocked += 1
            continue

        credits = sc.course.credits or 0
        current = bool(sc.is_pass_fail)

        # If no net change, skip
        if to_pf == current:
            continue

        # Enforce 9-credit cap when turning on
        next_total = pf_total + credits if to_pf and not current else pf_total - credits if (not to_pf and current) else pf_total
        if to_pf and next_total > 9:
            blocked += 1
            continue

        # Apply
        sc.is_pass_fail = to_pf
        sc.save(update_fields=["is_pass_fail"])
        pf_total = next_total
        applied += 1

    if applied:
        messages.success(request, f"Applied {applied} change(s).")
    if blocked:
        messages.warning(request, f"{blocked} change(s) were blocked (approved or over 9 credits).")

    return redirect("check_status_page")


def registered_courses(request):
    return render(request, 'registration/registered_course.html')

# def course_request(request):
#     return render(request, 'instructor/course_request.html')

def student_profile(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    student = get_object_or_404(Student, roll_no=roll_no)
    return render(request, "student_profile.html", {"student": student})

def faculty_profile(request):
    email_id = request.session.get("email_id")
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    faculty = get_object_or_404(Faculty, email_id=email_id)
    return render(request, "instructor/profile.html", {"faculty": faculty})


def student_edit_profile(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    student = get_object_or_404(Student, roll_no=roll_no)
    if request.method == "POST":
        form = StudentEditForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            return redirect(reverse("student_profile"))
    else:
        form = StudentEditForm(instance=student)
    context = {
        "form": form,
        "student": student,
    }
    return render(request, "student_edit_profile.html", context)



def faculty_edit_profile(request):
    email_id = request.session.get("email_id")  #
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    faculty = get_object_or_404(Faculty, email_id=email_id)

    if request.method == "POST":
        form = FacultyEditForm(request.POST, request.FILES, instance=faculty)
        if form.is_valid():
            form.save()
            return redirect(reverse("faculty_profile")) 
    else:
        form = FacultyEditForm(instance=faculty)

    return render(request, "instructor/edit_profile.html", {"form": form, "faculty": faculty})

def custom_admin_home(request):
    return render(request, "admin/custom_admin_home.html")

def custom_admin_students(request):
    students = Student.objects.select_related("department","branch").all().order_by("roll_no")

    if request.method == 'POST':
        firstname = request.POST['firstname'].strip()
        lastname  = request.POST['lastname'].strip()
        roll_no   = request.POST['roll_no'].strip()
        email     = request.POST['email'].strip()
        password1 = request.POST['password']
        mobile_no = request.POST.get('mobile_no') or None

        # Get selected IDs from dropdowns
        dept_id = request.POST.get('department_id')
        branch_id = request.POST.get('branch_id')

        # Validate basic formats
        pattern1 = re.compile(r'^(?:B|b|V|v|D|d|IM|im|MB|mb)\d{5}$')
        pattern2 = re.compile(r'^(?:B|b|V|v|D|d|IM|im|MB|mb)\d{5}@students\.iitmandi\.ac\.in$')

        if pattern1.match(roll_no) and pattern2.match(email) and (email[:len(roll_no)].lower() == roll_no.lower()):
            try:
                dept = Department.objects.get(pk=dept_id) if dept_id else None
                branch = Branch.objects.get(pk=branch_id) if branch_id else None

                Student.objects.create(
                    first_name=firstname,
                    last_name=lastname,
                    email_id=email.lower(),
                    roll_no=roll_no.lower(),
                    password=make_password(password1),
                    department=dept,     # ForeignKey object, not string
                    branch=branch,       # ForeignKey object, not string
                    mobile_no=mobile_no,
                )
                messages.success(request, 'Registration successful.')
                return redirect('custom_admin_students')
            except Department.DoesNotExist:
                messages.error(request, "Selected department does not exist.")
            except Branch.DoesNotExist:
                messages.error(request, "Selected branch does not exist.")
            except IntegrityError:
                messages.error(request, "Student with this email or roll number already exists.")
        else:
            messages.error(request, "Invalid Roll No. or Institute Email")

    # Supply choices for dropdowns
    departments = Department.objects.all().order_by('code')
    branches = Branch.objects.all().order_by('name')
    return render(request, "admin/custom_admin_students.html", {
        "students": students,
        "departments": departments,
        "branches": branches,
    })

def custom_admin_students_bulk_add(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            messages.error(request, "Please upload a CSV or Excel file.")
            return redirect("custom_admin_students_bulk_add")

        temp_file_path = default_storage.save(f"temp/{csv_file.name}", csv_file)
        added_count = 0
        error_rows = []

        try:
            ext = csv_file.name.split('.')[-1].lower()
            if ext == 'csv':
                with default_storage.open(temp_file_path, mode='r') as file:
                    reader = csv.DictReader(file)
                    rows = list(reader)
            elif ext in ['xls', 'xlsx']:
                with default_storage.open(temp_file_path, 'rb') as f:
                    df = pd.read_excel(f)
                rows = df.to_dict(orient='records')
            else:
                messages.error(request, "Unsupported file format. Please upload CSV or Excel.")
                default_storage.delete(temp_file_path)
                return redirect("custom_admin_students_bulk_add")

            # Cache departments and branches for FK efficiency
            departments = {d.code: d for d in Department.objects.all()}
            branches = {b.name: b for b in Branch.objects.all()}

            # Required fields except last_name (nullable)
            required_fields = [
                "first_name", "email_id", "password",
                "roll_no", "department", "branch"
            ]

            def safe_str(val):
                return '' if val is None else str(val).strip()

            for idx, row in enumerate(rows, start=2):  # header = 1
                missing_fields = [f for f in required_fields if not row.get(f) or safe_str(row.get(f)) == '']
                if missing_fields:
                    error_rows.append(f"Row {idx}: Missing required fields: {', '.join(missing_fields)}.")
                    continue

                first_name = safe_str(row.get('first_name'))
                last_name = safe_str(row.get('last_name')) or None  # Nullable field
                email = safe_str(row.get('email_id')).lower()
                password_raw = row.get('password')
                roll_no = safe_str(row.get('roll_no')).lower()
                dept_code = safe_str(row.get('department')).upper()
                br_code = safe_str(row.get('branch'))

                dept = departments.get(dept_code)
                if not dept:
                    error_rows.append(f"Row {idx}: Department code '{dept_code}' not found.")
                    continue

                br = branches.get(br_code)
                if not br:
                    error_rows.append(f"Row {idx}: Branch code '{br_code}' not found.")
                    continue

                try:
                    student, created = Student.objects.get_or_create(
                        roll_no=roll_no,
                        defaults={
                            "first_name": first_name,
                            "last_name": last_name,
                            "email_id": email,
                            "password": make_password(password_raw),
                            "department": dept,
                            "branch": br,
                            "mobile_no": None,  # since no mobile column
                        },
                    )
                    if created:
                        added_count += 1
                    else:
                        error_rows.append(f"Row {idx}: Student with roll_no '{roll_no}' already exists.")
                except IntegrityError as e:
                    error_rows.append(f"Row {idx}: Integrity error: {str(e)}")
                except Exception as e:
                    error_rows.append(f"Row {idx}: Error saving student - {str(e)}")

        except Exception as e:
            messages.error(request, f"Failed to process file: {str(e)}")
            default_storage.delete(temp_file_path)
            return redirect("custom_admin_students_bulk_add")

        default_storage.delete(temp_file_path)

        if added_count:
            messages.success(request, f"Successfully added {added_count} students.")
        for error in error_rows:
            messages.error(request, error)
        return redirect("custom_admin_students_bulk_add")

    return render(request, "admin/bulk_add.html")


def delete_student_by_roll(request, roll_no):
    student = get_object_or_404(Student, roll_no=roll_no)
    if request.method == "POST":
        student.delete()
        return redirect('custom_admin_students')

def custom_admin_edit_student(request, roll_no):
    student = get_object_or_404(Student, roll_no=roll_no)
    if request.method == "POST":
        student.roll_no = request.POST.get("roll_no", "").strip().lower()
        student.first_name = request.POST.get("first_name", "").strip()
        student.last_name  = request.POST.get("last_name", "").strip()
        student.email_id   = request.POST.get("email_id", "").strip().lower()

        dept_id = request.POST.get("department")
        br_id   = request.POST.get("branch")

        # Resolve FKs safely
        if dept_id:
            try:
                student.department = Department.objects.get(pk=dept_id)
            except Department.DoesNotExist:
                messages.error(request, "Selected department does not exist.")
                return redirect("custom_admin_edit_student", roll_no=student.roll_no)
        else:
            student.department = None

        if br_id:
            try:
                student.branch = Branch.objects.get(pk=br_id)
            except Branch.DoesNotExist:
                messages.error(request, "Selected branch does not exist.")
                return redirect("custom_admin_edit_student", roll_no=student.roll_no)
        else:
            student.branch = None

        student.mobile_no = request.POST.get("mobile_no") or None

        student.save()
        messages.success(request, "Student details updated successfully.")
        return redirect("custom_admin_students")

    # GET: provide dropdown data
    departments = Department.objects.all().order_by('code')
    branches = Branch.objects.all().order_by('name')
    return render(request, "admin/custom_admin_edit_student.html", {
        "student": student,
        "departments": departments,
        "branches": branches,
    })


def custom_admin_faculty(request):
    faculties = Faculty.objects.select_related("department").all().order_by("last_name", "first_name")
    departments = Department.objects.all().order_by('code')

    if request.method == 'POST':
        first_name = request.POST.get('firstname', '').strip()
        last_name = request.POST.get('lastname', '').strip()
        email_id = request.POST.get('email', '').strip().lower()
        department_id = request.POST.get('department')
        mobile_no = request.POST.get('mobile_no') or None
        raw_password = request.POST.get('password', '')

        # Basic validation
        if not EMAIL_RE.match(email_id):
            messages.error(request, "Invalid Institute Email")
            return redirect('custom_admin_faculty')

        # Resolve FK
        dept = None
        if department_id:
            try:
                dept = Department.objects.get(pk=department_id)
            except Department.DoesNotExist:
                messages.error(request, "Selected department does not exist.")
                return redirect('custom_admin_faculty')
        else:
            messages.error(request, "Please select a department.")
            return redirect('custom_admin_faculty')

        try:
            Faculty.objects.create(
                first_name=first_name,
                last_name=last_name,
                email_id=email_id,
                password=make_password(raw_password),
                department=dept,
                mobile_no=mobile_no,
            )
            messages.success(request, 'Faculty added successfully.')
            return redirect('custom_admin_faculty')
        except IntegrityError:
            messages.error(request, "Faculty with this email already exists.")
        except Exception as e:
            messages.error(request, f"Error adding faculty: {e}")

    return render(request, "admin/custom_admin_faculty.html", {
        "faculties": faculties,
        "departments": departments
    })


def custom_admin_faculty_bulk_add(request):
    if request.method == "POST":
        faculty_file = request.FILES.get("faculty_file")
        if not faculty_file:
            messages.error(request, "Please upload a CSV or Excel file.")
            return redirect("custom_admin_faculty_bulk_add")

        temp_file_path = default_storage.save(f"temp/{faculty_file.name}", faculty_file)
        added_count = 0
        error_rows = []

        try:
            ext = faculty_file.name.split('.')[-1].lower()
            if ext == 'csv':
                with default_storage.open(temp_file_path, mode='r') as file:
                    reader = csv.DictReader(file)
                    rows = list(reader)
            elif ext in ['xls', 'xlsx']:
                with default_storage.open(temp_file_path, 'rb') as f:
                    df = pd.read_excel(f)
                rows = df.to_dict(orient='records')
            else:
                messages.error(request, "Unsupported file format. Upload CSV or Excel.")
                return redirect("custom_admin_faculty_bulk_add")

            departments = {d.code: d for d in Department.objects.all()}

            def safe_str(val):
                return '' if val is None else str(val).strip()

            for idx, row in enumerate(rows, start=2):
                first_name = safe_str(row.get('first_name'))
                last_name = safe_str(row.get('last_name'))
                email = safe_str(row.get('email_id')).lower()
                password_raw = row.get('password')
                dept_code = safe_str(row.get('department')).upper()

                missing_fields = [f for f,v in [('first_name', first_name),  ('email_id', email), ('password', password_raw), ('department', dept_code)] if not v]
                if missing_fields:
                    error_rows.append(f"Row {idx}: Missing required fields: {', '.join(missing_fields)}.")
                    continue

                dept = departments.get(dept_code)
                if not dept:
                    error_rows.append(f"Row {idx}: Department code '{dept_code}' not found.")
                    continue

                mobile_no_raw = row.get('mobile_no')
                mobile_no = safe_str(mobile_no_raw) if mobile_no_raw else None

                try:
                    faculty, created = Faculty.objects.get_or_create(
                        email_id=email,
                        defaults={
                            'first_name': first_name,
                            'last_name': last_name if last_name else None,
                            'password': make_password(password_raw),
                            'department': dept,
                            'mobile_no': mobile_no if mobile_no else None,
                        }
                    )
                    if created:
                        added_count += 1
                    else:
                        error_rows.append(f"Row {idx}: Faculty with email '{email}' already exists.")
                except IntegrityError as e:
                    error_rows.append(f"Row {idx}: Integrity error: {str(e)}")
                except Exception as e:
                    error_rows.append(f"Row {idx}: Error saving faculty - {str(e)}")

        except Exception as e:
            messages.error(request, f"Failed to process file: {str(e)}")
            default_storage.delete(temp_file_path)
            return redirect("custom_admin_faculty_bulk_add")

        default_storage.delete(temp_file_path)

        if added_count:
            messages.success(request, f"Successfully added {added_count} faculties.")
        for err in error_rows:
            messages.error(request, err)
        return redirect("custom_admin_faculty_bulk_add")

    return render(request, "admin/custom_admin_faculty_bulk.html")



def delete_faculty(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    if request.method == "POST":
        faculty.delete()
        return redirect('custom_admin_faculty')

def custom_admin_edit_faculty(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    departments = Department.objects.all().order_by('code')

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name", "").strip()
        email_id   = request.POST.get("email_id", "").strip().lower()
        mobile_no  = request.POST.get("mobile_no") or None
        dept_id    = request.POST.get("department")
        raw_pwd    = request.POST.get("password", "")

        # Resolve FK
        dept = None
        if dept_id:
            try:
                dept = Department.objects.get(pk=dept_id)
            except Department.DoesNotExist:
                messages.error(request, "Selected department does not exist.")
                return redirect("custom_admin_edit_faculty", faculty_id=faculty.id)

        # Assign fields
        faculty.first_name = first_name
        faculty.last_name  = last_name
        faculty.email_id   = email_id
        faculty.department = dept
        faculty.mobile_no  = mobile_no

        # Update password only if a new one is provided (avoid double-hashing existing hash)
        if raw_pwd.strip():
            faculty.password = make_password(raw_pwd)

        # Update profile image if new file uploaded
        new_img = request.FILES.get("profile_image")
        if new_img:
            faculty.profile_image = new_img

        faculty.save()
        messages.success(request, "Faculty details updated successfully.")
        return redirect("custom_admin_faculty")

    return render(request, "admin/custom_admin_edit_faculty.html", {
        "faculty": faculty,
        "departments": departments
    })



def custom_admin_branch(request):
    branches = Branch.objects.select_related("department").order_by("department__code", "name")
    departments = Department.objects.all().order_by("code")

    # derive choices from model (list of (code, label))
    branch_choices = Branch.BRANCHES

    if request.method == "POST":
        dept_id = request.POST.get("department_id")
        branch_code = request.POST.get("branch_code")  # e.g., "CSE"

        if not dept_id or not branch_code:
            messages.error(request, "Please select both Department and Branch.")
            return redirect("custom_admin_branch")

        try:
            dept = Department.objects.get(pk=dept_id)
        except Department.DoesNotExist:
            messages.error(request, "Selected department does not exist.")
            return redirect("custom_admin_branch")

        valid_codes = {c for c, _ in branch_choices}
        if branch_code not in valid_codes:
            messages.error(request, "Invalid branch selection.")
            return redirect("custom_admin_branch")

        try:
            # Branch.name stores the code because name has choices=BRANCHES
            obj, created = Branch.objects.get_or_create(name=branch_code, defaults={"department": dept})
            if not created:
                # if it exists but department differs, update it
                if obj.department_id != dept.id:
                    obj.department = dept
                    obj.save()
                    messages.success(request, f"Branch {obj.name} moved to {dept.code}.")
                else:
                    messages.info(request, "Branch already exists under this department.")
            else:
                messages.success(request, "Branch created successfully.")
        except IntegrityError:
            messages.error(request, "Branch with the same code already exists.")
        return redirect("custom_admin_branch")

    return render(request, "admin/custom_admin_branch.html", {
        "branches": branches,
        "departments": departments,
        "branch_choices": branch_choices,
    })


def ajax_branches_json(request):
    dept_id = request.GET.get("department_id")
    qs = Branch.objects.none()
    if dept_id:
        qs = Branch.objects.filter(department_id=dept_id).order_by("name")
    data = [{"id": b.id, "label": getattr(b, "get_name_display", lambda: b.name)()} for b in qs]
    return JsonResponse({"options": data})



def custom_admin_courses(request):
    courses = Course.objects.all().order_by("code")
    slot_choices = Course.SLOT_CHOICES  # for form select

    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        name = request.POST.get("name", "").strip()
        credits = request.POST.get("credits")
        ltpc = request.POST.get("LTPC", "").strip().upper()
        slot = request.POST.get("slot")

        # Basic validation
        if not code or not name or not credits or not slot:
            messages.error(request, "Please fill in all required fields.")
            return redirect("custom_admin_courses")

        try:
            credits = int(credits)
        except ValueError:
            messages.error(request, "Credits must be an integer.")
            return redirect("custom_admin_courses")

        try:
            Course.objects.create(
                code=code, name=name, credits=credits, LTPC=ltpc, slot=slot
            )
            messages.success(request, "Course added successfully.")
        except IntegrityError as e:
            messages.error(request, f"Could not add course: {e}")
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect("custom_admin_courses")

    return render(request, "admin/custom_admin_courses.html", {
        "courses": courses,
        "slot_choices": slot_choices,
    })

def custom_admin_courses_bulk(request):
    if request.method == "POST":
        course_file = request.FILES.get("course_file")
        if not course_file:
            messages.error(request, "Please upload a CSV or Excel file.")
            return redirect("custom_admin_courses_bulk")

        temp_file_path = default_storage.save(f"temp/{course_file.name}", course_file)
        added_count = 0
        error_rows = []

        try:
            ext = course_file.name.split('.')[-1].lower()
            if ext == 'csv':
                with default_storage.open(temp_file_path, mode='r') as file:
                    reader = csv.DictReader(file)
                    rows = list(reader)
            elif ext in ['xls', 'xlsx']:
                with default_storage.open(temp_file_path, 'rb') as f:
                    df = pd.read_excel(f)
                rows = df.to_dict(orient='records')
            else:
                messages.error(request, "Unsupported file format. Upload CSV or Excel.")
                return redirect("custom_admin_courses_bulk")

            valid_slots = {val for val, _ in Course.SLOT_CHOICES}

            def safe_str(val):
                return '' if val is None else str(val).strip()

            for idx, row in enumerate(rows, start=2):  # header = 1, data starts at 2
                code = safe_str(row.get('Course Code')).upper()
                name = safe_str(row.get('Course Name'))
                status = safe_str(row.get('Status in course booklet')) or 'Yes'
                ltpc = safe_str(row.get('L-T-P-C')).upper()
                slot = safe_str(row.get('Slot')).upper()
                credit_val = row.get('Credit')
                try:
                    credits = int(float(credit_val)) if credit_val not in [None, ''] else None
                except (ValueError, TypeError):
                    credits = None

                if not (code and name and slot and credits is not None):
                    error_rows.append(f"Row {idx}: Missing required fields.")
                    continue
                if slot not in valid_slots:
                    error_rows.append(f"Row {idx}: Invalid slot '{slot}'.")
                    continue

                try:
                    course, created = Course.objects.get_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'status': status,
                            'LTPC': ltpc,
                            'slot': slot,
                            'credits': credits,
                        }
                    )
                    if created:
                        added_count += 1
                    else:
                        # Uncomment below to update existing course info if needed
                        # course.name = name
                        # course.status = status
                        # course.LTPC = ltpc
                        # course.slot = slot
                        # course.credits = credits
                        # course.save()
                        pass
                except IntegrityError:
                    error_rows.append(f"Row {idx}: Course with code '{code}' already exists.")
                except Exception as e:
                    error_rows.append(f"Row {idx}: Error saving course - {str(e)}")

        except Exception as e:
            messages.error(request, f"Failed to process file: {str(e)}")
            default_storage.delete(temp_file_path)
            return redirect("custom_admin_courses_bulk")

        default_storage.delete(temp_file_path)

        if added_count:
            messages.success(request, f"Successfully added {added_count} new courses.")
        for err in error_rows:
            messages.error(request, err)
        return redirect("custom_admin_courses_bulk")

    return render(request, "admin/bulk_add_courses.html")



def custom_admin_edit_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    slot_choices = Course.SLOT_CHOICES

    if request.method == "POST":
        course.code = request.POST.get("code", "").strip().upper()
        course.name = request.POST.get("name", "").strip()
        credits = request.POST.get("credits")
        course.LTPC = request.POST.get("LTPC", "").strip().upper()
        course.slot = request.POST.get("slot")

        try:
            course.credits = int(credits)
        except (TypeError, ValueError):
            messages.error(request, "Credits must be an integer.")
            return redirect("custom_admin_edit_course", course_id=course.id)

        try:
            course.save()
            messages.success(request, "Course updated successfully.")
            return redirect("custom_admin_courses")
        except IntegrityError as e:
            messages.error(request, f"Could not update course: {e}")
        except Exception as e:
            messages.error(request, f"Error: {e}")

    return render(request, "admin/custom_admin_edit_course.html", {
        "course": course,
        "slot_choices": slot_choices,
    })


from django.views.decorators.http import require_POST
@require_POST
def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    try:
        course.delete()
        messages.success(request, "Course deleted.")
    except Exception as e:
        messages.error(request, f"Could not delete: {e}")
    return redirect("custom_admin_courses")


def manage_course_faculties(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    faculties = Faculty.objects.select_related("department").order_by("last_name", "first_name")

    if request.method == "POST":
        selected_ids = request.POST.getlist("faculty_ids")  # list of strings
        # Replace all current assignments with selected ones
        try:
            # Ensure integers
            faculty_pks = [int(pk) for pk in selected_ids]
            course.faculties.set(faculty_pks)  # ManyToMany replace
            course.save()
            messages.success(request, "Faculties updated for this course.")
        except Exception as e:
            messages.error(request, f"Could not update faculties: {e}")
        return redirect("course_instructors_assign")

    assigned_ids = set(course.faculties.values_list("id", flat=True))
    return render(request, "admin/custom_admin_course_faculties.html", {
        "course": course,
        "faculties": faculties,
        "assigned_ids": assigned_ids,
    })


def course_branch_index(request):
    courses = Course.objects.all().order_by("code")
    return render(request, "admin/course_branch_index.html", {
        "courses": courses,
    })

@transaction.atomic
def manage_course_branches(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    categories = Category.objects.order_by("code")
    branches = Branch.objects.select_related("department").order_by("name")

    if request.method == "POST":
        for br in branches:
            ids = request.POST.getlist(f"category_{br.id}[]")
            cb, _ = CourseBranch.objects.get_or_create(course=course, branch=br)
            qs = Category.objects.filter(id__in=ids)
            cb.categories.set(qs) if ids else cb.categories.clear()
        return redirect("course_branch_index")

    # Build preselected sets from DB for this course
    cb_for_course = CourseBranch.objects.filter(course=course).prefetch_related("categories")
    selected_map = {
        cb.branch_id: set(cb.categories.values_list("id", flat=True))
        for cb in cb_for_course
    }
    for br in branches:
        br.selected_category_ids = selected_map.get(br.id, set())

    return render(
        request,
        "admin/custom_admin_course_branches.html",
        {"course": course, "branches": branches, "categories": categories},
    )


def bulk_upload_course_branch(request):
    if request.method == "POST":
        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"ok": False, "message": "Please upload a CSV or Excel file.", "errors": []}, status=400)

        temp_path = default_storage.save(f"temp/{upload.name}", upload)
        errors = []
        applied_links = 0
        rows_processed = 0

        try:
            ext = upload.name.split(".")[-1].lower()
            if ext == "csv":
                with default_storage.open(temp_path, mode="r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            elif ext in ["xls", "xlsx"]:
                with default_storage.open(temp_path, "rb") as f:
                    df = pd.read_excel(f, engine="openpyxl")
                rows = df.to_dict(orient="records")
            else:
                return JsonResponse({"ok": False, "message": "Unsupported file format. Upload CSV or Excel.", "errors": []}, status=400)

            if not rows:
                return JsonResponse({"ok": False, "message": "The uploaded file has no data rows.", "errors": []}, status=400)

            headers = set(rows[0].keys())
            must_have = {"Course Code", "Course Name"}
            missing = [h for h in must_have if h not in headers]
            if missing:
                return JsonResponse({"ok": False, "message": "Invalid header row.", "errors": [f"Missing required columns: {', '.join(missing)}"]}, status=400)
            if not any(h in headers for h in CATEGORY_HEADERS):
                return JsonResponse({"ok": False, "message": "No category columns present.", "errors": [f"Provide any of: {', '.join(CATEGORY_HEADERS)}"]}, status=400)

            # Preload references
            branches = list(Branch.objects.all())
            branches_by_code = {b.name.strip().upper(): b for b in branches}  # Branch.name holds the code
            all_branches = branches  # for ALL token
            categories_by_code = {c.code.strip().upper(): c for c in Category.objects.all()}
            missing_cats = [h for h in CATEGORY_HEADERS if h not in categories_by_code]
            if missing_cats:
                return JsonResponse({"ok": False, "message": "Missing Category rows in DB.", "errors": [f"Create Category for codes: {', '.join(missing_cats)}"]}, status=400)

            with transaction.atomic():
                for rix, row in enumerate(rows, start=2):
                    code = _safe_str(row.get("Course Code")).upper()
                    name = _safe_str(row.get("Course Name"))

                    if not code and not name:
                        errors.append(f"Row {rix}: Both Course Code and Course Name are empty; skipped.")
                        continue

                    course = None
                    if code:
                        course = Course.objects.filter(code__iexact=code).first()
                    if course is None and name:
                        course = Course.objects.filter(name__iexact=name).first()

                    if course is None:
                        errors.append(f"Row {rix}: Course not found by code '{code}' or name '{name}'. Skipped.")
                        continue

                    rows_processed += 1

                    # Process each category column
                    for header in CATEGORY_HEADERS:
                        if header not in headers:
                            continue
                        cell = row.get(header)

                        # Skip blanks/NaN entirely
                        if _is_blank_or_nan(cell):
                            continue

                        tokens = _split_codes(cell)
                        # If the cell explicitly contains ALL (case-insensitive), apply to all branches
                        # Detect ALL even if mixed with other separators/tokens
                        has_all = any(tok.upper() == "ALL" for tok in (tokens if tokens else [_safe_str(cell).upper()]))

                        if has_all:
                            target_branches = all_branches
                        else:
                            # Use parsed codes; unknown codes are reported individually
                            target_branches = []
                            for br_code in tokens:
                                if br_code == "ALL":
                                    # Already handled by has_all; skip here
                                    continue
                                br = branches_by_code.get(br_code)
                                if not br:
                                    errors.append(f"Row {rix}: Unknown Branch Code '{br_code}' in column '{header}'.")
                                    continue
                                target_branches.append(br)

                        if not target_branches:
                            continue  # nothing to do for this cell

                        cat = categories_by_code[HEADER_TO_CATEGORY[header]]

                        for br in target_branches:
                            cb, _ = CourseBranch.objects.get_or_create(course=course, branch=br)
                            # Add category if missing; never remove others
                            if not cb.categories.filter(id=cat.id).exists():
                                cb.categories.add(cat)
                                applied_links += 1

            return JsonResponse({
                "ok": True,
                "message": "Processed file.",
                "rows": rows_processed,
                "links_added": applied_links,
                "errors": errors[:100],
            }, status=200)

        except Exception as e:
            return JsonResponse({
                "ok": False,
                "message": f"Failed to process file: {str(e)}",
                "errors": errors[:100]
            }, status=500)
        finally:
            try:
                default_storage.delete(temp_path)
            except Exception:
                pass

    # GET
    return render(request, "admin/bulk_upload_course_branches.html")

def requirements_index(request):
    branches = Branch.objects.select_related("department").order_by("department__code", "name")
    return render(request, "admin/requirements_index.html", {"branches": branches})

def manage_branch_requirements(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    categories = ProgramRequirement.CATEGORY_CHOICES

    # map: category -> required
    existing = {
        r.category: r.required_credits for r in ProgramRequirement.objects.filter(branch=branch)
    }

    if request.method == "POST":
        try:
            with transaction.atomic():
                for cat, _label in categories:
                    req_val = request.POST.get(f"{cat}_req", "").strip()
                    if req_val == "":
                        # Treat blank as 0 to keep it simple; adjust if you prefer to delete rows when blank
                        req_i = 0
                    else:
                        try:
                            req_i = int(req_val)
                        except ValueError:
                            raise ValueError(f"{cat}: required must be an integer.")
                        if req_i < 0:
                            raise ValueError(f"{cat}: required cannot be negative.")

                    ProgramRequirement.objects.update_or_create(
                        branch=branch,
                        category=cat,
                        defaults={"required_credits": req_i},
                    )
            messages.success(request, "Requirements saved.")
        except Exception as e:
            messages.error(request, f"Could not save: {e}")
        return redirect("manage_branch_requirements", branch_id=branch.id)

    # Build rows for template
    rows = []
    for cat, label in categories:
        req_i = existing.get(cat, 0)
        rows.append({"cat": cat, "label": label, "req": req_i})

    return render(request, "admin/manage_branch_requirements.html", {
        "branch": branch,
        "rows": rows,
    })


def bulk_upload_program_requirements(request):
    if request.method == "POST":
        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({
                "ok": False,
                "message": "Please upload a CSV or Excel file.",
                "errors": []
            }, status=400)

        temp_file_path = default_storage.save(f"temp/{upload.name}", upload)
        created_count = 0
        updated_count = 0
        error_rows = []

        try:
            # Read rows
            ext = upload.name.split(".")[-1].lower()
            if ext == "csv":
                with default_storage.open(temp_file_path, mode="r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            elif ext in ["xls", "xlsx"]:
                with default_storage.open(temp_file_path, "rb") as f:
                    # Use openpyxl for .xlsx
                    df = pd.read_excel(f, engine="openpyxl")
                rows = df.to_dict(orient="records")
            else:
                return JsonResponse({
                    "ok": False,
                    "message": "Unsupported file format. Upload CSV or Excel.",
                    "errors": []
                }, status=400)

            # Guard: no data
            if not rows:
                return JsonResponse({
                    "ok": False,
                    "message": "The uploaded file contains no data rows.",
                    "errors": []
                }, status=400)

            # Header validation
            headers = set(rows[0].keys())
            required_headers = {"Branch Code"} | set(CATEGORY_MAP.keys())
            missing = [h for h in required_headers if h not in headers]
            if missing:
                return JsonResponse({
                    "ok": False,
                    "message": "Missing required columns.",
                    "errors": [f"Missing required columns: {', '.join(missing)}"]
                }, status=400)

            # Preload Branch by code.
            # IMPORTANT: Branch.name stores the code (choices), e.g., "CSE", "DSE", etc.
            branch_by_code = {b.name.strip().upper(): b for b in Branch.objects.all()}

            # Existing ProgramRequirement map
            existing = {
                (pr.branch_id, pr.category): pr
                for pr in ProgramRequirement.objects.all().only("id", "branch_id", "category", "required_credits")
            }

            def parse_int(val):
                if val is None:
                    return None
                s = str(val).strip()
                if s == "" or s.lower() in ("nan", "none"):
                    return None
                try:
                    return int(float(s))
                except Exception:
                    return None

            to_create = []
            to_update = []

            for idx, row in enumerate(rows, start=2):  # header row = 1
                branch_code = str(row.get("Branch Code", "")).strip().upper()
                if not branch_code:
                    error_rows.append(f"Row {idx}: Missing Branch Code.")
                    continue
                branch = branch_by_code.get(branch_code)
                if not branch:
                    error_rows.append(f"Row {idx}: Unknown Branch Code '{branch_code}'.")
                    continue

                any_valid = False
                for header_key, category_code in CATEGORY_MAP.items():
                    credits = parse_int(row.get(header_key))
                    if credits is None:
                        continue  # blank/invalid => no change
                    any_valid = True
                    key = (branch.id, category_code)
                    pr = existing.get(key)
                    if pr:
                        if pr.required_credits != credits:
                            pr.required_credits = credits
                            to_update.append(pr)
                    else:
                        to_create.append(ProgramRequirement(
                            branch=branch,
                            category=category_code,
                            required_credits=credits,
                        ))

                if not any_valid:
                    error_rows.append(f"Row {idx}: No valid integer credits for any category; row skipped.")

            # Apply DB changes atomically
            with transaction.atomic():
                if to_create:
                    ProgramRequirement.objects.bulk_create(to_create, batch_size=1000)
                    created_count = len(to_create)
                if to_update:
                    ProgramRequirement.objects.bulk_update(to_update, ["required_credits"], batch_size=1000)
                    updated_count = len(to_update)

            return JsonResponse({
                "ok": True,
                "created": created_count,
                "updated": updated_count,
                "errors": error_rows[:50],  # cap to avoid huge payloads
            }, status=200)

        except Exception as e:
            return JsonResponse({
                "ok": False,
                "message": f"Failed to process file: {str(e)}",
                "errors": error_rows[:50] if error_rows else []
            }, status=500)
        finally:
            try:
                default_storage.delete(temp_file_path)
            except Exception:
                # Silent cleanup failure
                pass

    # GET: render page
    return render(request, "admin/bulk_upload_program_requirements.html")


def course_instructors_assign(request):
    courses = (
        Course.objects
        .all()
        .prefetch_related("faculties__department")
        .order_by("code")
    )

    # Build mapping of course.id to list of mini faculty objects (first_name, last_name, email, department name)
    course_faculty_map: dict[int, list[FacultyMini]] = defaultdict(list)
    for course in courses:
        for f in course.faculties.all():
            dept_name = f.department.name if f.department else "—"
            course_faculty_map[course.id].append(
                FacultyMini(
                    first_name=f.first_name,
                    last_name=f.last_name or "",
                    email_id=f.email_id,
                    department=dept_name,
                )
            )

    # Filters for dropdowns
    departments = (
        Department.objects
        .order_by("name")
        .values_list("name", flat=True)
        .distinct()
    )
    slots = (
        Course.objects
        .order_by()
        .values_list("slot", flat=True)
        .distinct()
    )

    return render(
        request,
        "admin/course_instructors_assign.html",  # use the template you created for this page
        {
            "courses": courses,
            "course_faculty_map": course_faculty_map,
            "departments": departments,
            "slots": slots,
        },
    )

def course_instructors_assign_bulk(request):
    if request.method == "POST":
        upload = request.FILES.get("csv_file")
        if not upload:
            return JsonResponse({"ok": False, "message": "Please upload a CSV or Excel file.", "errors": []}, status=400)

        # Optional controls provided by the form
        conflict = (request.POST.get("conflict_policy") or "append").strip().lower()
        validation = (request.POST.get("validation_level") or "strict").strip().lower()
        if conflict not in {"append", "replace"}:
            conflict = "append"
        if validation not in {"strict", "lenient"}:
            validation = "strict"

        temp_path = default_storage.save(f"temp/{upload.name}", upload)
        errors = []
        links_added = 0
        rows_processed = 0

        try:
            ext = upload.name.split(".")[-1].lower()
            # Load rows as a list of dicts with keys 'course_code' and 'faculty_email'
            if ext == "csv":
                with default_storage.open(temp_path, mode="r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            elif ext in ["xls", "xlsx"]:
                with default_storage.open(temp_path, "rb") as f:
                    df = pd.read_excel(f, engine="openpyxl")
                rows = df.to_dict(orient="records")
            else:
                return JsonResponse(
                    {"ok": False, "message": "Unsupported file format. Upload CSV or Excel.", "errors": []},
                    status=400
                )

            if not rows:
                return JsonResponse({"ok": False, "message": "The uploaded file has no data rows.", "errors": []}, status=400)

            # Header validation (case-insensitive normalize)
            sample_keys = {str(k).strip().lower() for k in rows[0].keys()}
            need = {"course_code", "faculty_email"}
            missing = [h for h in need if h not in sample_keys]
            if missing:
                return JsonResponse(
                    {"ok": False, "message": "Invalid header row.", "errors": [f"Missing required columns: {', '.join(need)}"]},
                    status=400
                )

            # Normalize keys to lower for consistent access
            norm_rows = []
            for r in rows:
                norm = {str(k).strip().lower(): v for k, v in r.items()}
                norm_rows.append(norm)

            # Preload references
            codes = set()
            emails = set()
            for rix, row in enumerate(norm_rows, start=2):
                code = str(row.get("course_code") or "").strip()
                email = str(row.get("faculty_email") or "").strip()
                if not code or not email:
                    msg = f"Row {rix}: empty course_code or faculty_email; skipped."
                    if validation == "strict":
                        return JsonResponse({"ok": False, "message": msg, "errors": errors}, status=400)
                    errors.append(msg)
                    continue
                codes.add(code)
                emails.add(email)

            course_by_code = {c.code: c for c in Course.objects.filter(code__in=codes)}
            faculty_by_email = {f.email_id: f for f in Faculty.objects.filter(email_id__in=emails)}

            with transaction.atomic():
                # Replace clears once per course before applying rows
                if conflict == "replace":
                    for code in sorted(codes):
                        course = course_by_code.get(code)
                        if not course:
                            msg = f"Unknown course: {code}"
                            if validation == "strict":
                                return JsonResponse({"ok": False, "message": msg, "errors": errors}, status=400)
                            errors.append(msg)
                            continue
                        course.faculties.clear()

                # Apply rows
                for rix, row in enumerate(norm_rows, start=2):
                    code = str(row.get("course_code") or "").strip()
                    email = str(row.get("faculty_email") or "").strip()
                    if not code or not email:
                        # already recorded earlier when collecting codes/emails
                        continue

                    course = course_by_code.get(code)
                    if not course:
                        msg = f"Row {rix}: Unknown course: {code}"
                        if validation == "strict":
                            return JsonResponse({"ok": False, "message": msg, "errors": errors}, status=400)
                        errors.append(msg)
                        continue

                    faculty = faculty_by_email.get(email)
                    if not faculty:
                        msg = f"Row {rix}: Unknown faculty: {email}"
                        if validation == "strict":
                            return JsonResponse({"ok": False, "message": msg, "errors": errors}, status=400)
                        errors.append(msg)
                        continue

                    rows_processed += 1
                    if not course.faculties.filter(pk=faculty.pk).exists():
                        course.faculties.add(faculty)
                        links_added += 1

            return JsonResponse({
                "ok": True,
                "message": "Processed file.",
                "rows": rows_processed,
                "links_added": links_added,
                "errors": errors[:100],
            }, status=200)

        except Exception as e:
            return JsonResponse({
                "ok": False,
                "message": f"Failed to process file: {str(e)}",
                "errors": errors[:100]
            }, status=500)
        finally:
            try:
                default_storage.delete(temp_path)
            except Exception:
                pass

    # GET
    return render(request, "admin/bulk_add_course_instructors.html")



@require_POST
def submit_preregistration(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    student = get_object_or_404(Student, roll_no=roll_no)
    payload_raw = request.POST.get("payload", "")
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except Exception:
        messages.error(request, "Invalid submission payload.")
        return redirect("prereg_page")

    semester = payload.get("semester")
    try:
        semester = int(semester)
    except Exception:
        messages.error(request, "Select a valid semester.")
        return redirect("prereg_page")

    selections = payload.get("selections") or []
    if not isinstance(selections, list):
        messages.error(request, "Invalid selections.")
        return redirect("prereg_page")

    # Build a map from course_code to Course
    codes = [s.get("course_code","").strip().upper() for s in selections if s.get("course_code")]
    codes = [c for c in codes if c]
    if not codes:
        messages.error(request, "Select at least one course.")
        return redirect("prereg_page")

    courses = {c.code.upper(): c for c in Course.objects.filter(code__in=codes)}
    missing = [c for c in codes if c not in courses]
    if missing:
        messages.error(request, f"Unknown courses: {', '.join(missing)}")
        return redirect("prereg_page")

    # Validate credit bounds server-side as well
    total_credits = sum(int(selections[i].get("credits") or 0) for i in range(len(selections)))
    if total_credits < (request.GET.get("min_credit") or 0):
        # front-end already enforces; server trust existing min/max from context if desired
        pass

    created, skipped = 0, 0
    with transaction.atomic():
        for sel in selections:
            code = (sel.get("course_code") or "").strip().upper()
            if not code:
                continue
            course = courses.get(code)
            # PND = pending request
            obj, is_created = StudentCourse.objects.get_or_create(
                student=student, course=course, semester=semester,
                defaults={
                    "status": "PND",
                    "is_pass_fail": bool(sel.get("is_pass_fail") or False),
                    "type": sel.get("category") or None,
                }
            )
            if not is_created:
                # If already exists but not enrolled, keep it pending to allow resubmission window
                if obj.status in ("DRP",):
                    obj.status = "PND"
                    obj.is_pass_fail = bool(sel.get("is_pass_fail") or False)
                    obj.type = sel.get("category") or None
                    obj.save(update_fields=["status", "is_pass_fail", "type"])
                skipped += 1
            else:
                created += 1

    if created:
        messages.success(request, f"Submitted {created} request(s) for approval.")
    if skipped:
        messages.info(request, f"{skipped} existing request(s) retained.")
    return redirect("check_status_page")


##Should be changed -- Faculty Advisor
@require_POST
def advisor_request_action(request):
    # Assume Admins act as advisors; refine later to advisor mapping
    admin_email = request.session.get("email_id")
    if not admin_email or not Admins.objects.filter(email_id=admin_email).exists():
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    sc_id = request.POST.get("sc_id")
    action = (request.POST.get("action") or "").lower()

    sc = get_object_or_404(StudentCourse, id=sc_id)

    if sc.status != "INS":
        messages.info(request, "Request not ready for advisor approval.")
        return redirect("custom_admin_home")

    if action == "approve":
        sc.status = "ENR"
        sc.outcome = "UNK"
        sc.save(update_fields=["status", "outcome"])
        messages.success(request, "Student enrolled for this course.")
    elif action == "reject":
        sc.status = "DRP"
        sc.save(update_fields=["status"])
        messages.success(request, "Request rejected.")
    else:
        messages.error(request, "Unknown action.")
    return redirect("custom_admin_home")


def _compute_semester_from_roll_and_today(roll_no: str, today=None) -> int:
    if today is None:
        today = timezone.now().date()
    try:
        yr2 = int(roll_no[1:3])
        admit_year = 2000 + yr2
    except Exception:
        return 1
    years_delta = max(0, today.year - admit_year)
    term_index = 1 if today.month >= 7 else 2
    return max(1, years_delta * 2 + term_index)

def instructor_requests(request):
    email_id = request.session.get("email_id")
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    instructor = get_object_or_404(Faculty, email_id=email_id)

    status_filter = request.GET.get("status", "PND")
    course_code = (request.GET.get("course") or "").strip().upper()
    slot = (request.GET.get("slot") or "").strip().upper()

    qs = (
        StudentCourse.objects
        .filter(course__faculties__email_id=email_id)
        .select_related("course","student")
        .prefetch_related("course__faculties")
        .order_by("course__code","student__roll_no")
        .distinct()
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if course_code:
        qs = qs.filter(course__code=course_code)
    if slot:
        qs = qs.filter(course__slot=slot)

    # Get unique slots for filter
    slots = Course.objects.filter(faculties__email_id=email_id).values_list('slot', flat=True).distinct()

    # Model-agnostic my_courses
    my_courses = (
        Course.objects.filter(faculties__email_id=email_id)
        .order_by("code")
        .values_list("code","name","slot")
    )

    context = {
        "instructor": instructor,
        "requests": qs,
        "status_filter": status_filter,
        "course_code": course_code,
        "slot_filter": slot,
        "slots": slots,
        "my_courses": my_courses,
    }
    return render(request, "instructor/instructor_requests.html", context)


@require_POST
def instructor_request_action(request):
    email_id = request.session.get("email_id")
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    faculty = get_object_or_404(Faculty, email_id=email_id)

    sc_id = request.POST.get("sc_id")
    action = (request.POST.get("action") or "").lower()

    if not sc_id:
        messages.error(request, "No request selected.")
        return redirect("instructor_requests")

    sc = get_object_or_404(
        StudentCourse.objects.select_related("course", "student"),
        id=sc_id
    )

    # Ownership guard
    if not sc.course.faculties.filter(id=faculty.id).exists():
        messages.error(request, "Not authorized for this course.")
        return redirect("instructor_requests")

    # Only pending can change
    if sc.status != "PND":
        messages.info(request, "Request is not pending.")
        return redirect("instructor_requests")

    # Apply single action
    if action == "approve":
        sc.status = "ENR"
    elif action == "reject":
        sc.status = "DRP"
    else:
        messages.error(request, "Unknown action.")
        return redirect("instructor_requests")

    sc.save(update_fields=["status"])
    messages.success(request, f"Request {action}ed.")
    return redirect("instructor_requests")


@require_POST
def instructor_bulk_action(request):
    email_id = request.session.get("email_id")
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    faculty = get_object_or_404(Faculty, email_id=email_id)

    ids = request.POST.getlist("sc_ids")
    action = (request.POST.get("action") or "").lower()

    if not ids:
        messages.info(request, "No requests selected.")
        return redirect("instructor_requests")

    if action not in ("approve", "reject"):
        messages.error(request, "Unknown action.")
        return redirect("instructor_requests")

    qs = StudentCourse.objects.filter(id__in=ids).select_related("course", "student")
    updated = 0
    for sc in qs:
        if not sc.course.faculties.filter(id=faculty.id).exists():
            continue
        if sc.status != "PND":
            continue
        sc.status = "ENR" if action == "approve" else "DRP"
        sc.save(update_fields=["status"])
        updated += 1

    messages.success(request, f"{updated} request(s) {action}d.")
    return redirect("instructor_requests")

def instructor_courses(request):
    # Authn: get instructor
    email_id = request.session.get("email_id")
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")
    instructor = get_object_or_404(Faculty, email_id=email_id)

    # Optional semester label to display and use as default in links
    current_sem = _compute_semester_from_roll_and_today(instructor.email_id)

    # All courses this instructor teaches (ever), with total enrolled across all semesters
    courses = (
        Course.objects.filter(faculties=instructor)
        .distinct()
        .annotate(
            total_enrolled=Count("enrollments", filter=Q(enrollments__status="ENR"))
        )
        .order_by("code")
    )

    context = {
        "instructor": instructor,
        "courses": courses,
        "default_semester": str(current_sem),  # used in roster links
    }
    return render(request, "instructor/view_courses.html", context)


def course_roster(request, course_code, semester=None):
    # Auth
    email_id = request.session.get("email_id")
    if not email_id:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    instructor = get_object_or_404(Faculty, email_id=email_id)

    # Course ownership
    course = get_object_or_404(Course.objects.prefetch_related("faculties"), code=course_code)
    if not course.faculties.filter(id=instructor.id).exists():
        return redirect("instructor_courses")

    # Search text
    q = (request.GET.get("q") or request.POST.get("q") or "").strip()

    # POST actions: add student, remove student, attendance
    if request.method == "POST":
        action = (request.POST.get("action") or "").lower()

        if action == "add_student":
            roll_no = (request.POST.get("roll_no") or "").strip().lower()
            raw_sem = (request.POST.get("add_semester") or "").strip()
            if not roll_no:
                messages.error(request, "Roll number is required.")
            else:
                student = Student.objects.filter(roll_no__iexact=roll_no).first()
                if not student:
                    messages.error(request, "Student not found.")
                else:
                    # still set semester on enrollment to satisfy model constraint, but do not use it for display
                    try:
                        sem_val = int(raw_sem) if raw_sem else _compute_semester_from_roll_and_today(student.roll_no)
                    except Exception:
                        sem_val = _compute_semester_from_roll_and_today(student.roll_no)
                    with transaction.atomic():
                        obj, created = StudentCourse.objects.get_or_create(
                            student=student,
                            course=course,
                            semester=sem_val,
                            defaults={"status": "ENR", "is_pass_fail": False},
                        )
                        if created:
                            messages.success(request, f"Enrolled {student.roll_no} in {course.code}.")
                        else:
                            if obj.status != "ENR":
                                obj.status = "ENR"
                                obj.save(update_fields=["status"])
                                messages.success(request, f"Updated {student.roll_no} to ENR in {course.code}.")
                            else:
                                messages.info(request, f"{student.roll_no} is already enrolled in {course.code}.")
            # Redirect to same page, preserve search
            return redirect(f"{request.path}{'?q='+q if q else ''}")

        if action == "remove_student":
            sc_id = request.POST.get("sc_id")
            try:
                sc_id_int = int(sc_id)
            except (TypeError, ValueError):
                sc_id_int = None
            if not sc_id_int:
                messages.error(request, "Invalid selection.")
            else:
                with transaction.atomic():
                    sc = StudentCourse.objects.filter(id=sc_id_int, course=course, status="ENR").first()
                    if not sc:
                        messages.info(request, "No matching enrolled record found.")
                    else:
                        rid = sc.student.roll_no
                        sc.delete()
                        messages.success(request, f"Removed {rid} from {course.code}.")
            return redirect(f"{request.path}{'?q='+q if q else ''}")


        messages.error(request, "Unknown action.")
        return redirect(f"{request.path}{'?q='+q if q else ''}")

    # GET: all enrolled rows for this course, no semester filter or sort by semester
    enrollments_qs = (
        StudentCourse.objects
        .filter(course__code=course_code, status="ENR")
        .select_related("student", "course")
    )
    if q:
        enrollments_qs = enrollments_qs.filter(
            Q(student__roll_no__icontains=q) |
            Q(student__first_name__icontains=q) |
            Q(student__last_name__icontains=q)
        )
    enrollments_qs = enrollments_qs.order_by("student__roll_no")

    # Compute dynamic semester for display only
    enrollments = []
    for sc in enrollments_qs:
        sc.computed_semester = _compute_semester_from_roll_and_today(sc.student.roll_no)
        enrollments.append(sc)

    context = {
        "instructor": instructor,
        "course": course,
        "enrollments": enrollments,
        "q": q,
    }
    return render(request, "instructor/course_roster.html", context)


def custom_admin_preregistration(request):
    return render(request, "admin/preregistration.html")


def admin_prereg_deadline(request):
    # Read current deadline for display
    current_deadline = getattr(settings, "PREREG_DEADLINE", None)
    current_local_iso = ""
    if current_deadline:
        aware = current_deadline
        if timezone.is_naive(aware):
            aware = timezone.make_aware(aware, timezone.get_current_timezone())
        local = timezone.localtime(aware, timezone.get_current_timezone())
        current_local_iso = local.strftime("%Y-%m-%dT%H:%M")

    # Read current temporary override (None => follow deadline)
    temp_state = getattr(settings, TEMP_PREREG_OPEN_FLAG, None)  # True/False/None

    if request.method == "POST":
        # Two possible forms submit to this same endpoint:
        # 1) action=open/close/clear for temporary override
        # 2) deadline=... for deadline updates
        action = (request.POST.get("action") or "").lower()

        if action in {"open", "close", "clear"}:
            if action == "open":
                settings.PREREG_TEMP_OPEN = True
                messages.success(request, "Pre‑registration temporarily set to OPEN.")  # [web:647]
            elif action == "close":
                settings.PREREG_TEMP_OPEN = False
                messages.warning(request, "Pre‑registration temporarily set to CLOSED.")  # [web:647]
            else:
                settings.PREREG_TEMP_OPEN = None
                messages.info(request, "Temporary override cleared. Deadline rule applies.")  # [web:647]
            return redirect("admin_prereg_deadline")

        # Otherwise treat as deadline update (may be empty to clear)
        raw = (request.POST.get("deadline") or "").strip()
        if raw == "":
            settings.PREREG_DEADLINE = None
            messages.info(request, "Deadline cleared. Window will follow temporary override or remain open if none.")  # [web:647]
            return redirect("admin_prereg_deadline")

        naive = parse_datetime(raw)  # "YYYY-MM-DDTHH:MM"
        if not naive:
            messages.error(request, "Invalid date/time format for deadline.")  # [web:647]
            return redirect("admin_prereg_deadline")

        aware = naive
        if timezone.is_naive(aware):
            aware = timezone.make_aware(aware, timezone.get_current_timezone())  # [web:607]
        settings.PREREG_DEADLINE = aware  # runtime assignment [web:635]
        local_disp = timezone.localtime(aware).strftime("%Y-%m-%d %H:%M %Z")
        messages.success(request, f"Deadline set to {local_disp}.")  # [web:647]
        return redirect("admin_prereg_deadline")

    ctx = {
        "current_local_iso": current_local_iso,
        "temp_state": temp_state,  # True / False / None
    }
    return render(request, "admin/prereg_deadline.html", ctx)


def admin_prereg_enrollments(request):
    # GET filters
    q = (request.GET.get("q") or "").strip()
    code = (request.GET.get("course") or "").strip().upper()

    courses_qs = Course.objects.all().order_by("slot", "code")
    if q:
        courses_qs = courses_qs.filter(Q(code__icontains=q) | Q(name__icontains=q))

    slot = (request.GET.get("slot") or "").strip().upper()
    if slot:
        courses_qs = courses_qs.filter(slot=slot)

    # no slicing here
    courses = list(courses_qs)

    selected_course = None
    enrolled = []
    current_sem = None

    if code:
        selected_course = Course.objects.filter(code__iexact=code).first()
        if selected_course:
            # If admin provided ?sem=, show that semester; otherwise show ALL semesters
            sem_param = request.GET.get("sem")
            if sem_param and sem_param.isdigit():
                current_sem = int(sem_param)
                enrolled = (
                    StudentCourse.objects
                    .filter(course=selected_course, semester=current_sem)
                    .select_related("student")
                    .order_by("student__roll_no")
                )
            else:
                current_sem = None  # indicate "All"
                enrolled = (
                    StudentCourse.objects
                    .filter(course=selected_course)
                    .select_related("student")
                    .order_by("semester", "student__roll_no")
                )

    # Helper: preserve prior GET params without forcing sem when it wasn't present
    def redirect_with(query_overrides: dict):
        base_params = {
            "q": q,
            "course": code,
            "slot": slot,
        }
        # Only carry sem forward if it existed in the incoming GET
        if "sem" in request.GET and request.GET.get("sem"):
            base_params["sem"] = request.GET.get("sem")
        # Apply explicit overrides (e.g., after add/remove we may want to include sem used to mutate)
        base_params.update({k: v for k, v in query_overrides.items() if v not in [None, ""]})
        return redirect(f"{request.path}?{urlencode({k: v for k, v in base_params.items() if v not in [None, '']})}")

    # Handle add/remove via POST regardless of deadline
    if request.method == "POST":
        action = (request.POST.get("action") or "").lower()
        target_code = (request.POST.get("course_code") or "").strip().upper()
        roll_no = (request.POST.get("roll_no") or "").strip().upper()
        sem = request.POST.get("semester")
        try:
            sem = int(sem) if sem else None
        except ValueError:
            sem = None

        if not target_code or not roll_no:
            messages.error(request, "Course code and roll number are required.")
            return redirect_with({})

        course = Course.objects.filter(code__iexact=target_code).first()
        if not course:
            messages.error(request, "Invalid course code.")
            return redirect_with({})

        student = Student.objects.filter(roll_no__iexact=roll_no).first()
        if not student:
            messages.error(request, "Student not found.")
            return redirect_with({})

        if sem is None:
            try:
                sem = _compute_semester_from_roll_and_today(student.roll_no)
            except Exception:
                agg = StudentCourse.objects.filter(course=course).aggregate(mx=Max("semester"))
                sem = agg["mx"] or 1

        with transaction.atomic():
            if action == "remove":
                deleted, _ = StudentCourse.objects.filter(
                    student=student, course=course, semester=sem
                ).delete()
                if deleted:
                    messages.success(request, f"Removed {roll_no} from {target_code} (Sem {sem}).")
                else:
                    messages.info(request, f"No enrollment found to remove for {roll_no} in {target_code} (Sem {sem}).")
                # Do NOT force sem into the redirect unless the user had chosen a sem
                return redirect_with({})

            if action == "add":
                obj, created = StudentCourse.objects.get_or_create(
                    student=student, course=course, semester=sem,
                    defaults={"status": "ENR", "is_pass_fail": False}
                )
                if not created:
                    if obj.status != "ENR":
                        obj.status = "ENR"
                        obj.save(update_fields=["status"])
                        messages.success(request, f"Updated {roll_no} to ENR in {target_code} (Sem {sem}).")
                    else:
                        messages.info(request, f"{roll_no} is already enrolled in {target_code} (Sem {sem}).")
                else:
                    messages.success(request, f"Enrolled {roll_no} in {target_code} (Sem {sem}).")
                return redirect_with({})

        messages.error(request, "Unknown action.")
        return redirect_with({})

    context = {
        "q": q,
        "courses": courses,              # pass full list
        "selected_course": selected_course,
        "enrolled": enrolled,
        "current_sem": current_sem,      # None => All
        "slot": slot,
    }
    return render(request, "admin/prereg_enrollments.html", context)


def admin_prereg_swap(request):
    # Filters for course directory (left panel)
    q = (request.GET.get("q") or "").strip()
    slot = (request.GET.get("slot") or "").strip().upper()

    courses_qs = Course.objects.all().order_by("slot", "code")
    if q:
        courses_qs = courses_qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    if slot:
        courses_qs = courses_qs.filter(slot=slot)

    # No slicing — show all matching courses
    courses = list(courses_qs)

    context = {
        "courses": courses,
        "q": q,
        "slot": slot,
    }

    if request.method != "POST":
        return render(request, "admin/prereg_swap.html", context)

    # POST: perform swap
    roll_no = (request.POST.get("roll_no") or "").strip().upper()
    from_code = (request.POST.get("from_code") or "").strip().upper()
    to_code = (request.POST.get("to_code") or "").strip().upper()
    sem_raw = (request.POST.get("semester") or "").strip()

    if not roll_no or not from_code or not to_code:
        messages.error(request, "Roll no, From course and To course are required.")
        return redirect("admin_prereg_swap")

    if from_code == to_code:
        messages.info(request, "From and To courses are identical; nothing to swap.")
        return redirect("admin_prereg_swap")

    try:
        sem = int(sem_raw) if sem_raw else None
    except ValueError:
        sem = None

    student = Student.objects.filter(roll_no__iexact=roll_no).first()
    if not student:
        messages.error(request, "Student not found.")
        return redirect("admin_prereg_swap")

    from_course = Course.objects.filter(code__iexact=from_code).first()
    to_course   = Course.objects.filter(code__iexact=to_code).first()
    if not from_course or not to_course:
        messages.error(request, "Invalid course code(s).")
        return redirect("admin_prereg_swap")

    if from_course.slot != to_course.slot:
        messages.error(request, f"Courses must be in the same slot (got {from_course.slot} vs {to_course.slot}).")
        return redirect("admin_prereg_swap")

    if sem is None:
        try:
            sem = _compute_semester_from_roll_and_today(student.roll_no)
        except Exception:
            sem = 1

    with transaction.atomic():
        enrolled_to = StudentCourse.objects.filter(student=student, course=to_course, semester=sem).first()
        enrolled_from = StudentCourse.objects.filter(student=student, course=from_course, semester=sem).first()

        if not enrolled_from and not enrolled_to:
            StudentCourse.objects.filter(
                student=student, semester=sem, course__slot=from_course.slot
            ).exclude(course=to_course).delete()

            StudentCourse.objects.get_or_create(
                student=student, course=to_course, semester=sem,
                defaults={"status": "ENR", "is_pass_fail": False}
            )
            messages.success(request, f"Enrolled {roll_no} to {to_code} (Sem {sem}).")
            return redirect("admin_prereg_swap")

        if enrolled_to and enrolled_from:
            enrolled_from.delete()
            if enrolled_to.status != "ENR":
                enrolled_to.status = "ENR"
                enrolled_to.save(update_fields=["status"])
            messages.success(request, f"Swapped {roll_no}: removed {from_code}, kept {to_code} (Sem {sem}).")
            return redirect("admin_prereg_swap")

        StudentCourse.objects.filter(
            student=student, semester=sem, course__slot=from_course.slot
        ).exclude(course=from_course).exclude(course=to_course).delete()

        if enrolled_from:
            enrolled_from.delete()

        to_obj, created = StudentCourse.objects.get_or_create(
            student=student, course=to_course, semester=sem,
            defaults={"status": "ENR", "is_pass_fail": False}
        )
        if not created and to_obj.status != "ENR":
            to_obj.status = "ENR"
            to_obj.save(update_fields=["status"])

        messages.success(request, f"Swapped {roll_no} from {from_code} to {to_code} (Sem {sem}).")
        return redirect("admin_prereg_swap")
    
def student_registered_courses(request):
    roll_no = request.session.get("roll_no")
    if not roll_no:
        login_url = getattr(settings, "LOGIN_URL", "/login/")
        return redirect(f"{login_url}?next={request.path}")

    student = get_object_or_404(Student, roll_no=roll_no)

    # Optional filters
    sem = (request.GET.get("sem") or "").strip()
    q = (request.GET.get("q") or "").strip()

    sc_qs = (
        StudentCourse.objects
        .filter(student=student, status="ENR")
        .select_related("course")
        .prefetch_related(Prefetch("course__faculties"))
        .order_by("semester", "course__slot", "course__code")
    )

    if sem.isdigit():
        sc_qs = sc_qs.filter(semester=int(sem))

    if q:
        sc_qs = sc_qs.filter(
            Q(course__code__icontains=q) |
            Q(course__name__icontains=q) |
            Q(course__slot__icontains=q)
        )

    # Build a small data list for the template
    items = []
    for sc in sc_qs:
        c = sc.course
        facs = getattr(c, "faculties", None)
        fac_names = []
        if facs:
            for f in facs.all():
                parts = [p for p in [f.first_name, f.last_name] if p]
                if parts:
                    fac_names.append(" ".join(parts))
        items.append({
            "semester": sc.semester,
            "code": c.code,
            "name": c.name,
            "slot": c.slot,
            "credits": c.credits,
            "ltpc": getattr(c, "LTPC", ""),
            "instructors": ", ".join(fac_names) if fac_names else "—",
        })

    context = {
        "student": student,
        "items": items,
        "q": q,
        "sem": sem,
    }
    return render(request, "registration/registered_course.html", context)


def admin_prereg_reports(request):
    q = (request.GET.get("q") or "").strip()
    slot = (request.GET.get("slot") or "").strip().upper()

    courses = Course.objects.all().order_by("slot","code")
    if q:
        courses = courses.filter(code__icontains=q) | courses.filter(name__icontains=q)
    if slot:
        courses = courses.filter(slot=slot)

    # Optionally prefetch for counts
    # enrolled_count can be computed on demand in template by querying ENR count
    return render(request, "admin/prereg_reports.html", {"courses": courses, "q": q, "slot": slot})

def export_course_excel(request, code):
    course = Course.objects.filter(code__iexact=code).first()
    if not course:
        raise Http404("Course not found")

    rows = (
        StudentCourse.objects
        .filter(course=course, status="ENR")
        .select_related("student")
        .order_by("student__roll_no", "semester")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Enrolled"
    ws.append(["Roll No", "Name", "Semester", "Status"])

    for sc in rows:
        s = sc.student
        full_name = f"{s.first_name or ''} {s.last_name or ''}".strip()
        ws.append([s.roll_no, full_name or "—", sc.semester, sc.status])

    fname = f"{slugify(course.code)}-enrolled.xlsx"
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    wb.save(resp)
    return resp  # [web:779][web:778]

def export_course_pdf(request, code):
    course = Course.objects.filter(code__iexact=code).first()
    if not course:
        raise Http404("Course not found")

    rows = (
        StudentCourse.objects
        .filter(course=course, status="ENR")
        .select_related("student")
        .order_by("semester", "student__roll_no")
    )

    html = render_to_string(
        "admin/prereg_course_pdf.html",
        {"course": course, "rows": rows}
    )
    pdf_bytes = HTML(string=html).write_pdf()  # optional: stylesheets=[CSS(...)] [web:782][web:792]
    fname = f"{slugify(course.code)}-enrolled.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp
# views.py (faculty, require faculty session)
from django.forms import modelformset_factory
from django.db.models import Sum

def require_faculty(view):
    def _w(request, *a, **k):
        if not request.session.get("email_id"):
            return redirect(f"{getattr(settings,'LOGIN_URL','/login/')}?next={request.path}")
        return view(request, *a, **k)
    return _w

def instructor_schema_courses(request):
    email_id = request.session["email_id"]
    instructor = get_object_or_404(Faculty, email_id=email_id)
    courses = (
        Course.objects.filter(faculties=instructor)
        .annotate(total_enrolled=Count("enrollments", filter=Q(enrollments__status="ENR")))
        .order_by("code")
        .distinct()
    )
    return render(request, "instructor/schema_courses.html", {
        "instructor": instructor,
        "courses": courses,
    })
# ----------------- Edit assessment scheme (no semester on component) -----------------

def edit_assessment_scheme(request, course_code):
    email = request.session["email_id"]
    faculty = get_object_or_404(Faculty, email_id=email)
    course = get_object_or_404(Course, code=course_code, faculties=faculty)

    ComponentFormSet = modelformset_factory(
        AssessmentComponent,
        fields=["name", "weight", "max_marks"],
        extra=0, can_delete=True
    )
    qs = AssessmentComponent.objects.filter(course=course).order_by("id")

    if request.method == "POST":
        # Add-only branch
        if request.POST.get("intent") == "add":
            add_name = (request.POST.get("add_name") or "").strip()
            add_weight = request.POST.get("add_weight")
            add_max = request.POST.get("add_max") or 100
            if not add_name or add_weight is None:
                messages.error(request, "Name and weight are required.")
                return redirect(request.path)
            AssessmentComponent.objects.update_or_create(
                course=course, name=add_name,
                defaults={"weight": add_weight, "max_marks": add_max},
            )
            messages.success(request, "Component added.")
            return redirect(request.path)

        # Save edits/deletes
        formset = ComponentFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            instances = formset.save(commit=False)

            # Delete marked-for-deletion
            for f in formset.deleted_forms:
                if f.instance.pk:
                    f.instance.delete()

            # Save updates/creates, attach course
            for inst in instances:
                inst.course = course
                inst.save()

            total_w = AssessmentComponent.objects.filter(course=course).aggregate(s=Sum("weight"))["s"] or 0
            if round(float(total_w), 2) != 100.0:
                messages.warning(request, f"Total weight is {total_w}, should be 100.")
            else:
                messages.success(request, "Assessment scheme saved.")
            return redirect(request.path)
        else:
            messages.error(request, "Please correct the errors.")
    else:
        formset = ComponentFormSet(queryset=qs)

    return render(request, "instructor/edit_assessment_schema.html", {
        "course": course,
        "formset": formset,
        "sample_headers": ["roll_no", "email"] + [c.name for c in qs],
    })

from decimal import Decimal, InvalidOperation

def _canon(s: str) -> str:
    return re.sub(r'[^a-z0-9]+','', (s or "").lower())

from django.views.decorators.http import require_POST

# ----------------- Update/delete single component -----------------

from django.views.decorators.http import require_POST

@require_POST
def update_component(request, course_code, component_id):
    email = request.session["email_id"]
    faculty = get_object_or_404(Faculty, email_id=email)
    course = get_object_or_404(Course, code=course_code, faculties=faculty)
    comp = get_object_or_404(AssessmentComponent, id=component_id, course=course)
    name = (request.POST.get("name") or "").strip()
    weight = request.POST.get("weight")
    max_marks = request.POST.get("max_marks")
    if not name:
        messages.error(request, "Name is required.")
    else:
        comp.name = name
        if weight is not None:
            comp.weight = weight or 0
        if max_marks is not None:
            comp.max_marks = max_marks or 100
        comp.save()
        messages.success(request, "Component updated.")
    return redirect(reverse('edit_assessment_scheme', args=[course.code]))


@require_POST
def delete_component(request, course_code, component_id):
    email = request.session["email_id"]
    faculty = get_object_or_404(Faculty, email_id=email)
    course = get_object_or_404(Course, code=course_code, faculties=faculty)
    comp = get_object_or_404(AssessmentComponent, id=component_id, course=course)
    comp.delete()
    messages.success(request, "Component removed.")
    return redirect(reverse('edit_assessment_scheme', args=[course.code]))
# ----------------- Faculty course cards + enter marks -----------------

def faculty_marks_courses(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    courses = (
        Course.objects
        .filter(faculties=faculty)
        .order_by('code', 'name')
        .distinct()
    )
    return render(
        request,
        'instructor/marks_course_list.html',
        {'faculty': faculty, 'courses': courses}
    )

def mark_field_name(student_id, comp_id):
    return f"mark_{student_id}_{comp_id}"

def enter_marks(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # Identify Faculty (for back button)
    faculty = None
    fid = request.GET.get('faculty_id')
    if fid:
        faculty = Faculty.objects.filter(id=fid).first()
    if faculty is None:
        faculty = course.faculties.first()

    # Assessment components
    components = list(
        AssessmentComponent.objects.filter(course=course).order_by('id')
    )

    # Enrollments with students
    enrollments_qs = (
        StudentCourse.objects.filter(course=course, status='ENR')
        .select_related('student')
        .order_by('student__roll_no')
    )
    enrollments = list(enrollments_qs)
    students = [e.student for e in enrollments]

    # Existing marks map
    existing = {}
    if students and components:
        for s in AssessmentScore.objects.filter(
            course=course, student__in=students, component__in=components
        ):
            existing[(s.student_id, s.component_id)] = s

    # Prefill baseline from DB (used for GET and as base for POST re-render)
    prefill = {
        mark_field_name(stu_id, comp_id): f"{s.marks_obtained}"
        for (stu_id, comp_id), s in existing.items()
    }

    if request.method == 'POST':
        cell_errors, to_create, to_update = [], [], []

        is_upload_all = 'upload_all' in request.POST
        is_upload_component = 'upload_component' in request.POST

        import pandas as pd

        # -------- Bulk upload (one file with columns: roll_no and component names) --------
        if is_upload_all:
            file = request.FILES.get('bulk_file')
            if not file:
                cell_errors.append(("File Error", "-", "No file provided"))
            else:
                try:
                    df = pd.read_excel(file) if file.name.endswith(('.xls', '.xlsx')) else pd.read_csv(file)
                    df.columns = [c.strip().lower() for c in df.columns]
                except Exception as ex:
                    cell_errors.append(("File Error", "-", f"Failed to parse file: {ex}"))
                    df = None

                if df is not None:
                    if 'roll_no' not in df.columns:
                        cell_errors.append(("File Error", "-", "Missing 'roll_no' column"))
                    else:
                        by_roll = {e.student.roll_no.strip().lower(): e.student for e in enrollments}
                        for _, row in df.iterrows():
                            roll_key = str(row['roll_no']).strip().lower()
                            student_obj = by_roll.get(roll_key)
                            if not student_obj:
                                cell_errors.append((row.get('roll_no', ''), "N/A", "Not enrolled"))
                                continue
                            for comp in components:
                                cname = comp.name.strip().lower()
                                if cname not in df.columns:
                                    continue
                                val = row[cname]
                                if pd.isna(val):
                                    continue
                                try:
                                    val = float(val)
                                except (ValueError, TypeError):
                                    cell_errors.append((row.get('roll_no', ''), comp.name, "Invalid number"))
                                    continue
                                if val < 0 or val > comp.max_marks:
                                    cell_errors.append((row.get('roll_no', ''), comp.name, f"Must be 0–{comp.max_marks}"))
                                    continue
                                obj = existing.get((student_obj.id, comp.id))
                                if obj:
                                    obj.marks_obtained = val
                                    to_update.append(obj)
                                else:
                                    to_create.append(AssessmentScore(
                                        student=student_obj, course=course, component=comp, marks_obtained=val
                                    ))

            if to_create:
                AssessmentScore.objects.bulk_create(to_create, batch_size=500)
                for obj in to_create:
                    existing[(obj.student_id, obj.component_id)] = obj
            if to_update:
                AssessmentScore.objects.bulk_update(to_update, ['marks_obtained'], batch_size=500)

            # Refresh prefill from DB results
            prefill = {
                mark_field_name(stu_id, comp_id): f"{s.marks_obtained}"
                for (stu_id, comp_id), s in existing.items()
            }

            if cell_errors:
                return render(request, 'instructor/enter_marks.html', {
                    'course': course, 'components': components, 'enrollments': enrollments,
                    'prefill': prefill, 'cell_errors': cell_errors, 'faculty': faculty
                })
            url = reverse('enter_marks', kwargs={'course_id': course.id})
            if faculty:
                url = f"{url}?faculty_id={faculty.id}"
            return redirect(url)

        # -------- Per-component upload (multiple component_csv_<id> inputs) --------
        elif is_upload_component:
            for comp in components:
                file = request.FILES.get(f'component_csv_{comp.id}')
                if not file:
                    continue
                try:
                    df = pd.read_excel(file) if file.name.endswith(('.xls', '.xlsx')) else pd.read_csv(file)
                    df.columns = [c.strip().lower() for c in df.columns]
                except Exception as ex:
                    cell_errors.append((comp.name, "-", f"Failed to parse file: {ex}"))
                    continue
                if 'roll_no' not in df.columns or 'marks' not in df.columns:
                    cell_errors.append((comp.name, "-", "Missing roll_no or marks column"))
                    continue

                by_roll = {e.student.roll_no.strip().lower(): e.student for e in enrollments}
                for _, row in df.iterrows():
                    roll_key = str(row['roll_no']).strip().lower()
                    val = row['marks']
                    student_obj = by_roll.get(roll_key)
                    if not student_obj:
                        cell_errors.append((row.get('roll_no', ''), comp.name, "Not enrolled"))
                        continue
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        cell_errors.append((row.get('roll_no', ''), comp.name, "Invalid number"))
                        continue
                    if val < 0 or val > comp.max_marks:
                        cell_errors.append((row.get('roll_no', ''), comp.name, f"Must be 0–{comp.max_marks}"))
                        continue
                    obj = existing.get((student_obj.id, comp.id))
                    if obj:
                        obj.marks_obtained = val
                        to_update.append(obj)
                    else:
                        to_create.append(AssessmentScore(
                            student=student_obj, course=course, component=comp, marks_obtained=val
                        ))

            if to_create:
                AssessmentScore.objects.bulk_create(to_create, batch_size=500)
                for obj in to_create:
                    existing[(obj.student_id, obj.component_id)] = obj
            if to_update:
                AssessmentScore.objects.bulk_update(to_update, ['marks_obtained'], batch_size=500)

            prefill = {
                mark_field_name(stu_id, comp_id): f"{s.marks_obtained}"
                for (stu_id, comp_id), s in existing.items()
            }

            if cell_errors:
                return render(request, 'instructor/enter_marks.html', {
                    'course': course, 'components': components, 'enrollments': enrollments,
                    'prefill': prefill, 'cell_errors': cell_errors, 'faculty': faculty
                })
            url = reverse('enter_marks', kwargs={'course_id': course.id})
            if faculty:
                url = f"{url}?faculty_id={faculty.id}"
            return redirect(url)

        # -------- Manual grid --------
        else:
            for e in enrollments:
                for comp in components:
                    field = mark_field_name(e.student_id, comp.id)
                    raw = (request.POST.get(field) or '').strip()
                    if raw == '':
                        continue
                    try:
                        val = float(raw)
                    except ValueError:
                        cell_errors.append((e.student.roll_no, comp.name, "Invalid number"))
                        continue
                    if val < 0 or val > comp.max_marks:
                        cell_errors.append((e.student.roll_no, comp.name, f"Must be 0–{comp.max_marks}"))
                        continue
                    obj = existing.get((e.student_id, comp.id))
                    if obj:
                        obj.marks_obtained = val
                        to_update.append(obj)
                    else:
                        to_create.append(AssessmentScore(
                            student=e.student, course=course, component=comp, marks_obtained=val
                        ))

            if to_create:
                AssessmentScore.objects.bulk_create(to_create, batch_size=500)
                for obj in to_create:
                    existing[(obj.student_id, obj.component_id)] = obj
            if to_update:
                AssessmentScore.objects.bulk_update(to_update, ['marks_obtained'], batch_size=500)

            # Prefill = DB + posted values for failed cells to keep the user's input visible
            prefill = {
                mark_field_name(stu_id, comp_id): f"{s.marks_obtained}"
                for (stu_id, comp_id), s in existing.items()
            }
            for e in enrollments:
                for comp in components:
                    key = mark_field_name(e.student_id, comp.id)
                    if key in request.POST:
                        prefill[key] = request.POST.get(key, '')

            if cell_errors:
                return render(request, 'instructor/enter_marks.html', {
                    'course': course, 'components': components, 'enrollments': enrollments,
                    'prefill': prefill, 'cell_errors': cell_errors, 'faculty': faculty
                })

            url = reverse('enter_marks', kwargs={'course_id': course.id})
            if faculty:
                url = f"{url}?faculty_id={faculty.id}"
            return redirect(url)

    # GET: show current DB values prefilled
    return render(request, 'instructor/enter_marks.html', {
        'course': course, 'components': components, 'enrollments': enrollments,
        'prefill': prefill, 'cell_errors': [], 'faculty': faculty
    })

def course_marks_overview(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    components = list(
        AssessmentComponent.objects.filter(course=course).order_by('id')
    )

    enrollments = (
        StudentCourse.objects
        .filter(course=course, status='ENR')
        .select_related('student')
        .order_by('student__roll_no')
    )
    students = [e.student for e in enrollments]

    # Scores lookup as Decimal
    scores = {}
    if students and components:
        for s in AssessmentScore.objects.filter(
            course=course, student__in=students, component__in=components
        ):
            try:
                scores[(s.student_id, s.component_id)] = Decimal(str(s.marks_obtained))
            except (InvalidOperation, TypeError):
                scores[(s.student_id, s.component_id)] = None

    # Component max and weights as Decimal
    comp_info = []
    total_weight = Decimal('0')
    for c in components:
        max_d = Decimal(str(c.max_marks))
        # If your model lacks 'weight', replace with Decimal('1') or the appropriate field
        w = getattr(c, 'weight', None)
        weight_d = Decimal(str(w)) if w is not None else Decimal('1')
        comp_info.append((c, max_d, weight_d))
        total_weight += weight_d

    # Prepare rows with weighted totals
    rows = []
    totals_by_student = {}
    for e in enrollments:
        stu = e.student
        pairs = []
        weighted_total = Decimal('0')
        for comp, max_d, weight_d in comp_info:
            val = scores.get((stu.id, comp.id))
            # value shown as raw marks; weighted used for total
            if val is not None and max_d > 0:
                contrib = (val / max_d) * weight_d
                weighted_total += contrib
            pairs.append({
                'component': comp,
                'value': val,                 # raw mark
                'max': comp.max_marks,        # for display
                'component_id': comp.id,
            })

        totals_by_student[stu.id] = weighted_total

        # Percentage relative to sum of weights
        if total_weight > 0:
            percentage = (weighted_total / total_weight) * Decimal('100')
        else:
            percentage = None

        rows.append({
            'student': stu,
            'pairs': pairs,
            'total': weighted_total,     # weighted total
            'percentage': percentage,
        })

    # Percentile: rank-based, highest ~100, lowest ~0
    all_totals = [totals_by_student[e.student.id] for e in enrollments]
    n = len(all_totals)
    sorted_totals = sorted(all_totals)

    def percentile_rank(total_value):
        if n == 0:
            return None
        if n == 1:
            return Decimal('100')
        # count strictly lower totals (lower bound index)
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_totals[mid] < total_value:
                lo = mid + 1
            else:
                hi = mid
        lower = lo
        # scale to [0, 100] with highest = 100 exactly when unique max
        return (Decimal(lower) / Decimal(n - 1)) * Decimal('100')

    for r in rows:
        r['percentile'] = percentile_rank(r['total']) if r['total'] is not None else None

    # For table header "Max total", show sum of weights (the denominator for %)
    max_total_display = total_weight

    return render(request, 'instructor/course_marks_overview.html', {
        'course': course,
        'components': components,
        'rows': rows,
        'max_total': max_total_display,   # sum of weights
    })

@require_POST
def update_mark_cell(request, course_id):
    # AJAX endpoint for inline edits
    try:
        student_id = int(request.POST.get('student_id'))
        component_id = int(request.POST.get('component_id'))
        raw_val = (request.POST.get('value') or '').strip()
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid parameters")

    course = get_object_or_404(Course, id=course_id)
    comp = get_object_or_404(AssessmentComponent, id=component_id, course=course)

    # Validate enrollment
    enrolled = StudentCourse.objects.filter(
        course=course, status='ENR', student_id=student_id
    ).exists()
    if not enrolled:
        return JsonResponse({'ok': False, 'error': 'Student not enrolled'}, status=400)

    if raw_val == '':
        # Treat empty as delete/unset? Here we choose to clear the score record.
        with transaction.atomic():
            AssessmentScore.objects.filter(
                course=course, student_id=student_id, component_id=component_id
            ).delete()
        return JsonResponse({'ok': True, 'value': ''})

    # Validate number and bounds
    try:
        val = Decimal(raw_val)
    except InvalidOperation:
        return JsonResponse({'ok': False, 'error': 'Invalid number'}, status=400)
    if val < 0 or val > Decimal(str(comp.max_marks)):
        return JsonResponse({'ok': False, 'error': f'0 to {comp.max_marks}'}, status=400)

    # Upsert
    with transaction.atomic():
        obj, created = AssessmentScore.objects.select_for_update().get_or_create(
            course=course, student_id=student_id, component=comp,
            defaults={'marks_obtained': val}
        )
        if not created:
            obj.marks_obtained = val
            obj.save(update_fields=['marks_obtained'])

    return JsonResponse({'ok': True, 'value': str(val)})

from io import TextIOWrapper
import csv
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from openpyxl import load_workbook


def _canon(s: str) -> str:
    import re
    return re.sub(r'[^a-z0-9]+','', (s or "").lower())

def _iter_rows_as_dicts(uploaded_file):
    """
    Yield rows as dicts keyed by header from CSV/XLSX/XLS.
    """
    name = (getattr(uploaded_file, "name", "") or "").lower()

    # CSV
    if name.endswith(".csv"):
        text = TextIOWrapper(uploaded_file.file, encoding="utf-8", newline="")
        reader = csv.DictReader(text)
        for row in reader:
            yield row
        return

    # Excel
    if name.endswith(".xlsx") or name.endswith(".xls"):
        wb = load_workbook(uploaded_file, data_only=True)
        ws = wb.active  # use first sheet
        rows = ws.iter_rows(values_only=True)
        headers = None
        for idx, r in enumerate(rows):
            if idx == 0:
                headers = [str(h or "").strip() for h in r]
                continue
            row = {}
            for h, v in zip(headers, r):
                row[h] = "" if v is None else v
            yield row
        return

    # Fallback to CSV
    text = TextIOWrapper(uploaded_file.file, encoding="utf-8", newline="")
    reader = csv.DictReader(text)
    for row in reader:
        yield row


def all_courses(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)

    qs = (
        Course.objects
        .filter(faculties=faculty)
        .prefetch_related('faculties')
        .annotate(
            enrolled_count=Count(
                'enrollments',
                filter=Q(enrollments__status='ENR'),
                distinct=True
            )
        )
        .order_by('code')
    )

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))

    courses = []
    for c in qs:
        sem_disp = getattr(c, 'semester_display', None) or getattr(c, 'semester', '') or ''
        c.semester_display = sem_disp
        if not hasattr(c, 'enrolled_count') or c.enrolled_count is None:
            c.enrolled_count = 0
        courses.append(c)

    return render(request, 'instructor/all_courses.html', {
        'faculty': faculty,
        'courses': courses,
    })

def assign_grades_csv(request, course_code):
    NUM_TO_LETTER_GRADE = {
        10: "A", 9: "A-", 8: "B", 7: "B-", 6: "C", 5: "C-", 4: "D", 0: "F"
    }

    # Auth and course
    email = request.session.get("email_id")
    faculty = get_object_or_404(Faculty, email_id=email)
    course = get_object_or_404(Course, code=course_code, faculties=faculty)

    # Components (no semester on model)
    components = list(AssessmentComponent.objects.filter(course=course))
    comp_by_key = {_canon(c.name): c for c in components}

    # ENR students
    affected_qs = StudentCourse.objects.filter(course=course, status='ENR').select_related("student")
    num_enr_students = affected_qs.count()
    force_absolute = num_enr_students <= 25

    if request.method == "POST":
        f_scores = request.FILES.get("csv_file")
        if not f_scores:
            messages.error(request, "Please choose a CSV or Excel file to upload.")
            return redirect(request.path)

        # Grading mode and parameters
        policy_mode = (request.POST.get("mode") or "ABS").upper()
        if force_absolute:
            policy_mode = "ABS"

        # Helper casting
        def _as_int(v, d):  
            try: return int(v)
            except (TypeError, ValueError): return d
        def _as_float(v, d):
            try: return float(v)
            except (TypeError, ValueError): return d

        abs_thresholds = {
            "A": _as_int(request.POST.get("abs_A"), 85),
            "A_minus": _as_int(request.POST.get("abs_B"), 75),
            "B": _as_int(request.POST.get("abs_C"), 65),
            "B_minus": _as_int(request.POST.get("abs_D"), 55),
            "C": _as_int(request.POST.get("abs_E"), 45),
            "C_minus": _as_int(request.POST.get("abs_C_minus"), 40),
            "D": _as_int(request.POST.get("abs_D_grade"), 35),
        }
        try:
            pass_min = Decimal(request.POST.get("pass_min_percent") or 45)
        except (InvalidOperation, TypeError):
            pass_min = Decimal("45")

        rel_buckets = {
            "top10": _as_float(request.POST.get("top10"), 10),
            "next15": _as_float(request.POST.get("next15"), 15),
            "next25": _as_float(request.POST.get("next25"), 25),
            "next25b": _as_float(request.POST.get("next25b"), 25),
            "next15b": _as_float(request.POST.get("next15b"), 15),
            "next10": _as_float(request.POST.get("next10"), 10),
            "rest_min": _as_int(request.POST.get("rest_min"), 4),
        }

        # Read uploaded rows
        rows_list = list(_iter_rows_as_dicts(f_scores))
        if not rows_list:
            messages.error(request, "No rows found in the uploaded file.")
            return redirect(request.path)
        headers = list(rows_list[0].keys())
        roll_aliases = {"roll", "rollno", "rollnumber", "roll_no", "roll no"}
        has_roll = any(_canon(h) in roll_aliases for h in headers)
        if not has_roll:
            messages.error(request, "File must contain a roll_no column.")
            return redirect(request.path)
        comp_headers = [h for h in headers if _canon(h) in comp_by_key]
        if not comp_headers:
            messages.error(request, "File must contain at least one component matching the scheme.")
            return redirect(request.path)

        updated_scores, missing_students, invalid_marks = 0, [], []

        with transaction.atomic():
            for row in rows_list:
                ident = (row.get("roll_no") or row.get("roll") or row.get("Roll No") or row.get("ROLL_NO") or "")
                ident = str(ident).strip()
                if not ident:
                    missing_students.append("(blank)")
                    continue
                student = Student.objects.filter(roll_no__iexact=ident).first()
                if not student:
                    missing_students.append(ident)
                    continue
                sc = StudentCourse.objects.filter(student=student, course=course, status='ENR').first()
                if not sc:
                    continue
                for raw_h, val in row.items():
                    key = _canon(raw_h)
                    comp = comp_by_key.get(key)
                    if not comp or val is None or str(val).strip() == "":
                        continue
                    try:
                        m = Decimal(str(val))
                    except InvalidOperation:
                        invalid_marks.append((ident, raw_h, val))
                        continue
                    try:
                        max_d = Decimal(str(comp.max_marks))
                    except (InvalidOperation, TypeError):
                        max_d = Decimal("0")
                    if m < 0 or m > max_d:
                        invalid_marks.append((ident, raw_h, val))
                        continue
                    AssessmentScore.objects.update_or_create(
                        student=student,
                        course=course,
                        component=comp,
                        defaults={"marks_obtained": m}
                    )
                    updated_scores += 1

        # Grading: process only non-P/F students
        totals_per_student, totals_dict = [], {}
        for sc in affected_qs:
            if getattr(sc, "pass_fail", False):
                continue
            total_percent = Decimal("0")
            for comp in components:
                s = AssessmentScore.objects.filter(student=sc.student, course=course, component=comp).first()
                if s and comp.max_marks and comp.weight:
                    try:
                        total_percent += (Decimal(str(s.marks_obtained)) / Decimal(str(comp.max_marks))) * Decimal(str(comp.weight))
                    except (InvalidOperation, TypeError):
                        continue
            totals_per_student.append((sc.student_id, total_percent))
            totals_dict[sc.student_id] = total_percent

        # Absolute or Relative Assign
        if policy_mode == "REL":
            cohort = sorted(totals_per_student, key=lambda x: x[1], reverse=True)
            n = len(cohort)
            seq = [("top10", 10), ("next15", 9), ("next25", 8), ("next25b", 7), ("next15b", 6), ("next10", 5)]
            counts, remaining = [], n
            for key, _cg in seq:
                pct = float(rel_buckets.get(key, 0))
                c = int(round((pct / 100.0) * n))
                c = max(0, min(c, remaining))
                counts.append(c)
                remaining -= c
            rest_min = int(rel_buckets.get("rest_min", 4))
            cg_map, idx = {}, 0
            for (count, (_key, cg)) in zip(counts, seq):
                for _ in range(count):
                    if idx < n:
                        sid, _ = cohort[idx]
                        cg_map[sid] = cg
                        idx += 1
            for i in range(idx, n):
                sid, _ = cohort[i]
                cg_map[sid] = rest_min

            for sc in affected_qs:
                if getattr(sc, "pass_fail", False):
                    continue
                cg = cg_map.get(sc.student_id)
                if cg is not None:
                    letter_grade = NUM_TO_LETTER_GRADE.get(int(cg), "F")
                    sc.grade = letter_grade
                    sc.outcome = "PAS" if cg >= 4 else "FAI"
                    sc.status = "CMP"
                    sc.save(update_fields=["grade", "outcome", "status"])
        else:
            def cg_from_abs(pct: Decimal) -> int:
                if pct >= abs_thresholds["A"]: return 10
                if pct >= abs_thresholds["A_minus"]: return 9
                if pct >= abs_thresholds["B"]: return 8
                if pct >= abs_thresholds["B_minus"]: return 7
                if pct >= abs_thresholds["C"]: return 6
                if pct >= abs_thresholds["C_minus"]: return 5
                if pct >= abs_thresholds["D"]: return 4
                return 0

            for sc in affected_qs:
                if getattr(sc, "pass_fail", False):
                    continue
                pct = totals_dict.get(sc.student_id, Decimal("0"))
                cg = cg_from_abs(pct)
                letter_grade = NUM_TO_LETTER_GRADE.get(cg, "F")
                sc.grade = letter_grade
                sc.outcome = "PAS" if pct >= pass_min and cg >= 4 else "FAI"
                sc.status = "CMP"
                sc.save(update_fields=["grade", "outcome", "status"])

        # Messages on upload status
        if updated_scores: messages.success(request, f"Uploaded {updated_scores} scores and assigned grades.")
        if missing_students: messages.warning(request, f"{len(missing_students)} rows had missing or unknown roll_no.")
        if invalid_marks: messages.warning(request, f"{len(invalid_marks)} invalid marks skipped.")

        return redirect(f"{reverse('grade_results', args=[course.code])}")

    # GET: Render
    return render(request, "instructor/assign_grades.html", {
        "course": course,
        "faculty": faculty,
        "components": components,
        "total_weight": sum([float(c.weight or 0) for c in components]) if components else None,
        "sample_headers": ["roll_no"] + [c.name for c in components],
        "force_absolute": force_absolute,
        "num_enr_students": num_enr_students,
    })


def grade_results(request, course_code):
    # Auth and course
    email = request.session.get("email_id")
    faculty = get_object_or_404(Faculty, email_id=email)
    course = get_object_or_404(Course, code=course_code, faculties=faculty)

    # Components (shown as columns)
    components = list(AssessmentComponent.objects.filter(course=course))

    # ENR or CMP enrollments, across all semesters (shows completed too)
    enrollments = (
        StudentCourse.objects
        .filter(course=course, status__in=['ENR', 'CMP'])
        .select_related('student')
        .order_by('student__roll_no')
    )

    LETTER_TO_POINTS = {
        "A": 10,
        "A-": 9,
        "B": 8,
        "B-": 7,
        "C": 6,
        "C-": 5,
        "D": 4,
        "F": 0,
    }

    def letter_for_points(points):
        try:
            p = int(points)
        except (TypeError, ValueError):
            return ''
        if p >= 10: return 'A'
        if p == 9:  return 'A-'
        if p == 8:  return 'B'
        if p == 7:  return 'B-'
        if p == 6:  return 'C'
        if p == 5:  return 'C-'
        if p == 4:  return 'D'
        return 'F'

    rows = []
    for sc in enrollments:
        comp_marks = {}
        total_percent = Decimal("0")
        for comp in components:
            s = AssessmentScore.objects.filter(student=sc.student, course=course, component=comp).first()
            mark = s.marks_obtained if s else None
            comp_marks[comp.id] = mark
            if s and comp.max_marks and comp.weight:
                try:
                    total_percent += (Decimal(str(s.marks_obtained)) / Decimal(str(comp.max_marks))) * Decimal(str(comp.weight))
                except (InvalidOperation, TypeError):
                    pass

        pts_int = LETTER_TO_POINTS.get(sc.grade, None)
        letter = sc.grade or (letter_for_points(pts_int) if pts_int is not None else "")

        rows.append({
            'student': sc.student,
            'roll': sc.student.roll_no,
            'name': f"{sc.student.first_name} {sc.student.last_name or ''}".strip(),
            'components': comp_marks,
            'total_percent': float(total_percent.quantize(Decimal('0.01'))),
            'points': pts_int,
            'letter': letter,
            'outcome': sc.outcome or '',
        })

    # Sorting
    sort = (request.GET.get("sort") or "roll_asc").lower()
    reverse = sort.endswith("_desc")
    base = sort.split("_")[0]
    if base == "name":
        rows.sort(key=lambda r: (r['name'].lower(), r['roll'].lower()), reverse=reverse)
    elif base == "roll":
        rows.sort(key=lambda r: r['roll'].lower(), reverse=reverse)
    elif base == "points":
        rows.sort(key=lambda r: (r['points'] if r['points'] is not None else -1, r['name'].lower()), reverse=reverse)
    elif base == "letter":
        rows.sort(key=lambda r: (r['points'] if r['points'] is not None else -1, r['name'].lower()), reverse=reverse)

    return render(request, 'instructor/grade_results.html', {
        'course': course,
        'faculty': faculty,
        'components': components,
        'rows': rows,
        'sort': sort,
    })

def student_result_semester_list(request, roll_no):
    student = get_object_or_404(Student, roll_no=roll_no)
    admin = Admins.objects.first()

    results_visible = admin.is_results_visible() if admin else False
    current_sem = student.calculate_current_semester()

    semesters = (
        student.enrollments
        .filter(status__in=['ENR', 'CMP'])
        .values_list('semester', flat=True)
        .distinct()
        .order_by('semester')
    )

    context = {
        "student": student,
        "semesters": semesters,
        "current_sem": current_sem,
        "results_visible": results_visible,
    }
    return render(request, "student/result_semester_list.html", context)

def student_view_results(request, student_id, semester):
    student = get_object_or_404(Student, id=student_id)
    enrollments = (
        StudentCourse.objects
        .filter(student=student, semester=semester, status__in=['ENR', 'CMP'])
        .select_related('course')
    )

    # Prepare detailed list of courses and grades
    results = []
    for enr in enrollments:
        course = enr.course
        grade = enr.grade or ''
        points = GRADE_POINTS.get(grade, 0)
        results.append({
            "course_code": course.code,
            "course_name": course.name,
            "credits": course.credits,
            "grade": grade,
            "points": points,
            "outcome": enr.outcome,
            "is_pass_fail": enr.is_pass_fail,
        })

    # Compute registered and earned credits from approved enrollments only
    registered_credits = sum((enr.course.credits or 0) for enr in enrollments)
    earned_credits = sum((enr.course.credits or 0) for enr in enrollments if (enr.outcome or '').upper() == 'PAS')

    # Keep existing metrics but override rcr/ecr to the approved-enrollment view
    metrics = student.calculate_semester_metrics(semester)
    try:
        metrics['rcr'] = registered_credits
    except Exception:
        pass
    try:
        metrics['ecr'] = earned_credits
    except Exception:
        pass
    cg_metrics = student.calculate_cumulative_metrics()
    return render(request, "student/result_semester_view.html", {
        "student": student,
        "semester": semester,
        "results": results,
        "metrics": metrics,
        "cg_metrics": cg_metrics,
    })


def student_result_pdf(request, student_id, semester):
    student = get_object_or_404(Student, id=student_id)
    enrollments = (
        StudentCourse.objects
        .filter(student=student, semester=semester, status__in=['ENR', 'CMP'])
        .select_related('course')
    )
    
    results = []
    for enr in enrollments:
        course = enr.course
        grade = enr.grade or ''
        points = GRADE_POINTS.get(grade, 0)
        results.append({
            "course_code": course.code,
            "course_name": course.name,
            "credits": course.credits,
            "grade": grade,
            "points": points,
            "outcome": enr.outcome,
            "is_pass_fail": enr.is_pass_fail,
        })

    # Compute registered and earned credits based on approved enrollments only
    registered_credits = sum((enr.course.credits or 0) for enr in enrollments)
    earned_credits = sum((enr.course.credits or 0) for enr in enrollments if (enr.outcome or '').upper() == 'PAS')

    # Keep existing metrics but override rcr/ecr
    metrics = student.calculate_semester_metrics(semester)
    try:
        metrics['rcr'] = registered_credits
    except Exception:
        pass
    try:
        metrics['ecr'] = earned_credits
    except Exception:
        pass

    cg_metrics = student.calculate_cumulative_metrics()

    html_string = render_to_string(
        "student/marksheet_pdf.html",
        {
            "student": student,
            "semester": semester,
            "results": results,
            "metrics": metrics,
            "cg_metrics": cg_metrics,
        }
    )
    html = HTML(string=html_string)
    pdf = html.write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=Marksheet_{student.roll_no}_Sem_{semester}.pdf"
    return response

from django.db.models import Count, Q
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone


def get_main_admin():
    """Fetch main admin record (assuming 1 admin controls visibility)."""
    return Admins.objects.first()


def admin_grade_management(request):
    """
    Admin landing page: List all courses with enrolled students + control result visibility.
    """
    # Get all courses with at least one enrolled student
    courses = Course.objects.annotate(
        enrolled_count=Count('enrollments', filter=Q(enrollments__status__in=['ENR', 'CMP']))
    ).filter(enrolled_count__gt=0)

    # Prepare course data (no grading_type needed)
    course_data = [
        {
            'code': c.code,
            'name': c.name,
            'slot': c.slot,
            'enrolled_count': c.enrolled_count,
        }
        for c in courses
    ]

    # Get unique semesters and slots for filters
    semesters = StudentCourse.objects.values_list('semester', flat=True).distinct().order_by('semester')
    slots = Course.objects.values_list('slot', flat=True).distinct().order_by('slot')

    # ✅ Fetch result visibility settings from Admin model
    admin = get_main_admin()
    if not admin:
        admin = Admins.objects.create(
            first_name="Default", last_name="Admin",
            email_id="admin@example.com", password="admin"
        )

    return render(request, 'admin/assign_grade_management.html', {
        'courses': course_data,
        'semesters': semesters,
        'slots': slots,
        'admin': admin,  # 👈 Pass to template for mode + deadline
    })


def set_result_visibility(request):
    """
    Handle result visibility setting form submission.
    """
    if request.method == "POST":
        admin = get_main_admin()
        mode = request.POST.get("mode")
        deadline = request.POST.get("deadline") or None

        admin.results_mode = mode
        admin.results_deadline = deadline
        admin.save()

        messages.success(request, "Result visibility settings updated successfully!")
    return redirect("admin_grade_management")

def admin_assign_grades(request, course_code):
    """
    Display all enrolled students for a course to assign/edit grades
    Allows editing for both ENR and CMP statuses!
    """
    course = get_object_or_404(Course, code=course_code)
    
    # Show both ENR and CMP
    enrollments = StudentCourse.objects.filter(
        course=course,
        status__in=['ENR', 'CMP']
    ).select_related('student').order_by('student__roll_no')

    return render(request, 'admin/assign_edit_grades.html', {
        'course': course,
        'enrollments': enrollments,
    })

def admin_save_grades(request, course_code):
    """
    Save grades submitted by admin for a course.
    Now updates grades for BOTH ENR and CMP records, and always sets them to CMP.
    """
    if request.method != 'POST':
        return redirect('admin_assign_grades', course_code=course_code)

    course = get_object_or_404(Course, code=course_code)
    
    # Allow grade changes for both ENR and CMP status enrollments
    enrollments = StudentCourse.objects.filter(course=course, status__in=['ENR', 'CMP'])

    updated_count = 0
    for enrollment in enrollments:
        grade_key = f'grade_{enrollment.id}'
        outcome_key = f'outcome_{enrollment.id}'
        grade = request.POST.get(grade_key, '').strip()
        outcome = request.POST.get(outcome_key, 'UNK')

        # Update if grade is provided
        if grade and grade in GRADE_POINTS:
            enrollment.grade = grade
            enrollment.outcome = outcome
            enrollment.status = 'CMP'  # Always set as complete when edited
            enrollment.save(update_fields=['grade', 'outcome', 'status'])
            updated_count += 1

    messages.success(request, f'Successfully updated grades for {updated_count} student(s) in {course.code}.')
    return redirect('admin_assign_grades', course_code=course_code)

# For Excel export
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# For PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER

from Registration.models import (
    Student, Faculty, Course, Branch, Department, 
    StudentCourse, Category, ProgramRequirement, 
    CourseBranch, AssessmentComponent, AssessmentScore
)


def database_management_view(request):
    """
    Main view for database management dashboard
    Loads all data with pagination support
    """
    
    # Fetch all data from database
    students = Student.objects.select_related('branch', 'department').all()
    faculty = Faculty.objects.select_related('department').all()
    courses = Course.objects.all()
    branches = Branch.objects.select_related('department').all()
    departments = Department.objects.all()
    enrollments = StudentCourse.objects.select_related('student', 'course').all()
    categories = Category.objects.all()
    requirements = ProgramRequirement.objects.select_related('branch').all()
    
    # Prepare students data
    students_data = []
    for student in students:
        students_data.append({
            'id': student.id,
            'roll_no': student.roll_no,
            'first_name': student.first_name,
            'last_name': student.last_name or '',
            'email': student.email_id,
            'branch': student.branch.name if student.branch else 'N/A',
            'department': student.department.code if student.department else 'N/A',
            'semester': student.calculate_current_semester(),  # Use calculated semester
            'mobile': str(student.mobile_no) if student.mobile_no else 'N/A'
        })
    
    # Prepare faculty data
    faculty_data = []
    for fac in faculty:
        course_count = fac.courses.count()
        faculty_data.append({
            'id': fac.id,
            'first_name': fac.first_name,
            'last_name': fac.last_name or '',
            'email': fac.email_id,
            'department': fac.department.code if fac.department else 'N/A',
            'mobile': str(fac.mobile_no) if fac.mobile_no else 'N/A',
            'courses': course_count
        })
    
    # Prepare courses data
    courses_data = []
    for course in courses:
        enrolled_count = course.enrollments.filter(status__in=['ENR', 'CMP']).count()
        courses_data.append({
            'id': course.id,
            'code': course.code,
            'name': course.name,
            'credits': course.credits,
            'ltpc': course.LTPC,
            'slot': course.slot,
            'status': course.status,
            'enrolled': enrolled_count
        })
    
    # Prepare branches data
    branches_data = []
    for branch in branches:
        student_count = branch.student_set.count()
        course_count = branch.courses.count()
        branches_data.append({
            'id': branch.id,
            'name': branch.name,
            'full_name': dict(Branch.BRANCHES).get(branch.name, branch.name),
            'department': branch.department.code if branch.department else 'N/A',
            'students': student_count,
            'courses': course_count
        })
    
    # Prepare departments data
    departments_data = []
    for dept in departments:
        branch_count = dept.branches.count()
        faculty_count = dept.faculty_set.count()
        student_count = dept.student_set.count()
        departments_data.append({
            'id': dept.id,
            'code': dept.code,
            'name': dept.name,
            'branches': branch_count,
            'faculty': faculty_count,
            'students': student_count
        })
    
    # Prepare enrollments data
    enrollments_data = []
    for enr in enrollments:
        enrollments_data.append({
            'id': enr.id,
            'student': f"{enr.student.first_name} {enr.student.last_name or ''}".strip(),
            'roll_no': enr.student.roll_no,
            'course': enr.course.code,
            'semester': enr.semester or 'N/A',
            'status': enr.status,
            'grade': enr.grade or '-',
            'outcome': enr.outcome,
            'is_pass_fail': enr.is_pass_fail
        })
    
    # Prepare categories data
    categories_data = []
    for cat in categories:
        course_count = cat.course_branches.count()
        categories_data.append({
            'id': cat.id,
            'code': cat.code,
            'label': cat.label,
            'courses': course_count
        })
    
    # Prepare requirements data
    requirements_data = []
    for req in requirements:
        requirements_data.append({
            'id': req.id,
            'branch': req.branch.name,
            'category': req.category,
            'required_credits': req.required_credits
        })
    
    # Convert to JSON for template
    import json
    context = {
        'students_json': json.dumps(students_data),
        'faculty_json': json.dumps(faculty_data),
        'courses_json': json.dumps(courses_data),
        'branches_json': json.dumps(branches_data),
        'departments_json': json.dumps(departments_data),
        'enrollments_json': json.dumps(enrollments_data),
        'categories_json': json.dumps(categories_data),
        'requirements_json': json.dumps(requirements_data),
    }
    
    return render(request, 'admin/database_management.html', context)


def edit_database_record(request, record_type, record_id):
    """
    View for editing a specific record
    """
    
    if request.method == 'POST':
        try:
            if record_type == 'student':
                student = get_object_or_404(Student, id=record_id)
                student.first_name = request.POST.get('first_name', student.first_name)
                student.last_name = request.POST.get('last_name', student.last_name)
                student.email_id = request.POST.get('email', student.email_id)
                student.mobile_no = request.POST.get('mobile', student.mobile_no)
                
                branch_id = request.POST.get('branch')
                if branch_id:
                    student.branch = Branch.objects.get(id=branch_id)
                
                student.save()
                return JsonResponse({'success': True, 'message': 'Student updated successfully'})
            
            elif record_type == 'faculty':
                faculty = get_object_or_404(Faculty, id=record_id)
                faculty.first_name = request.POST.get('first_name', faculty.first_name)
                faculty.last_name = request.POST.get('last_name', faculty.last_name)
                faculty.email_id = request.POST.get('email', faculty.email_id)
                faculty.mobile_no = request.POST.get('mobile', faculty.mobile_no)
                
                dept_id = request.POST.get('department')
                if dept_id:
                    faculty.department = Department.objects.get(id=dept_id)
                
                faculty.save()
                return JsonResponse({'success': True, 'message': 'Faculty updated successfully'})
            
            elif record_type == 'course':
                course = get_object_or_404(Course, id=record_id)
                course.code = request.POST.get('code', course.code)
                course.name = request.POST.get('name', course.name)
                course.credits = request.POST.get('credits', course.credits)
                course.LTPC = request.POST.get('ltpc', course.LTPC)
                course.slot = request.POST.get('slot', course.slot)
                course.status = request.POST.get('status', course.status)
                course.save()
                return JsonResponse({'success': True, 'message': 'Course updated successfully'})
            
            elif record_type == 'enrollment':
                enrollment = get_object_or_404(StudentCourse, id=record_id)
                enrollment.status = request.POST.get('status', enrollment.status)
                enrollment.grade = request.POST.get('grade', enrollment.grade)
                enrollment.outcome = request.POST.get('outcome', enrollment.outcome)
                enrollment.is_pass_fail = request.POST.get('is_pass_fail', 'false') == 'true'
                enrollment.save()
                return JsonResponse({'success': True, 'message': 'Enrollment updated successfully'})
            
            elif record_type == 'requirement':
                requirement = get_object_or_404(ProgramRequirement, id=record_id)
                requirement.required_credits = request.POST.get('required_credits', requirement.required_credits)
                requirement.save()
                return JsonResponse({'success': True, 'message': 'Requirement updated successfully'})
            
            else:
                return JsonResponse({'success': False, 'error': 'Invalid record type'})
        
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    # GET request - show edit form
    context = {}
    
    if record_type == 'student':
        student = get_object_or_404(Student, id=record_id)
        branches = Branch.objects.all()
        context = {
            'record_type': 'Student',
            'record': student,
            'branches': branches
        }
    
    elif record_type == 'faculty':
        faculty = get_object_or_404(Faculty, id=record_id)
        departments = Department.objects.all()
        context = {
            'record_type': 'Faculty',
            'record': faculty,
            'departments': departments
        }
    
    elif record_type == 'course':
        course = get_object_or_404(Course, id=record_id)
        context = {
            'record_type': 'Course',
            'record': course,
            'slots': Course.SLOT_CHOICES
        }
    
    elif record_type == 'enrollment':
        enrollment = get_object_or_404(StudentCourse, id=record_id)
        context = {
            'record_type': 'Enrollment',
            'record': enrollment,
            'statuses': StudentCourse.STATUS,
            'outcomes': StudentCourse.OUTCOME,
            'grades': StudentCourse.GRADES
        }
    
    elif record_type == 'requirement':
        requirement = get_object_or_404(ProgramRequirement, id=record_id)
        context = {
            'record_type': 'Requirement',
            'record': requirement
        }
    
    return render(request, 'edit_record.html', context)


@require_http_methods(["POST"])
def delete_database_record(request, record_type, record_id):
    """
    Delete a specific record
    """
    try:
        if record_type == 'student':
            record = get_object_or_404(Student, id=record_id)
        elif record_type == 'faculty':
            record = get_object_or_404(Faculty, id=record_id)
        elif record_type == 'course':
            record = get_object_or_404(Course, id=record_id)
        elif record_type == 'enrollment':
            record = get_object_or_404(StudentCourse, id=record_id)
        elif record_type == 'requirement':
            record = get_object_or_404(ProgramRequirement, id=record_id)
        elif record_type == 'branch':
            record = get_object_or_404(Branch, id=record_id)
        elif record_type == 'department':
            record = get_object_or_404(Department, id=record_id)
        elif record_type == 'category':
            record = get_object_or_404(Category, id=record_id)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid record type'})
        
        record.delete()
        return JsonResponse({'success': True, 'message': f'{record_type.capitalize()} deleted successfully'})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def export_page_view(request):
    """
    Display the export configuration page
    """
    context = {
        'students_count': Student.objects.count(),
        'faculty_count': Faculty.objects.count(),
        'courses_count': Course.objects.count(),
        'enrollments_count': StudentCourse.objects.count(),
        'branches_count': Branch.objects.count(),
        'departments_count': Department.objects.count(),
        'categories_count': Category.objects.count(),
        'requirements_count': ProgramRequirement.objects.count(),
        'branches': Branch.objects.all(),
        'departments': Department.objects.all(),
    }
    return render(request, 'admin/database_export.html', context)


def export_filtered_data(request):
    """
    Export filtered data based on user selections
    """
    data_type = request.GET.get('data_type', '')
    export_format = request.GET.get('format', 'csv')
    
    # Get filtered data based on type
    if data_type == 'students':
        data = filter_students(request)
        headers = ['ID', 'Roll No', 'First Name', 'Last Name', 'Email', 'Branch', 'Department', 'Semester', 'Mobile']
        title = 'Students Data'
        
    elif data_type == 'faculty':
        data = filter_faculty(request)
        headers = ['ID', 'First Name', 'Last Name', 'Email', 'Department', 'Mobile', 'Courses Count']
        title = 'Faculty Data'
        
    elif data_type == 'courses':
        data = filter_courses(request)
        headers = ['ID', 'Code', 'Name', 'Credits', 'LTPC', 'Slot', 'Status', 'Enrolled']
        title = 'Courses Data'
        
    elif data_type == 'enrollments':
        data = filter_enrollments(request)
        headers = ['ID', 'Student', 'Roll No', 'Course', 'Semester', 'Status', 'Grade', 'Outcome']
        title = 'Enrollments Data'
        
    elif data_type == 'branches':
        data = filter_branches(request)
        headers = ['ID', 'Code', 'Full Name', 'Department', 'Students', 'Courses']
        title = 'Branches Data'
        
    elif data_type == 'departments':
        data = filter_departments(request)
        headers = ['ID', 'Code', 'Name', 'Branches', 'Faculty', 'Students']
        title = 'Departments Data'
        
    elif data_type == 'categories':
        data = filter_categories(request)
        headers = ['ID', 'Code', 'Label', 'Courses Count']
        title = 'Categories Data'
        
    elif data_type == 'requirements':
        data = filter_requirements(request)
        headers = ['ID', 'Branch', 'Category', 'Required Credits']
        title = 'Program Requirements Data'
        
    else:
        return HttpResponse('Invalid data type', status=400)
    
    # Export based on format
    if export_format == 'excel':
        return export_to_excel(data, headers, title)
    elif export_format == 'pdf':
        return export_to_pdf(data, headers, title)
    else:  # csv
        return export_to_csv(data, headers, title)

def filter_students(request):
    """Filter students based on query parameters"""
    students = Student.objects.select_related('branch', 'department').all()
    
    # Filter by year (from roll number) - FIXED
    years = request.GET.getlist('year')  # Get multiple years
    if years:
        # Extract year patterns: 2024 -> "24", 2023 -> "23", etc.
        year_patterns = [year[2:] for year in years]  # ["24", "23"]
        # Filter students whose roll_no contains any of these patterns
        from django.db.models import Q
        year_query = Q()
        for pattern in year_patterns:
            # Match roll numbers like "B24001", "b24002", etc.
            year_query |= Q(roll_no__iregex=r'^[a-zA-Z]' + pattern + r'\d+$')
        students = students.filter(year_query)
    
    # Filter by branch - UPDATED for multiple values
    branches = request.GET.getlist('branch')
    if branches:
        students = students.filter(branch__name__in=branches)
    
    # Filter by semester - UPDATED for multiple values
    semesters = request.GET.getlist('semester')
    if semesters:
        # Convert to integers for comparison
        semester_ints = [int(s) for s in semesters]
        # Filter by calculated semester
        filtered_students = []
        for student in students:
            if student.calculate_current_semester() in semester_ints:
                filtered_students.append(student)
        students = filtered_students
    
    # Filter by department - UPDATED for multiple values
    departments = request.GET.getlist('department')
    if departments:
        if isinstance(students, list):
            # If already filtered by semester (list)
            students = [s for s in students if s.department and s.department.code in departments]
        else:
            students = students.filter(department__code__in=departments)
    
    # Prepare data rows
    data = []
    student_list = students if isinstance(students, list) else students
    for student in student_list:
        data.append([
            student.id,
            student.roll_no,
            student.first_name,
            student.last_name or '',
            student.email_id,
            student.branch.name if student.branch else 'N/A',
            student.department.code if student.department else 'N/A',
            student.calculate_current_semester(),
            str(student.mobile_no) if student.mobile_no else 'N/A'
        ])
    
    return data


def filter_faculty(request):
    """Filter faculty based on query parameters"""
    faculty = Faculty.objects.select_related('department').all()
    
    # Filter by department - UPDATED for multiple values
    departments = request.GET.getlist('department')
    if departments:
        faculty = faculty.filter(department__code__in=departments)
    
    # Filter by minimum courses
    min_courses = request.GET.get('min_courses')
    if min_courses:
        faculty = faculty.annotate(course_count=Count('courses')).filter(course_count__gte=int(min_courses))
    
    # Prepare data rows
    data = []
    for fac in faculty:
        data.append([
            fac.id,
            fac.first_name,
            fac.last_name or '',
            fac.email_id,
            fac.department.code if fac.department else 'N/A',
            str(fac.mobile_no) if fac.mobile_no else 'N/A',
            fac.courses.count()
        ])
    
    return data


def filter_courses(request):
    """Filter courses based on query parameters"""
    courses = Course.objects.all()
    
    # Filter by slot - UPDATED for multiple values
    slots = request.GET.getlist('slot')
    if slots:
        courses = courses.filter(slot__in=slots)
    
    # Filter by credits - UPDATED for multiple values
    credits_list = request.GET.getlist('credits')
    if credits_list:
        credits_ints = [int(c) for c in credits_list]
        courses = courses.filter(credits__in=credits_ints)
    
    # Filter by status - UPDATED for multiple values
    statuses = request.GET.getlist('status')
    if statuses:
        courses = courses.filter(status__in=statuses)
    
    # Prepare data rows
    data = []
    for course in courses:
        enrolled_count = course.enrollments.filter(status__in=['ENR', 'CMP']).count()
        data.append([
            course.id,
            course.code,
            course.name,
            course.credits,
            course.LTPC,
            course.slot,
            course.status,
            enrolled_count
        ])
    
    return data


def filter_enrollments(request):
    """Filter enrollments based on query parameters"""
    enrollments = StudentCourse.objects.select_related('student', 'course').all()
    
    # Filter by semester - UPDATED for multiple values
    semesters = request.GET.getlist('semester')
    if semesters:
        semester_ints = [int(s) for s in semesters]
        enrollments = enrollments.filter(semester__in=semester_ints)
    
    # Filter by status - UPDATED for multiple values
    statuses = request.GET.getlist('status')
    if statuses:
        enrollments = enrollments.filter(status__in=statuses)
    
    # Filter by outcome - UPDATED for multiple values
    outcomes = request.GET.getlist('outcome')
    if outcomes:
        enrollments = enrollments.filter(outcome__in=outcomes)
    
    # Filter by grade - UPDATED for multiple values
    grades = request.GET.getlist('grade')
    if grades:
        enrollments = enrollments.filter(grade__in=grades)
    
    # Prepare data rows
    data = []
    for enr in enrollments:
        data.append([
            enr.id,
            f"{enr.student.first_name} {enr.student.last_name or ''}".strip(),
            enr.student.roll_no,
            enr.course.code,
            enr.semester or 'N/A',
            enr.status,
            enr.grade or '-',
            enr.outcome
        ])
    
    return data


def filter_requirements(request):
    """Filter requirements based on query parameters"""
    requirements = ProgramRequirement.objects.select_related('branch').all()
    
    # Filter by branch - UPDATED for multiple values
    branches = request.GET.getlist('branch')
    if branches:
        requirements = requirements.filter(branch__name__in=branches)
    
    # Filter by category - UPDATED for multiple values
    categories = request.GET.getlist('category')
    if categories:
        requirements = requirements.filter(category__in=categories)
    
    data = []
    for req in requirements:
        data.append([
            req.id,
            req.branch.name,
            req.category,
            req.required_credits
        ])
    
    return data


def export_to_csv(data, headers, title):
    """Export data to CSV format"""
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{title.replace(' ', '_')}_{timestamp}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(data)
    
    return response


def export_to_excel(data, headers, title):
    """Export data to Excel format with styling"""
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{title.replace(' ', '_')}_{timestamp}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]  # Excel sheet name limit
    
    # Styling
    header_fill = PatternFill(start_color="0D6EFD", end_color="0D6EFD", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=12)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Write headers
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border
    
    # Write data
    for row_num, row_data in enumerate(data, 2):
        for col_num, cell_value in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.value = cell_value
            cell.border = border
            cell.alignment = Alignment(horizontal='left', vertical='center')
            
            # Alternate row colors
            if row_num % 2 == 0:
                cell.fill = PatternFill(start_color="F8F9FA", end_color="F8F9FA", fill_type="solid")
    
    # Auto-adjust column widths
    for col_num, header in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        max_length = len(str(header))
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_num, max_col=col_num):
            for cell in row:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Freeze header row
    ws.freeze_panes = 'A2'
    
    wb.save(response)
    return response


def export_to_pdf(data, headers, title):
    """Export data to PDF format"""
    response = HttpResponse(content_type='application/pdf')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{title.replace(' ', '_')}_{timestamp}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create PDF
    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                           rightMargin=30, leftMargin=30,
                           topMargin=30, bottomMargin=30)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#0d6efd'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    title_para = Paragraph(f"{title}<br/>{datetime.now().strftime('%B %d, %Y %H:%M')}", title_style)
    elements.append(title_para)
    elements.append(Spacer(1, 0.3*inch))
    
    # Prepare table data
    table_data = [headers] + data[:100]  # Limit to 100 rows for PDF
    
    # Calculate column widths
    available_width = landscape(A4)[0] - 60  # Total width minus margins
    col_width = available_width / len(headers)
    col_widths = [col_width] * len(headers)
    
    # Create table
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Style table
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    
    # Add note if data was truncated
    if len(data) > 100:
        elements.append(Spacer(1, 0.3*inch))
        note = Paragraph(
            f"<i>Note: Showing first 100 of {len(data)} records. For complete data, please use Excel or CSV format.</i>",
            styles['Normal']
        )
        elements.append(note)
    
    doc.build(elements)
    return response

def faculty_view_courses_for_grades(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    
    # Courses where faculty is assigned, with enrolled students count
    courses = Course.objects.filter(faculties=faculty).annotate(
        enrolled_count=Count('enrollments', filter=Q(enrollments__status__in=['ENR', 'CMP']))
    ).filter(enrolled_count__gt=0)
    
    return render(request, 'instructor/view_results_courses.html', {
        'faculty': faculty,
        'courses': courses,
    })

def faculty_view_course_grades(request, faculty_id, course_code):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    course = get_object_or_404(Course, code=course_code, faculties=faculty)

    enrollments = StudentCourse.objects.filter(course=course, status__in=['ENR', 'CMP']).select_related('student')

    results = []
    for enr in enrollments:
        grade = enr.grade or ""
        outcome = enr.outcome or ""
        is_pf = enr.is_pass_fail
        # Determine display of Pass/Fail Courses
        display_grade = "Pass/Fail Mode" if is_pf else grade
        display_outcome = "Pass" if is_pf and outcome.upper() == "PAS" else (
            "Fail" if is_pf and outcome.upper() == "FAI" else outcome)
        
        results.append({
            'student': enr.student,
            'grade': display_grade,
            'outcome': display_outcome,
        })
    
    return render(request, 'instructor/faculty_course_grades.html', {
        'faculty': faculty,
        'course': course,
        'results': results,
    })



