"""
V2 serializers — adapted from v1 with updated FK paths.

Changes from v1:
- WordMeaning → Word (model rename)
- meaning.term.term_text → word.text
- Definition → WordDefinition
- chinese_translation → Translation model lookup
- Added native_language to UserSerializer
- StudentGroup moved to users.models (same as v1)
"""
from rest_framework import serializers
from django.conf import settings

from users.models import CustomUser, StudentGroup
from .models import (
    Word, WordDefinition, Question, WordSet, Curriculum, Level,
)
from .utils import get_tier_info, calculate_xp_in_current_level


# =============================================================================
# USER & AUTHENTICATION SERIALIZERS
# =============================================================================

class UserSerializer(serializers.ModelSerializer):
    tier_info = serializers.SerializerMethodField()
    xp_in_current_level = serializers.SerializerMethodField()
    xp_for_next_level = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'role', 'level', 'xp_points',
            'tier_info', 'xp_in_current_level', 'xp_for_next_level',
            'lexile_min', 'lexile_max',
            'native_language',
        ]

    def get_tier_info(self, obj):
        return get_tier_info(obj.level)

    def get_xp_for_next_level(self, obj):
        tier_info = get_tier_info(obj.level)
        return tier_info['xp_per_level'] if tier_info else 0

    def get_xp_in_current_level(self, obj):
        return calculate_xp_in_current_level(obj.xp_points, obj.level)


# =============================================================================
# CORE VOCABULARY SERIALIZERS
# =============================================================================

class WordDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WordDefinition
        fields = ['id', 'definition_text', 'example_sentence', 'lexile_score']


class WordSerializer(serializers.ModelSerializer):
    """
    Replaces v1 WordMeaningSerializer.
    Dynamically selects the best definition based on student Lexile range.
    """
    definition = serializers.SerializerMethodField()
    example_sentence = serializers.SerializerMethodField()

    class Meta:
        model = Word
        fields = ['id', 'text', 'part_of_speech', 'definition', 'example_sentence']

    def _get_best_definition(self, obj):
        if hasattr(self, '_best_def_cache') and obj.id in self._best_def_cache:
            return self._best_def_cache[obj.id]

        request = self.context.get('request')
        user = request.user if request and hasattr(request, 'user') else None

        all_definitions = obj.definitions.all()
        if not all_definitions:
            best_def = None
        elif not user or not user.is_authenticated or user.role != 'STUDENT':
            best_def = all_definitions.first()
        else:
            user_min = user.lexile_min
            user_max = user.lexile_max
            user_mid = (user_min + user_max) / 2

            in_range = [
                d for d in all_definitions
                if d.lexile_score is not None and user_min <= d.lexile_score <= user_max
            ]
            if in_range:
                best_def = min(in_range, key=lambda d: abs(d.lexile_score - user_mid))
            else:
                below = [
                    d for d in all_definitions
                    if d.lexile_score is not None and d.lexile_score < user_max
                ]
                if below:
                    best_def = max(below, key=lambda d: d.lexile_score)
                else:
                    best_def = all_definitions.first()

        if not hasattr(self, '_best_def_cache'):
            self._best_def_cache = {}
        self._best_def_cache[obj.id] = best_def
        return best_def

    def get_definition(self, obj):
        best_def = self._get_best_definition(obj)
        return best_def.definition_text if best_def else ''

    def get_example_sentence(self, obj):
        best_def = self._get_best_definition(obj)
        return best_def.example_sentence if best_def else ''


class WordDetailSerializer(WordSerializer):
    """Extends WordSerializer with a full list of definitions."""
    definitions = WordDefinitionSerializer(many=True, read_only=True)

    class Meta(WordSerializer.Meta):
        fields = WordSerializer.Meta.fields + ['definitions']


class QuestionSerializer(serializers.ModelSerializer):
    """Serializes Question for practice — excludes correct_answers."""
    term_text = serializers.CharField(source='word.text', read_only=True)

    class Meta:
        model = Question
        fields = [
            'id', 'term_text', 'question_type', 'question_text',
            'options', 'explanation', 'example_sentence', 'lexile_score',
        ]


# =============================================================================
# CURRICULUM & WORD SET SERIALIZERS
# =============================================================================

class CurriculumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Curriculum
        fields = ['id', 'name']


class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = ['id', 'name']


class WordSetSerializer(serializers.ModelSerializer):
    """Summary view of a WordSet for list endpoints."""
    curriculum = CurriculumSerializer(read_only=True)
    level = LevelSerializer(read_only=True)
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    word_count = serializers.SerializerMethodField()

    class Meta:
        model = WordSet
        fields = [
            'id', 'title', 'unit_or_chapter', 'description',
            'curriculum', 'level', 'creator_username', 'is_public', 'word_count',
            'target_lexile', 'generation_status', 'input_words',
            'input_source_title', 'input_source_chapter',
        ]

    def get_word_count(self, obj):
        return obj.words.count()


