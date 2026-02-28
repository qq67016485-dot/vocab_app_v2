from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, StudentGroup


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Custom User Info', {
            'fields': (
                'role',
                'native_language',
                'daily_question_limit',
                'lexile_min',
                'lexile_max',
                'students',
                'current_practice_streak',
                'last_practice_date',
                'streak_freezes_available',
                'xp_points',
                'level',
            ),
        }),
    )
    list_display = (
        'username',
        'email',
        'role',
        'native_language',
        'daily_question_limit',
        'is_staff',
        'current_practice_streak',
        'xp_points',
        'level',
    )
    list_filter = ('role', 'native_language', 'is_staff', 'is_superuser', 'groups')
    filter_horizontal = ('students',)


@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'student_count', 'created_at')
    list_filter = ('teacher',)
    search_fields = ('name', 'teacher__username', 'students__username')
    filter_horizontal = ('students',)
    readonly_fields = ('created_at', 'updated_at')

    def student_count(self, obj):
        return obj.students.count()
    student_count.short_description = 'Number of Students'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('students')


admin.site.register(CustomUser, CustomUserAdmin)
