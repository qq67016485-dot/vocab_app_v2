from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    user_views,
    practice_views,
    dashboard_views,
    instructional_views,
    teacher_views,
    group_views,
    generation_views,
)

router = DefaultRouter()
router.register(r'words', teacher_views.WordViewSet, basename='word')
router.register(r'word-sets', teacher_views.WordSetViewSet, basename='wordset')
router.register(r'curricula', teacher_views.CurriculumViewSet, basename='curriculum')
router.register(r'levels', teacher_views.LevelViewSet, basename='level')
router.register(r'groups', group_views.StudentGroupViewSet, basename='studentgroup')

urlpatterns = [
    path('', include(router.urls)),

    # Auth
    path('csrf/', user_views.get_csrf_token, name='get-csrf-token'),
    path('login/', user_views.custom_login_view, name='custom-login'),
    path('logout/', user_views.custom_logout_view, name='custom-logout'),
    path('user/', user_views.UserDetailView.as_view(), name='user-detail'),

    # Practice
    path('practice/next/', practice_views.NextPracticeWordView.as_view(), name='next-practice-word'),
    path('practice/submit/', practice_views.SubmitAnswerView.as_view(), name='submit-answer'),
    path('practice/session-summary/', practice_views.SessionSummaryView.as_view(), name='session-summary'),
    path('practice/apply-bonuses/', practice_views.ApplySessionBonusesView.as_view(), name='apply-session-bonuses'),

    # Student Dashboard
    path('student/dashboard/', dashboard_views.StudentDashboardView.as_view(), name='student-dashboard'),
    path('student/words-by-level/<int:level_id>/', dashboard_views.WordsByLevelView.as_view(), name='words-by-level'),
    path('student/learning-patterns/', dashboard_views.LearningPatternsView.as_view(), name='student-learning-patterns'),
    path('student/assigned-sets/', instructional_views.StudentAssignedSetsView.as_view(), name='student-assigned-sets'),

    # Instructional
    path('instructional/packs/<int:pack_id>/', instructional_views.InstructionalPackView.as_view(), name='instructional-pack'),
    path('instructional/packs/<int:pack_id>/complete/', instructional_views.CompletePackView.as_view(), name='complete-pack'),

    # Teacher Student Management (bulk before <int:pk> to avoid matching "bulk" as int)
    path('teacher/students/bulk/', teacher_views.BulkCreateStudentsView.as_view(), name='teacher-student-bulk-create'),
    path(
        'teacher/students/',
        teacher_views.TeacherStudentViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='teacher-student-list',
    ),
    path(
        'teacher/students/<int:pk>/',
        teacher_views.TeacherStudentViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='teacher-student-detail',
    ),
    path('teacher/students/<int:student_id>/progress/', dashboard_views.StudentProgressDashboardView.as_view(), name='student-progress-dashboard'),
    path('teacher/students/<int:student_id>/learning-patterns/', dashboard_views.LearningPatternsView.as_view(), name='teacher-learning-patterns'),

    # Teacher Roster
    path('teacher/roster/', dashboard_views.RosterDashboardView.as_view(), name='roster-dashboard'),

    # Generation (Admin only)
    path('word-sets/<int:word_set_id>/generate/', generation_views.TriggerGenerationView.as_view(), name='trigger-generation'),
    path('generation-jobs/<int:job_id>/', generation_views.GenerationJobStatusView.as_view(), name='generation-job-status'),
    path('generation-jobs/<int:job_id>/logs/', generation_views.GenerationJobLogsView.as_view(), name='generation-job-logs'),
]