class WordSetDetailSerializer(WordSetSerializer):
    """Extends WordSetSerializer with the full word list."""
    words = WordSerializer(many=True, read_only=True)

    class Meta(WordSetSerializer.Meta):
        fields = WordSetSerializer.Meta.fields + ['words']


class WordSetFormSerializer(serializers.ModelSerializer):
    """For creating and updating a WordSet."""
    curriculum_id = serializers.PrimaryKeyRelatedField(
        queryset=Curriculum.objects.all(), source='curriculum',
        write_only=True, required=False, allow_null=True,
    )
    level_id = serializers.PrimaryKeyRelatedField(
        queryset=Level.objects.all(), source='level',
        write_only=True, required=False, allow_null=True,
    )

    class Meta:
        model = WordSet
        fields = [
            'title', 'unit_or_chapter', 'description', 'is_public',
            'curriculum_id', 'level_id', 'target_lexile',
            'input_words', 'input_source_title', 'input_source_chapter',
        ]


# =============================================================================
# STUDENT GROUP SERIALIZERS
# =============================================================================

class StudentInGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username']


class StudentGroupSerializer(serializers.ModelSerializer):
    """Read serializer for group list/detail views."""
    teacher_username = serializers.CharField(source='teacher.username', read_only=True)
    students = StudentInGroupSerializer(many=True, read_only=True)
    student_count = serializers.IntegerField(source='students.count', read_only=True)

    class Meta:
        model = StudentGroup
        fields = [
            'id', 'name', 'description', 'teacher_username',
            'students', 'student_count', 'updated_at',
        ]


class StudentGroupFormSerializer(serializers.ModelSerializer):
    """Write serializer for group create/update."""
    students = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(role=CustomUser.Role.STUDENT),
        many=True,
        required=False,
    )

    class Meta:
        model = StudentGroup
        fields = ['name', 'description', 'students']

    def validate_students(self, students):
        teacher = self.context['request'].user
        for student in students:
            if not teacher.students.filter(id=student.id).exists():
                raise serializers.ValidationError(
                    f"Student '{student.username}' is not assigned to you."
                )
        return students


# =============================================================================
# TEACHER STUDENT SERIALIZERS
# =============================================================================

class TeacherStudentSerializer(serializers.ModelSerializer):
    """Lists students assigned to a teacher with their learning settings."""
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'daily_question_limit',
            'lexile_min', 'lexile_max',
        ]


class StudentCreateUpdateSerializer(serializers.ModelSerializer):
    """For creating and updating student accounts."""
    password = serializers.CharField(
        write_only=True, required=False, style={'input_type': 'password'},
    )

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'password',
            'daily_question_limit', 'lexile_min', 'lexile_max',
        ]
        read_only_fields = ['id']

    def validate(self, data):
        min_score = data.get('lexile_min')
        max_score = data.get('lexile_max')
        if self.instance:
            if min_score is None:
                min_score = self.instance.lexile_min
            if max_score is None:
                max_score = self.instance.lexile_max
        if min_score is not None and max_score is not None and min_score > max_score:
            raise serializers.ValidationError(
                {"lexile_scores": "Lexile min cannot be greater than Lexile max."}
            )
        return data

    def create(self, validated_data):
        return CustomUser.objects.create_user(
            username=validated_data['username'],
            password=validated_data.get('password'),
            role=CustomUser.Role.STUDENT,
            daily_question_limit=validated_data.get('daily_question_limit', 20),
            lexile_min=validated_data.get('lexile_min', 0),
            lexile_max=validated_data.get('lexile_max', 2000),
        )

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


# =============================================================================
# ROSTER SERIALIZERS
# =============================================================================

class RosterGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentGroup
        fields = ['id', 'name']


class RosterActivitySerializer(serializers.Serializer):
    questions_answered = serializers.IntegerField(default=0)
    accuracy_percent = serializers.IntegerField(default=0)


class RosterSnapshotSerializer(serializers.Serializer):
    challenging_words = serializers.ListField(child=serializers.CharField())
    skills_to_develop = serializers.ListField(child=serializers.CharField())
    words_due_for_review = serializers.IntegerField(default=0)


class RosterStudentSerializer(serializers.ModelSerializer):
    activity_3d = RosterActivitySerializer(read_only=True)
    snapshot = RosterSnapshotSerializer(read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'activity_3d', 'snapshot',
            'daily_question_limit', 'lexile_min', 'lexile_max',
        ]


class RosterDashboardSerializer(serializers.Serializer):
    groups = RosterGroupSerializer(many=True, read_only=True)
    roster = RosterStudentSerializer(many=True, read_only=True)
