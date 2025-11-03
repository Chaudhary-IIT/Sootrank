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
from django.urls import path, include
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
    path("custom-admin/prereg/", views.custom_admin_preregistration, name="admin_preregistration"),
    path("custom-admin/prereg/deadline/", views.admin_prereg_deadline, name="admin_prereg_deadline"),
    path("custom-admin/prereg/enrollments/", views.admin_prereg_enrollments, name="admin_prereg_enrollments"),
    path("custom-admin/prereg/swap/", views.admin_prereg_swap, name="admin_prereg_swap"),
    path("custom-admin/prereg/reports/", views.admin_prereg_reports, name="admin_prereg_reports"),
    path("custom-admin/prereg/reports/<str:code>/excel/", views.export_course_excel, name="export_course_excel"),
    path("custom-admin/prereg/reports/<str:code>/pdf/", views.export_course_pdf, name="export_course_pdf"),
    # other urls
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
    path("students_dashboard/registered_courses/", views.student_registered_courses, name="registered_courses"),

    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("ajax/branches-json/", views.ajax_branches_json, name="ajax_branches_json"),
    #--------
    path("instructor/<str:course_code>/roster/<str:semester>/", views.course_roster, name="course_roster"),
    path("instructor/schema/courses/", views.instructor_schema_courses, name="view_schema_courses"),
    path("instructor/<str:course_code>/scheme/", views.edit_assessment_scheme, name="edit_assessment_scheme"),
    path("instructor/<str:course_code>/scheme/<int:component_id>/update/", views.update_component, name="update_component"),
    path("instructor/<str:course_code>/scheme/<int:component_id>/delete/", views.delete_component, name="delete_component"),
    #-----------
    path('instructor/marks/<int:faculty_id>/', views.faculty_marks_courses, name='faculty_marks_courses'),
    path('instructor/marks/course/<int:course_id>/', views.enter_marks, name='enter_marks'),
    path('courses/<int:course_id>/marks/overview/', views.course_marks_overview, name='course_marks_overview'),
    path('courses/<int:course_id>/marks/update/', views.update_mark_cell, name='update_mark_cell'),
    path('faculty/<int:faculty_id>/courses/', views.all_courses, name='grading_courses'),
    path('courses/<str:course_code>/grades/assign/',views.assign_grades_csv, name='assign_grades_csv'),
    path('courses/<str:course_code>/grades/results/', views.grade_results, name='grade_results'),
    #------------
    path('student/results/<str:roll_no>/', views.student_result_semester_list, name='student_result_semester_list'),
    path('student/results/view/<int:student_id>/<int:semester>/', views.student_view_results, name='student_view_results'),
    path('student/results/pdf/<int:student_id>/<int:semester>/', views.student_result_pdf, name='student_result_pdf'),
    #------------
    path('custom-admin/grades/', views.admin_grade_management, name='admin_grade_management'),
    path('custom-admin/grades/assign/<str:course_code>/', views.admin_assign_grades, name='admin_assign_grades'),
    path('custom-admin/grades/save/<str:course_code>/', views.admin_save_grades, name='admin_save_grades'),
    #-----------(Database Management- Admin)
    path('custom-admin/database/', views.database_management_view, name='database_management'),
    path('custom-admin/database/edit/<str:record_type>/<int:record_id>/', views.edit_database_record, name='edit_database_record'),
    path('custom-admin/database/delete/<str:record_type>/<int:record_id>/', views.delete_database_record, name='delete_database_record'),
    path('custom-admin/database/export/', views.export_page_view, name='export_page'),
    path('custom-admin/database/export-filtered/', views.export_filtered_data, name='export_filtered_data'),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 