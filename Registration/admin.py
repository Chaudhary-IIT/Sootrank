from django.contrib import admin
from . models import Student,Faculty,Admins
# Register your models here.
admin.site.register(Student)
admin.site.register(Faculty)
admin.site.register(Admins)
