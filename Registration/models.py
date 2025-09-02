from django.db import models
from django.contrib.auth.hashers import make_password

# Create your models here.
class Student(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    roll_no=models.CharField(max_length=10,unique=True)
    department=models.CharField(max_length=255)
    branch=models.CharField(max_length=255)
    mobile_no=models.BigIntegerField(null=True)

    def __str__(self):
        return self.roll_no
    
    def save(self, *args, **kwargs):
    # Hash password only if it’s not already hashed
        if not self.password.startswith('pbkdf2_sha256$'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)
    
class Faculty(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    # faculty_id=models.CharField(max_length=10,unique=True)
    department=models.CharField(max_length=255)
    mobile_no=models.BigIntegerField(null=True)

    def save(self, *args, **kwargs):
        # Hash password only if it’s not already hashed
        if not self.password.startswith('pbkdf2_sha256$'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.first_name+ " " +self.last_name

class Admins(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)

    def __str__(self):
        return self.first_name+ " " +self.last_name

    def save(self, *args, **kwargs):
        # Hash password only if it’s not already hashed
        if not self.password.startswith('pbkdf2_sha256$'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
class CourseBranch(models.Model):
    CORE_ELECTIVE_CHOICES = [
        ("DC", "Disciplinary Core (DC)"),
        ("DE", "Disciplinary Elective (DE)"),
        ("IC","Institute Core (IC)"),
        ("HSS","Humanities and Social Science (HSS)"),
        ("FE","Free Elective (FE)"),
        ("IKS","Indian Knowledge System (IKS)"),
        ("ISTP","Interactive Socio-Technical Practicum (ISTP)"),
        ("MTP","Major Technical Project (MTP)"),
    ]

    course = models.ForeignKey("Course", on_delete=models.CASCADE)
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE)
    category = models.CharField(max_length=4, choices=CORE_ELECTIVE_CHOICES)

    def __str__(self):
        return f"{self.course.title} - {self.branch.name} ({self.get_category_display()})"


class Course(models.Model):
    SLOT_CHOICES=[
        ("A","A"),
        ("B","B"),
        ("C","C"),
        ("D","D"),
        ("E","E"),
        ("F","F"),
        ("G","G"),
        ("H","H"),
        ("FS","FS"),
    ]
    code=models.CharField(max_length=255)
    name=models.CharField(max_length=255)
    credits=models.IntegerField()
    LTPC=models.CharField(max_length=20)
    slot = models.CharField(max_length=2, choices=SLOT_CHOICES)
    branches = models.ManyToManyField(Branch, through="CourseBranch", related_name="courses")
    faculties = models.ManyToManyField(Faculty, related_name="courses")

    
