from django.contrib import admin
from . models import Student,Faculty,Admins,Course,CourseBranch,StudentCourse,Department,Branch,ProgramRequirement
from django.contrib.admin import AdminSite
from django.shortcuts import render, redirect
from django.urls import path
from django import forms
import csv

# Form for uploading CSV
class UploadCSVForm(forms.Form):
    csv_file = forms.FileField()

class MyAdminSite(AdminSite):
    index_template = 'yourapp/admin_dashboard.html'
my_admin_site = MyAdminSite()


admin.site.site_header = "SOOTRANK Admin Dashboard"
admin.site.index_title = "Welcome to SOOTRANK Administration"
admin.site.site_title = "SOOTRANK Admin"


# class MyAdminSite(admin.AdminSite):
#     class Media:
#         css = {
#             'all': ('css/admin.css',)
#         }
#         # js = ('js/admin.js',)


class FacultyAdmin(admin.ModelAdmin):
    list_display = ('first_name','last_name','department',)
    search_fields = ('first_name',)


# Register your models here.
admin.site.register(Student)
admin.site.register(Faculty,FacultyAdmin)
admin.site.register(Admins)
admin.site.register(Course)
admin.site.register(CourseBranch)
admin.site.register(StudentCourse)
admin.site.register(Department)
admin.site.register(Branch)
admin.site.register(ProgramRequirement)

