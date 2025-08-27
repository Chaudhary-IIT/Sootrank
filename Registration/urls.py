from django.urls import path
from . import views

urlpatterns = [
    path('', views.login, name='login'),  # homepage goes to login
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('students_dashboard/', views.students_dashboard, name='students_dashboard'),
     path("add-course-offering/", views.add_course_offering, name="add_course_offering"),
    # later we’ll add professors_dashboard, course creation, etc.
]
