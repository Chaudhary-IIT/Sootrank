from django.db import models
from django.contrib.auth.hashers import make_password
from datetime import datetime
from django.utils import timezone


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
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255, null=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id = models.EmailField(max_length=255, unique=True)
    password = models.CharField(max_length=255)
    roll_no = models.CharField(max_length=10, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True)
    semester = models.IntegerField(null=True, default=1)
    mobile_no = models.BigIntegerField(null=True)
    courses = models.ManyToManyField(Course, through="StudentCourse", related_name="students")

    def calculate_current_semester(self):
        """
        Calculate current semester based on roll number and current date.
        Roll number format: b24001 where 24 = admission year (2024)
        July-December = Odd semesters (1, 3, 5, 7)
        January-June = Even semesters (2, 4, 6, 8)
        """
        if not self.roll_no or len(self.roll_no) < 3:
            return 1
        
        try:
            # Extract year from roll number (e.g., "b24001" -> "24" -> 2024)
            year_str = self.roll_no[1:3]
            admission_year = 2000 + int(year_str)
            
            # Get current date info
            current_date = datetime.now()
            current_year = current_date.year
            current_month = current_date.month
            
            # Calculate years since admission
            years_diff = current_year - admission_year
            
            # Determine semester within the academic year
            if current_month >= 7:  # July-December (Odd semester)
                semester_in_year = 1
            else:  # January-June (Even semester)
                semester_in_year = 2
            
            # Calculate total semester
            total_semester = (years_diff * 2) + semester_in_year
            
            # Cap between 1 and 8
            return max(1, min(total_semester, 8))
        
        except (ValueError, IndexError):
            return 1

    def update_semester(self):
        """
        Update the semester field with calculated current semester.
        Call this method to auto-update semester based on current date.
        """
        self.semester = self.calculate_current_semester()
        self.save(update_fields=['semester'])

    def save(self, *args, **kwargs):
        # Auto-calculate semester if not set or if you want it always updated
        if not self.semester:
            self.semester = self.calculate_current_semester()
        
        # Hash password only if it's not already hashed
        if not self.password.startswith('pbkdf2_sha256$'):
            self.password = make_password(self.password)
        
        super().save(*args, **kwargs)
    
    def get_semester_courses(self, semester):
        return self.enrollments.filter(semester=semester, status__in=['ENR', 'CMP'])

    def calculate_semester_metrics(self, semester):
        """
        - RCR: All attempted (registered) credits including pass/fail
        - ECR: Pass/fail courses count only if passed, regular require passing grade
        - STCR: Only regular, Pass/Fail counted as 0
        - SGPA: STCR / (RCR - pass/fail credits)
        """
        enrollments = self.enrollments.filter(semester=semester, status__in=['ENR', 'CMP'])

        rcr = ecr = stcr = 0
        pf_credits = 0  # Total Pass/Fail credits for the semester

        for enr in enrollments:
            credits = enr.course.credits or 0
            if enr.is_pass_fail:
                rcr += credits
                pf_credits += credits
                if (enr.outcome or '').upper() == "PAS":
                    ecr += credits
                # No addition to stcr for PF
            else:
                rcr += credits
                points = GRADE_POINTS.get(enr.grade, 0)
                stcr += points * credits
                if (enr.outcome or '').upper() == "PAS" and points > 0:
                    ecr += credits

        # SGPA denominator is only regular credits
        regular_rcr = rcr - pf_credits
        sgpa = round(stcr / regular_rcr, 2) if regular_rcr else 0
        return {"RCR": rcr, "ECR": ecr, "STCR": stcr, "SGPA": sgpa}


    def calculate_cumulative_metrics(self):
        """
        - TRCR: All attempted credits including pass/fail
        - TECR: Passed courses (including passed P/F)
        - TSTCR: Only regular, Pass/Fail counted as 0
        - CGPA: TSTCR / (TRCR - pass/fail credits)
        Handles latest attempt logic as before.
        """
        enrollments = self.enrollments.filter(status__in=['ENR', 'CMP']).order_by('semester', 'id')
        trcr = tecr = tstcr = 0
        latest_course = {}
        pf_credits = 0

        for enr in enrollments:
            course_code = enr.course.code
            credits = enr.course.credits or 0

            if enr.is_pass_fail:
                trcr += credits
                pf_credits += credits
                if (enr.outcome or '').upper() == "PAS":
                    tecr += credits
                continue

            grade_points = GRADE_POINTS.get(enr.grade, 0)
            prev = latest_course.get(course_code)

            if prev is None:
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
                if prev['grade_points'] == 0 and grade_points > 0:
                    trcr -= prev['credits']
                    latest_course[course_code] = {
                        'grade_points': grade_points,
                        'credits': credits,
                        'outcome': (enr.outcome or '').upper(),
                    }
                    trcr += credits
                    if (enr.outcome or '').upper() == "PAS":
                        tecr += credits
                    tstcr += grade_points * credits

        regular_trcr = trcr - pf_credits
        cgpa = round(tstcr / regular_trcr, 2) if regular_trcr else 0
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
    GRADES = [(g, g) for g in GRADE_POINTS.keys()]

    COURSE_MODE = [
        ("REG", "Regular"),
        ("PF", "Pass/Fail"),
        ("AUD", "Audit"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=3, choices=STATUS, default="PND")
    outcome = models.CharField(max_length=3, choices=OUTCOME, default="UNK")
    grade = models.CharField(max_length=3, null=True, blank=True, choices=GRADES)
    semester = models.IntegerField(null=True)
    type = models.CharField(max_length=10, null=True, blank=True)
    course_mode = models.CharField(max_length=3, choices=COURSE_MODE, default="REG")

    class Meta:
        unique_together = ("student", "course", "semester")

    def is_pass_fail(self):
        return self.course_mode == "PF"

    def is_audit(self):
        return self.course_mode == "AUD"

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


class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="attendance_records")
    total_classes = models.PositiveIntegerField(default=0)
    attended_classes = models.PositiveIntegerField(default=0)

    @property
    def attendance_percent(self):
        if self.total_classes == 0:
            return 0
        return round((self.attended_classes / self.total_classes) * 100, 1)

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student.roll_no} - {self.course.code}: {self.attendance_percent}%"


class Timetable(models.Model):
    DAYS = [
        ("Monday", "Monday"),
        ("Tuesday", "Tuesday"),
        ("Wednesday", "Wednesday"),
        ("Thursday", "Thursday"),
        ("Friday", "Friday"),
        ("Saturday", "Saturday"),
        ("Sunday", "Sunday"),
    ]

    course = models.ForeignKey("Course", on_delete=models.CASCADE, related_name="timetables")
    faculty = models.ForeignKey("Faculty", on_delete=models.SET_NULL, null=True, blank=True, related_name="timetables")
    day = models.CharField(max_length=10, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["day", "start_time"]
        unique_together = ("course", "day", "start_time", "end_time")

    def __str__(self):
        return f"{self.course.code} | {self.day} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"


class FeeRecord(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Paid", "Paid"),
        ("Failed", "Failed"),
    ]

    student = models.ForeignKey("Student", on_delete=models.CASCADE, related_name="fees")
    semester = models.IntegerField()
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")

    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    payment_time = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.roll_no} | Sem {self.semester} | {self.status}"

    def receipt_number(self):
        # Simple receipt id — you can change format
        return f"SR-{self.pk:06d}"