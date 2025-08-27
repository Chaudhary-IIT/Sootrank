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
    mobile_no=models.IntegerField(null=True)

    def __str__(self):
        return self.roll_no
    
class Faculty(models.Model):
    first_name=models.CharField(max_length=255)
    last_name=models.CharField(max_length=255)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    email_id=models.EmailField(max_length=255,unique=True)
    password=models.CharField(max_length=255)
    # faculty_id=models.CharField(max_length=10,unique=True)
    department=models.CharField(max_length=255)
    mobile_no=models.IntegerField(null=True)

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

