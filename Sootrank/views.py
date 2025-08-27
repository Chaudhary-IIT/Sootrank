from http.client import HTTPResponse
from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from Registration.models import Student, Faculty, Admins
from django.contrib.auth import authenticate , login as auth_login
from django.contrib.auth.hashers import make_password,check_password
import re

def login(request):
    if request.method == "POST":
        identifier = request.POST['identifier'].lower()
        password = request.POST['password']

        try:
            if Admins.objects.filter(email_id=identifier).exists():
                Admin = Admins.objects.get(email_id=identifier)
                if check_password(password, Admin.password):
                    return redirect("/admin/")
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
                    return redirect("/faculty_dashboard/")   # Faculty also goes to admin
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
                return redirect("/students_dashboard/")
            else:
                messages.error(request, "Invalid Student Credentials")
        except Student.DoesNotExist:
            messages.error(request, "First Register Yourself")

    return render(request, "login.html")
            # # Try matching roll_no first
            # if Student.objects.filter(roll_no=identifier).exists():
            #     this_user = Student.objects.get(roll_no=identifier)
            # # If not roll_no, then check email
            # elif Student.objects.filter(email_id=identifier).exists():
            #     this_user = Student.objects.get(email_id=identifier)
            # else:
            #     messages.error(request, "Invalid Username")
            #     return render(request, 'login.html')

            # Now check password
        #     if (check_password(password, this_user.password)):   
        #         return redirect("/students_dashboard/", roll_no=this_user.roll_no)
        #     else:
        #         messages.error(request, "Invalid Roll No/Email or Password")

        # except Student.DoesNotExist:
        #     messages.error(request, "First Register Yourself")
        #     return render(request, 'login.html')

    return render(request, 'login.html')



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
    # student = Student.objects.get(roll_no=roll_no)
    return render(request,'students_dashboard.html')

def faculty_dashboard(request):
    # student = Student.objects.get(roll_no=roll_no)
    return render(request,'faculty_dashboard.html')
