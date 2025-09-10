from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from Registration.models import Branch, Category, Course, CourseBranch, Department, ProgramRequirement, Student, Faculty, Admins
from django.contrib.auth import authenticate , login as auth_login
from django.contrib.auth.hashers import make_password,check_password
from urllib.parse import urlencode
from django.core.files.storage import default_storage
import re
from Registration.forms import FacultyEditForm, StudentEditForm
import csv
from django.http import JsonResponse

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@iitmandi\.ac\.in$')
SLOTS = ["A","B","C","D","E","F","G","H","FS"]

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
                        "full_name": f"{faculty.first_name} {faculty.last_name}",
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
                    "full_name": f"{student.first_name} {student.last_name}",
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
    context = {
        "student": student,
        "full_name": flash.get("full_name"),
        "role_label": flash.get("role_label", "Student"),
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
        return redirect("/")
    student = get_object_or_404(Student, roll_no=roll_no)
    branch = student.branch

    # Base prefetch: only CourseBranch rows for this student's branch
    base_cb = CourseBranch.objects.filter(branch=branch)

    # Build per-slot, per-category querysets
    slot_map = {}
    for slot in SLOTS:
        cat_map = {}
        for cat in [c["code"] for c in CATEGORIES]:
            qs = (
                Course.objects.filter(slot=slot, coursebranch__branch=branch, coursebranch__category=cat)
                .prefetch_related(Prefetch("coursebranch_set", queryset=base_cb, to_attr="cb_for_branch"))
                .distinct()
            )
            cat_map[cat] = qs
        slot_map[slot] = cat_map

    context = {
        "student": student,
        "categories": CATEGORIES,
        "slot_map": slot_map,
        "min_credit": 4,
        "max_credit": 22,
    }
    return render(request, "registration/pre_registration.html", context)

def check_status(request):
    return render(request, 'registration/check_status.html')

def update_registration(request):
    return render(request, 'registration/update_registration.html')

def registered_courses(request):
    return render(request, 'registration/registered_course.html')

def course_request(request):
    return render(request, 'instructor/course_request.html')

def view_courses(request):
    return render(request,'instructor/view_courses.html')

def update_courses(request):
    return render(request,'instructor/edit_courses.html')


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

# def custom_admin_students(request):
#     students = Student.objects.all()
#     if request.method=='POST':
#         firstname=request.POST['firstname']
#         lastname=request.POST['lastname']
#         roll_no=request.POST['roll_no']
#         email=request.POST['email']
#         department=request.POST['department']
#         branch=request.POST['branch']
#         password1=request.POST['password']
#         mobile_no=request.POST['mobile_no']
#         hashed_password = make_password(password1)

#         pattern1=re.compile(r'^(?:B|b|V|v|D|d|IM|im|MB|mb)\d{5}$')
#         pattern2=re.compile(r'^(?:B|b|V|v|D|d|IM|im|MB|mb)\d{5}@students\.iitmandi\.ac\.in$')


#         if(pattern1.match(roll_no) and pattern2.match(email) and (email[:len(roll_no)].lower()==roll_no.lower())):
            
#             try:
#                 Student.objects.create(
#                     first_name=firstname,
#                     last_name=lastname,
#                     email_id=email.lower(),
#                     roll_no=roll_no.lower(),
#                     password=hashed_password,
#                     department=department,
#                     branch=branch,
#                     mobile_no=mobile_no,

#                 )
#                 messages.success(request, 'Registration successful.')
#                 return redirect('/custom-admin/students/')  # Redirect to login page or another page
#             except IntegrityError:
#                 messages.error(request, "Student with this email or roll number already exists.")
#         else:
#             messages.error(request, "Invalid Roll No. or Institute Email")
#     return render(request, "admin/custom_admin_students.html", {"students": students})


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


def custom_admin_students_bulk_add(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return redirect("custom_admin_students_bulk_add")

        temp_file_path = default_storage.save(f"temp/{csv_file.name}", csv_file)
        added_count = 0
        error_rows = []

        try:
            with default_storage.open(temp_file_path, mode='r') as file:
                reader = csv.DictReader(file)
                required_fields = [
                    "first_name", "last_name", "email_id", "password",
                    "roll_no", "department", "branch", "mobile_no"
                ]
                for idx, row in enumerate(reader, start=2):  # header=1, first data row=2
                    if not all(row.get(f) for f in required_fields):
                        error_rows.append(f"Row {idx}: Missing required fields.")
                        continue

                    # Normalize codes from CSV (accept 'scee' or 'SCEE', 'cse' or 'CSE')
                    dept_code = (row["department"] or "").strip().upper()
                    br_code = (row["branch"] or "").strip()  # Case-sensitive for your Branch codes
                    # If branch codes in CSV are lower, normalize similarly:
                    # br_code = br_code.upper()

                    # Resolve FKs
                    try:
                        dept = Department.objects.get(code=dept_code)
                    except Department.DoesNotExist:
                        error_rows.append(f"Row {idx}: Department code '{dept_code}' not found.")
                        continue

                    try:
                        br = Branch.objects.get(name=br_code)
                    except Branch.DoesNotExist:
                        error_rows.append(f"Row {idx}: Branch code '{br_code}' not found.")
                        continue

                    try:
                        student, created = Student.objects.get_or_create(
                            roll_no=row["roll_no"].strip().lower(),
                            defaults={
                                "first_name": row["first_name"].strip(),
                                "last_name": row["last_name"].strip(),
                                "email_id": row["email_id"].strip().lower(),
                                "password": make_password(row["password"]),  # hash here
                                "department": dept,
                                "branch": br,
                                "mobile_no": (row["mobile_no"].strip() or None),
                            },
                        )
                        if created:
                            added_count += 1
                        else:
                            error_rows.append(
                                f"Row {idx}: Student with roll_no '{row['roll_no']}' already exists."
                            )
                    except IntegrityError as e:
                        error_rows.append(f"Row {idx}: Integrity error: {e}")
                    except Exception as e:
                        error_rows.append(f"Row {idx}: {str(e)}")
        finally:
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


# def custom_admin_admins(request):
#     return render(request, "admin/custom_admin_admins.html")

# def custom_admin_branches(request):
#     return render(request, "admin/custom_admin_branches.html")

# def custom_admin_courses(request):
#     return render(request, "admin/custom_admin_courses.html")

# def custom_admin_coursebranches(request):
#     return render(request, "admin/custom_admin_coursebranches.html")



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
        return redirect("custom_admin_courses")

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