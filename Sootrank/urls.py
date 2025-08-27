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
from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',views.login),
    path('login/', views.login, name='login'),
    path('register/',views.register),
    path("students_dashboard/", views.students_dashboard, name="students_dashboard"),
    path("faculty_dashboard/", views.faculty_dashboard, name="faculty_dashboard"),
    # path("logout/", views.logout_view, name="logout"),
    # path("catalog/", views.catalog, name="catalog"),
    # path("select-courses/", views.select_courses, name="select_courses"),
    # path("register-courses/", views.register_courses, name="register_courses"),
    # path("profile/update/", views.profile_update, name="profile_update"),
    # path("pay-fees/", views.pay_fees, name="pay_fees"),
    # path("support/ticket/", views.support_ticket, name="support_ticket"),
    # path("tickets/", views.tickets, name="tickets"),
    # path("notifications/", views.notifications, name="notifications"),
    # path("change-password/", views.change_password, name="change_password"),
]
