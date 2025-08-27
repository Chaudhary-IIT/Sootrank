
from http.client import HTTPResponse
from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from Registration.models import Student, Faculty
from django.contrib.auth.hashers import make_password,check_password
import re
from .forms import CourseOfferingForm


def login(request):
    if request.method == "POST":
        identifier = request.POST['identifier'].lower()   # could be roll_no OR email
        password = request.POST['password']

        try:
            # Try matching roll_no first
            if Student.objects.filter(roll_no=identifier).exists():
                this_user = Student.objects.get(roll_no=identifier)
            # If not roll_no, then check email
            elif Student.objects.filter(email_id=identifier).exists():
                this_user = Student.objects.get(email_id=identifier)
            else:
                messages.error(request, "Invalid Roll No/Email or Password")
                return render(request, 'login.html')

            # Now check password
            if (check_password(password, this_user.password)):   
                return redirect("/students_dashboard/", roll_no=this_user.roll_no)
            else:
                messages.error(request, "Invalid Roll No/Email or Password")

        except Student.DoesNotExist:
            messages.error(request, "First Register Yourself")
            return render(request, 'login.html')

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


def add_course_offering(request):
    if request.method == "POST":
        form = CourseOfferingForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("success_page")  # replace with dashboard or list page
    else:
        form = CourseOfferingForm()
    return render(request, "Registration/add_course_offering.html", {"form": form})