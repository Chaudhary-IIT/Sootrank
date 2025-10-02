from django import forms  
from .models import Branch, Department, Student, Faculty

class StudentEditForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["first_name", "last_name", "email_id", "mobile_no", "department", "branch", "profile_image"]  
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),  
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),  
            "email_id": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}),  
            "mobile_no": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Mobile number"}),  
            "department": forms.TextInput(attrs={"class": "form-control", "placeholder": "Department"}),  
            "branch": forms.TextInput(attrs={"class": "form-control", "placeholder": "Branch"}),  
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs) 
        self.fields["mobile_no"].required = False 
        self.fields["profile_image"].required = False 


class FacultyEditForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = ["first_name", "last_name", "email_id", "mobile_no", "department", "profile_image"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
            "email_id": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}),
            "mobile_no": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Mobile number"}),
            "department": forms.TextInput(attrs={"class": "form-control", "placeholder": "Department"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make mobile_no and profile_image optional in the form
        self.fields["mobile_no"].required = False
        self.fields["profile_image"].required = False

# class StudentForm(forms.ModelForm):
#     class Meta:
#         model = Student
#         fields = ["first_name","last_name","email_id","roll_no","department","branch","mobile_no","password","profile_image"]
#         widgets = {
#             "password": forms.PasswordInput(render_value=False),
#         }

#     # Optional: order dropdowns
#     department = forms.ModelChoiceField(queryset=Department.objects.all().order_by("code"))
#     branch = forms.ModelChoiceField(queryset=Branch.objects.all().order_by("name"))