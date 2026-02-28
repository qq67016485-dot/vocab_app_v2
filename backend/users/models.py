from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        TEACHER = 'TEACHER', 'Teacher'
        STUDENT = 'STUDENT', 'Student'

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.STUDENT)

    native_language = models.CharField(
        max_length=10,
        choices=settings.SUPPORTED_LANGUAGES,
        default='zh-CN',
        help_text='For students: determines which translations are shown.',
    )

    daily_question_limit = models.IntegerField(
        default=20,
        help_text='The maximum number of questions a student can answer per day.',
    )

    lexile_min = models.IntegerField(
        default=0,
        help_text='The minimum Lexile score for questions shown to this student.',
    )
    lexile_max = models.IntegerField(
        default=2000,
        help_text='The maximum Lexile score for questions shown to this student.',
    )

    students = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='teachers',
    )

    current_practice_streak = models.IntegerField(default=0)
    last_practice_date = models.DateField(null=True, blank=True)
    streak_freezes_available = models.IntegerField(
        default=2,
        help_text='Number of times a student can miss a day without breaking their streak.',
    )

    xp_points = models.IntegerField(default=0)
    level = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class StudentGroup(models.Model):
    name = models.CharField(max_length=150)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_groups',
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='enrolled_groups',
        blank=True,
        limit_choices_to={'role': CustomUser.Role.STUDENT},
    )
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('name', 'teacher')
        ordering = ['name']

    def __str__(self):
        return f"'{self.name}' (Teacher: {self.teacher.username})"
