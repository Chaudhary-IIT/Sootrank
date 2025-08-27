from django.db import models


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
    mobile_no=models.IntegerField(null=True)

    def __str__(self):
        return self.roll_no
    
class Faculty(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    faculty_id=models.CharField(max_length=10,unique=True)
    department=models.CharField(max_length=255)
    mobile_no=models.IntegerField(null=True)

    def __str__(self):
        return self.first_name+ " " +self.last_name





class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Course(models.Model):
    course_code = models.CharField(max_length=20, unique=True)
    course_name = models.CharField(max_length=200)
    credits = models.IntegerField()

    def __str__(self):
        return f"{self.course_code} - {self.course_name}"

class CourseOffering(models.Model):
    YEAR_CHOICES = [(1, "1st Year"), (2, "2nd Year"), (3, "3rd Year"), (4, "4th Year")]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="offerings")
    years = models.ManyToManyField("Year")
    branches = models.ManyToManyField(Branch)

    def __str__(self):
        return f"{self.course.course_code}"
    
class Year(models.Model):
    number = models.IntegerField(choices=[(1,"1st"),(2,"2nd"),(3,"3rd"),(4,"4th")], unique=True)

    def __str__(self):
        return f"{self.number} Year"



