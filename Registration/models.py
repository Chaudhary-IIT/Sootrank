from django.db import models
from django.contrib.auth.hashers import make_password

class Department(models.Model):
    SCHOOL_CHOICES = [
        ('SCEE', 'School of Computing and Electrical Engineering (SCEE)'),
        ('SMSS', 'School of Mathematics & Statistical Sciences (SMSS)'),
        ('SPS', 'School of Physical Sciences (SPS)'),
        ('SBB', 'School of Biosciences & Bioengineering (SBB)'),
        ('SCENE', 'School of Civil & Environmental Engineering (SCENE)'),
        ('SMME', 'School of Mechanical and Materials Engineering (SMME)'),
        ('SCS', 'School of Chemical Sciences (SCS)'),
    ]

    code = models.CharField(max_length=10, choices=SCHOOL_CHOICES, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    
class Branch(models.Model):
    BRANCHES = [
        ("CSE", "Computer Science and Engineering"),
        ("DSE", "Data Science and Engineering"),
        ("ME", "Mechanical Engineering"),
        ("CE", "Civil Engineering"),
        ("EE", "Electrical Engineering"),
        ("MVLSI", "Microelectronics and Very Large Scale Integration"),
        ("EP", "Engineering Physics"),
        ("GE", "General Engineering"),
        ("MnC", "Mathematics and Computing"),
        ("MSE", "Material Science and Engineering"),
        ("BioEng", "Bioengineering"),
        ("BS_CS","Bachelor of Science in Chemical Science")
    ]
    name = models.CharField(max_length=100, unique=True,choices=BRANCHES)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='branches',null=True)  # One-to-many

    def __str__(self):
        return self.name
    
class Faculty(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    # faculty_id=models.CharField(max_length=10,unique=True) 
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)  # Faculty linked to department
    mobile_no=models.BigIntegerField(null=True)

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

class Student(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    roll_no = models.CharField(max_length=10, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)  # Student linked to department
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True)  # Student linked to branch
    mobile_no = models.BigIntegerField(null=True)
    courses = models.ManyToManyField(Course, through="StudentCourse", related_name="students")

    def __str__(self):
        return self.roll_no
    
    def save(self, *args, **kwargs):
    # Hash password only if it’s not already hashed
        if not self.password.startswith('pbkdf2_sha256$'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)
    


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
from django.db import models


    
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

    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    category = models.CharField(max_length=4, choices=CORE_ELECTIVE_CHOICES)

    def __str__(self):
        return f"{self.course.name} - {self.branch.name} ({self.get_category_display()})"



class StudentCourse(models.Model):
    STATUS = [("ENR","Enrolled"), ("CMP","Completed"), ("DRP","Dropped")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    # optional branch snapshot (useful if course is tied to specific branch rules):
    status = models.CharField(max_length=3, choices=STATUS, default="ENR")
    grade = models.CharField(max_length=2, null=True, blank=True)  # if grading is tracked
    term = models.CharField(max_length=20, null=True, blank=True)  # e.g., "2025-ODD"

    class Meta:
        unique_together = ("student", "course", "term")  # adjust to your policy

class ProgramRequirement(models.Model):
    CATEGORY_CHOICES = [
        ("DC", "Disciplinary Core (DC)"),
        ("DE", "Disciplinary Elective (DE)"),
        ("IC","Institute Core (IC)"),
        ("HSS","Humanities and Social Science (HSS)"),
        ("FE","Free Elective (FE)"),
        ("IKS","Indian Knowledge System (IKS)"),
        ("ISTP","Interactive Socio-Technical Practicum (ISTP)"),
        ("MTP","Major Technical Project (MTP)"),
    ]
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="requirements")
    category = models.CharField(max_length=4, choices=CATEGORY_CHOICES)
    required_credits = models.PositiveIntegerField()
    # Optional if rules vary by admission year or track:
    # cohort = models.CharField(max_length=9, null=True, blank=True)  # e.g., "2025"

    class Meta:
        unique_together = ("branch", "category")

