from http.client import HTTPResponse
from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from Registration.models import Student, Faculty
from django.contrib.auth.hashers import make_password

def login(request):
    return render(request, 'login.html')

def register(request):
    return render(request,'register.html')


def register_student(request):
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

        try:
            Student.objects.create(
                first_name=firstname,
                last_name=lastname,
                email_id=email,
                roll_no=roll_no,
                password=hashed_password,
                department=department,
                branch=branch
            )
            messages.success(request, 'Registration successful! Please log in.')
            return redirect('/')  # Redirect to login page or another page
        except IntegrityError:
            messages.error(request, "Student with this email or roll number already exists.")

    return render(request, 'register_student.html')


def register_faculty(request):
    if request.method=='POST':
        firstname=request.POST['firstname']
        lastname=request.POST['lastname']
        faculty_id=request.POST['faculty_id']
        email=request.POST['email']
        department=request.POST['department']
        password1=request.POST['password1']
        password2=request.POST['password2']
        hashed_password = make_password(password1)

        try:
            Faculty.objects.create(
                first_name=firstname,
                last_name=lastname,
                email_id=email,
                faculty_id=faculty_id,
                password=hashed_password,
                department=department
            )
            messages.success(request, 'Registration successful! Please log in.')
            return redirect('/')  # Redirect to login page or another page
        except IntegrityError:
            messages.error(request, "Student with this email or roll number already exists.")

    return render(request, 'register_faculty.html')