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
    path('custom-admin/branches/', views.custom_admin_branch, name='custom_admin_branch'),
    path('custom-admin/students/delete/<str:roll_no>/', views.delete_student_by_roll, name='delete_student_by_roll'),
    path('custom-admin/students/edit/<str:roll_no>/', views.custom_admin_edit_student, name='custom_admin_edit_student'),
    path('custom-admin/faculty/', views.custom_admin_faculty, name='custom_admin_faculty'),
    path('custom-admin/faculty/bulk_add/', views.custom_admin_faculty_bulk_add, name='custom_admin_faculty_bulk_add'),
    path('custom-admin/faculty/delete/<int:faculty_id>/', views.delete_faculty, name='delete_faculty'),
    path('custom-admin/faculty/edit/<int:faculty_id>/', views.custom_admin_edit_faculty, name='custom_admin_edit_faculty'),
    path("custom-admin/courses/", views.custom_admin_courses, name="custom_admin_courses"),
    path('custom-admin/courses/bulk/', views.custom_admin_courses_bulk, name='custom_admin_courses_bulk'),
    path("custom-admin/courses/<int:course_id>/edit/", views.custom_admin_edit_course, name="custom_admin_edit_course"),
    path("custom-admin/courses/<int:course_id>/delete/", views.delete_course, name="delete_course"),
    path("custom-admin/courses/<int:course_id>/faculties/", views.manage_course_faculties, name="manage_course_faculties"),
    path("custom-admin/course-branches/", views.course_branch_index, name="course_branch_index"),
    path("custom-admin/course-branches/<int:course_id>/", views.manage_course_branches, name="manage_course_branches"),
    path('custom-admin/course-branches/bulk/', views.bulk_upload_course_branch, name='bulk_upload_course_branch'),
    path("custom-admin/requirements/", views.requirements_index, name="requirements_index"),
    path("custom-admin/requirements_bulk/", views.bulk_upload_program_requirements, name="custom_admin_requirements_bulk"),
    path("custom-admin/requirements/<int:branch_id>/", views.manage_branch_requirements, name="manage_branch_requirements"),
    path("custom-admin/course-instructors",views.course_instructors_assign,name='course_instructors_assign'),
    path("custom-admin/course-instructors-bulk",views.course_instructors_assign_bulk,name='course_instructors_assign_bulk'),
    path('',views.login),
    path('login/', views.login, name='login'),
    path('register/',views.register),
    path("students_dashboard/", views.students_dashboard, name="students_dashboard"),
    path("students_dashboard/profile/", views.student_profile, name="student_profile"),
    path("student/profile/edit/", views.student_edit_profile, name="student_edit_profile"),
    path("faculty_dashboard/", views.faculty_dashboard, name="faculty_dashboard"),
    path("faculty_dashboard/profile/", views.faculty_profile, name="faculty_profile"),
    path("faculty/profile/edit/", views.faculty_edit_profile, name="faculty_edit_profile"),
    path("students_dashboard/registration/pre/", views.pre_registration, name="prereg_page"),
    #------
    path("students_dashboard/registration/submit/", views.submit_preregistration, name="submit_preregistration"),
    path("faculty_dashboard/approvals/", views.instructor_requests, name="instructor_requests"),
    path("faculty_dashboard/approvals/action/", views.instructor_request_action, name="instructor_request_action"),
    path("faculty_dashboard/approvals/bulk/", views.instructor_bulk_action, name="instructor_bulk_action"),
    path("custom-admin/advisor/approvals/action/", views.advisor_request_action, name="advisor_request_action"),
    #-----
    path("students_dashboard/registration/status/", views.check_status, name="check_status_page"),    
    path("faculty_dashboard/courses/", views.instructor_courses, name="instructor_courses"),
    path("faculty_dashboard/courses/<str:course_code>/<str:semester>/", views.course_roster , name="course_roster"),
    path("students_dashboard/registration/apply_pf_changes/", views.apply_pf_changes, name="apply_pf_changes"),
    path("students_dashboard/registrated_courses/", views.registered_courses, name="registered_courses"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("ajax/branches-json/", views.ajax_branches_json, name="ajax_branches_json"),
    
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 