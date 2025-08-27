from django import forms
from .models import Course, Branch

YEAR_CHOICES = [
    (1, "1st Year"),
    (2, "2nd Year"),
    (3, "3rd Year"),
    (4, "4th Year"),
]

class CourseOfferingForm(forms.Form):
    course_code = forms.ModelChoiceField(
        queryset=Course.objects.all(),
        label="Course Code"
    )
    years = forms.MultipleChoiceField(
        choices=YEAR_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Select Years"
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Branches"
    )
