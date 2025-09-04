"""
URL configuration for Sootrank project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('custom-admin/', views.custom_admin_home, name='custom_admin_home'),
    path('custom-admin/students/', views.custom_admin_students, name='custom_admin_students'),
    path('custom-admin/students/bulk_add/', views.custom_admin_students_bulk_add, name='custom_admin_students_bulk_add'),
    path('custom-admin/faculty/', views.custom_admin_faculty, name='custom_admin_faculty'),
    path('custom-admin/students/delete/<str:roll_no>/', views.delete_student_by_roll, name='delete_student_by_roll'),
    path('custom-admin/students/edit/<str:roll_no>/', views.custom_admin_edit_student, name='custom_admin_edit_student'),
    path('custom-admin/faculty/delete/<int:faculty_id>/', views.delete_faculty, name='delete_faculty'),
    path('custom-admin/faculty/edit/<int:faculty_id>/', views.custom_admin_edit_faculty, name='custom_admin_edit_faculty'),
    path('',views.login),
    path('login/', views.login, name='login'),
    path('register/',views.register),
    # path('auth/success/', views.auth_success, name='auth_success'),
    path("students_dashboard/", views.students_dashboard, name="students_dashboard"),
    path("students_dashboard/profile/", views.student_profile, name="student_profile"),
    path("student/profile/edit/", views.student_edit_profile, name="student_edit_profile"),
    path("faculty_dashboard/", views.faculty_dashboard, name="faculty_dashboard"),
    path("faculty_dashboard/profile/", views.faculty_profile, name="faculty_profile"),
    path("faculty/profile/edit/", views.faculty_edit_profile, name="faculty_edit_profile"),
    path('student/bulk-upload/', views.student_bulk_upload, name='registration_student_bulk_upload'),
    path("students_dashboard/registration/pre/", views.pre_registration, name="prereg_page"),
    path("students_dashboard/registration/status/", views.check_status, name="check_status_page"),
    path("students_dashboard/registration/update/", views.update_registration, name="update_reg_page"),
    path("students_dashboard/registrated_courses/", views.registered_courses, name="registered_courses"),
    path("faculty_dashboard/course_request", views.course_request, name="course_request"),
    path("faculty_dashboard/view_courses", views.view_courses, name="view_courses"),
    path("faculty_dashboard/update_courses", views.update_courses, name="update_courses"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout")
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 