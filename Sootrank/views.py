from http.client import HTTPResponse
from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from Registration.models import Branch, Department, Student, Faculty, Admins
from django.contrib.auth import authenticate , login as auth_login
from django.contrib.auth.hashers import make_password,check_password
from urllib.parse import urlencode
from django.core.files.storage import default_storage
import re
from Registration.forms import FacultyEditForm, StudentEditForm
import csv

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
    return render(request,'registration/pre_registration.html')

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


def custom_admin_students_bulk_add(request):
    return render(request, "admin/bulk_add.html")

def custom_admin_faculty(request):
    faculties = Faculty.objects.all()
    if request.method=='POST':
        first_name=request.POST['firstname']
        last_name=request.POST['lastname']
        email_id=request.POST['email']
        department=request.POST['department']
        password1=request.POST['password']
        hashed_password = make_password(password1)

        pattern=re.compile(r'^[a-zA-Z0-9._%+-]+@iitmandi\.ac\.in$')

        if(pattern.match(email_id)):
            try:
                Faculty.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    email_id=email_id.lower(),
                    password=hashed_password,
                    department=department,
                )
                messages.success(request, 'Faculty added successfully.')
                return redirect('/custom-admin/faculty/')  # Redirect to login page or another page
            except IntegrityError:
                messages.error(request, "Faculty with this email already exists.")
        else:
            messages.error(request, "Invalid Institute Email")
    return render(request, "admin/custom_admin_faculty.html", {"faculties": faculties})


def custom_admin_students_bulk_add(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return redirect("custom_admin_students_bulk_add")

        # Save uploaded file temporarily
        temp_file_path = default_storage.save(
            f"temp/{csv_file.name}", csv_file
        )
        added_count = 0
        error_rows = []

        with default_storage.open(temp_file_path, mode='r') as file:
            reader = csv.DictReader(file)
            required_fields = [
                "first_name", "last_name", "email_id", "password",
                "roll_no", "department", "branch", "mobile_no"
            ]
            for idx, row in enumerate(reader, start=2):  # start at 2 for header
                # Validate required fields
                if not all(row.get(f) for f in required_fields):
                    error_rows.append(f"Row {idx}: Missing required fields.")
                    continue
                try:
                    student, created = Student.objects.get_or_create(
                        roll_no=row["roll_no"],
                        defaults={
                            "first_name": row["first_name"],
                            "last_name": row["last_name"],
                            "email_id": row["email_id"],
                            "password": row["password"],
                            "department": row["department"],
                            "branch": row["branch"],
                            "mobile_no": row["mobile_no"] or None,
                        }
                    )
                    if created:
                        added_count += 1
                    else:
                        error_rows.append(
                            f"Row {idx}: Student with roll_no '{row['roll_no']}' already exists."
                        )
                except Exception as e:
                    error_rows.append(f"Row {idx}: {str(e)}")

        default_storage.delete(temp_file_path)

        if added_count:
            messages.success(request, f"Successfully added {added_count} students.")
        for error in error_rows:
            messages.error(request, error)
        return redirect("custom_admin_students_bulk_add")
    
    # GET: Render the bulk add page
    return render(request, "admin/bulk_add.html")

def delete_student_by_roll(request, roll_no):
    student = get_object_or_404(Student, roll_no=roll_no)
    if request.method == "POST":
        student.delete()
        return redirect('custom_admin_students')

def custom_admin_edit_student(request, roll_no):
    student = get_object_or_404(Student, roll_no=roll_no)
    if request.method == "POST":
        # Update student details
        student.roll_no = request.POST.get("roll_no")
        student.first_name = request.POST.get("first_name")
        student.last_name = request.POST.get("last_name")
        student.email_id = request.POST.get("email_id")
        student.department = request.POST.get("department")
        student.branch = request.POST.get("branch")
        student.mobile_no = request.POST.get("mobile_no")
        student.save()
        messages.success(request, "Student details updated successfully.")
        return redirect("custom_admin_students")
    return render(request, "admin/custom_admin_edit_student.html", {"student": student})

def delete_faculty(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    if request.method == "POST":
        faculty.delete()
        return redirect('custom_admin_faculty')
    
def custom_admin_edit_faculty(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    if request.method == "POST":
        faculty.first_name = request.POST.get("first_name")
        faculty.last_name = request.POST.get("last_name")
        faculty.email_id = request.POST.get("email_id")
        faculty.department = request.POST.get("department")
        faculty.mobile_no = request.POST.get("mobile_no")
        faculty.password = request.POST.get("password")
        faculty.password = make_password(faculty.password)
        faculty.profile_image = request.FILES.get("profile_image") or faculty.profile_image
        faculty.save()
        messages.success(request, "Faculty details updated successfully.")
        return redirect("custom_admin_faculty")
    return render(request, "admin/custom_admin_edit_faculty.html", {"faculty": faculty})

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
            return redirect("custom_admin_branches")

        try:
            dept = Department.objects.get(pk=dept_id)
        except Department.DoesNotExist:
            messages.error(request, "Selected department does not exist.")
            return redirect("custom_admin_branches")

        valid_codes = {c for c, _ in branch_choices}
        if branch_code not in valid_codes:
            messages.error(request, "Invalid branch selection.")
            return redirect("custom_admin_branches")

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
        return redirect("custom_admin_branches")

    return render(request, "admin/custom_admin_branch.html", {
        "branches": branches,
        "departments": departments,
        "branch_choices": branch_choices,
    })
