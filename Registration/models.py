from django.db import models
from django.contrib.auth.hashers import make_password

GRADE_POINTS = {
    "A": 10,
    "A-": 9,
    "B": 8,
    "B-": 7,
    "C": 6,
    "C-": 5,
    "D": 4,
    "F": 0,
    "FS": 0  # Fail due to attendance
}


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
    last_name=models.CharField(max_length=255,null=True)
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
    status=models.CharField(max_length=20,default="Yes")
    slot = models.CharField(max_length=2, choices=SLOT_CHOICES)
    branches = models.ManyToManyField(Branch, through="CourseBranch", related_name="courses")
    faculties = models.ManyToManyField(Faculty, related_name="courses")

    


class Student(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255,null=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    roll_no = models.CharField(max_length=10, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)  # Student linked to department
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True)  # Student linked to branch
    semester = models.IntegerField(null=True,default=1)
    mobile_no = models.BigIntegerField(null=True)
    courses = models.ManyToManyField(Course, through="StudentCourse", related_name="students")

    def save(self, *args, **kwargs):
    # Hash password only if it’s not already hashed
        if not self.password.startswith('pbkdf2_sha256$'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)
    
    def get_semester_courses(self, semester):
        # Only approved (enrolled or completed) courses are considered
        return self.enrollments.filter(semester=semester, status__in=['ENR', 'CMP'])

    def calculate_semester_metrics(self, semester):
        """
        Calculate semester metrics (SGPA, RCR, ECR, STCR) from approved enrollments only.
        Pass/Fail courses:
        - Count in ECR if passed
        - Do NOT count in RCR or STCR (no impact on SGPA)
        """
        # Only approved (ENR/CMP) enrollments are included
        enrollments = self.enrollments.filter(semester=semester, status__in=['ENR', 'CMP'])
        rcr, ecr, stcr = 0, 0, 0

        for enr in enrollments:
            credits = enr.course.credits or 0

            if enr.is_pass_fail:
                # Pass/Fail: earned if passed, never counted in RCR/STCR
                if (enr.outcome or '').upper() == "PAS":
                    ecr += credits
            else:
                # Graded: registered credits include approved enrollments
                rcr += credits
                points = GRADE_POINTS.get(enr.grade, 0)
                stcr += points * credits
                if (enr.outcome or '').upper() == "PAS" and points > 0:
                    ecr += credits

        sgpa = round(stcr / rcr, 2) if rcr else 0
        return {"RCR": rcr, "ECR": ecr, "STCR": stcr, "SGPA": sgpa}

    def calculate_cumulative_metrics(self):
        """
        Calculate cumulative metrics (CGPA, TRCR, TECR, TSTCR) from approved enrollments only.
        Pass/Fail courses:
        - Count in TECR if passed
        - Do NOT count in TRCR or TSTCR (no impact on CGPA)
        Handles retakes: only the latest passing attempt counts if an earlier attempt was failed.
        """
        # Only approved (ENR/CMP) enrollments across all semesters
        enrollments = self.enrollments.filter(status__in=['ENR', 'CMP']).order_by('semester', 'id')
        trcr, tecr, tstcr = 0, 0, 0
        latest_course = {}  # course_code -> dict(grade_points, credits, outcome)

        for enr in enrollments:
            course_code = enr.course.code
            credits = enr.course.credits or 0

            # Pass/Fail handling
            if enr.is_pass_fail:
                if (enr.outcome or '').upper() == "PAS":
                    tecr += credits
                continue

            # Graded handling with retakes
            grade_points = GRADE_POINTS.get(enr.grade, 0)
            prev = latest_course.get(course_code)

            if prev is None:
                # First seen attempt (by semester order)
                latest_course[course_code] = {
                    'grade_points': grade_points,
                    'credits': credits,
                    'outcome': (enr.outcome or '').upper(),
                }
                trcr += credits
                if (enr.outcome or '').upper() == "PAS":
                    tecr += credits
                tstcr += grade_points * credits
            else:
                # Only upgrade if previously failed (0 pts) and now earned points (>0)
                if prev['grade_points'] == 0 and grade_points > 0:
                    # Remove previous failed attempt contribution (TRCR counted credits, TSTCR was zero)
                    trcr -= prev['credits']
                    # Add new (passing) attempt
                    latest_course[course_code] = {
                        'grade_points': grade_points,
                        'credits': credits,
                        'outcome': (enr.outcome or '').upper(),
                    }
                    trcr += credits
                    if (enr.outcome or '').upper() == "PAS":
                        tecr += credits
                    tstcr += grade_points * credits
                else:
                    # Keep earlier attempt if it was already passing or new attempt not better
                    continue

        cgpa = round(tstcr / trcr, 2) if trcr else 0
        return {"TRCR": trcr, "TECR": tecr, "TSTCR": tstcr, "CGPA": cgpa}




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

class Category(models.Model):
    code = models.CharField(max_length=10, unique=True)  # "DC", "DE", "IC", "HSS", ...
    label = models.CharField(max_length=100)            # "Disciplinary Core (DC)", ...

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.label}"
    
class CourseBranch(models.Model):
    

    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    categories = models.ManyToManyField(Category, related_name="course_branches", blank=True)
    
    class Meta:
        unique_together = ("course", "branch")
        
    def __str__(self):
        if self.pk:
            codes = ", ".join(self.categories.values_list("code", flat=True))
        else:
            codes = ""
        return f"{self.course.name} - {self.branch.name} ({codes})"

class StudentCourse(models.Model):
    STATUS = [
        ("PND", "Pending"),
        ("ENR", "Enrolled"),
        ("CMP", "Completed"),
        ("DRP", "Dropped"),
    ]
    OUTCOME = [
        ("UNK", "Unknown"),
        ("PAS", "Pass"),
        ("FAI", "Fail"),
    ]

    GRADES = [(g, g) for g in GRADE_POINTS.keys()]  # Add grade choices list

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=3, choices=STATUS, default="PND")
    outcome = models.CharField(max_length=3, choices=OUTCOME, default="UNK")
    grade = models.CharField(
        max_length=3,
        null=True,
        blank=True,
        choices=GRADES
    )
    is_pass_fail = models.BooleanField(default=False)  # NEW: PF selection at registration/approval
    semester = models.IntegerField(null=True)  # e.g., 1, 2, ..., 8
    type = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        unique_together = ("student", "course", "semester")

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

class AssessmentComponent(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assessment_components")  # scope by course
    name = models.CharField(max_length=64)  # e.g., "Quiz 1", "Midsem", "Endsem", "Lab"
    weight = models.DecimalField(max_digits=5, decimal_places=2)  # percent weight like 10.00, 30.00
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)

    class Meta:
        unique_together = ("course", "name")

class AssessmentScore(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="assessment_scores")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assessment_scores")
    component = models.ForeignKey(AssessmentComponent, on_delete=models.CASCADE, related_name="scores")
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        unique_together = ("student", "course", "component")
