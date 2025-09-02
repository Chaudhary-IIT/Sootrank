from django.contrib import admin
from . models import Student,Faculty,Admins,Course

from django.shortcuts import render, redirect
from django.urls import path
from django import forms
import csv

# Form for uploading CSV
class UploadCSVForm(forms.Form):
    csv_file = forms.FileField()

class StudentAdmin(admin.ModelAdmin):
    list_display = ('roll_no','first_name','last_name', 'branch',)
    search_fields = ('roll_no',)


    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("bulk-upload/", self.admin_site.admin_view(self.bulk_upload))
        ]
        return custom_urls + urls

    def bulk_upload(self, request):
        if request.method == "POST":
            form = UploadCSVForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                decoded_file = csv_file.read().decode("utf-8").splitlines()
                reader = csv.DictReader(decoded_file)

                for row in reader:
                    Student.objects.create(
                        first_name=row["first_name"],
                        last_name=row["last_name"],
                        email_id=row["email_id"],
                        mobile_no=row["mobile_no"],
                        department=row["department"],
                    )
                self.message_user(request, "Students uploaded successfully.")
                return redirect("..")  # back to students page
        else:
            form = UploadCSVForm()

        return render(request, "admin/bulk_upload.html", {"form": form})


admin.site.site_header = "SOOTRANK Admin Dashboard"
admin.site.index_title = "Welcome to SOOTRANK Administration"
admin.site.site_title = "SOOTRANK Admin"


class MyAdminSite(admin.AdminSite):
    class Media:
        css = {
            'all': ('css/admin.css',)
        }
        # js = ('js/admin.js',)


class FacultyAdmin(admin.ModelAdmin):
    list_display = ('first_name','last_name','department',)
    search_fields = ('first_name',)


# Register your models here.
admin.site.register(Student,StudentAdmin)
admin.site.register(Faculty,FacultyAdmin)
admin.site.register(Admins)
admin.site.register(Course)

