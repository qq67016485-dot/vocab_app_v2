from django.contrib import admin
from .models import (
    Tag, Word, WordDefinition, DefinitionEmbedding, Translation,
    MasteryLevel, UserWordProgress, MasteryLevelLog,
    Question, PracticeSession, UserAnswer,
    Curriculum, Level, WordSet, StudentWordSetAssignment,
    WordPack, WordPackItem, PrimerCardContent, MicroStory,
    ClozeItem, GeneratedImage, StudentPackCompletion,
    GenerationJob, GenerationJobLog,
)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('tag_name',)
    search_fields = ('tag_name',)


class WordDefinitionInline(admin.TabularInline):
    model = WordDefinition
    extra = 0


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ('text', 'part_of_speech', 'source_context', 'created_at')
    list_filter = ('part_of_speech',)
    search_fields = ('text',)
    filter_horizontal = ('tags',)
    inlines = [WordDefinitionInline]


@admin.register(WordDefinition)
class WordDefinitionAdmin(admin.ModelAdmin):
    list_display = ('word', 'lexile_score', 'definition_text_short')
    list_filter = ('lexile_score',)
    search_fields = ('word__text', 'definition_text')

    def definition_text_short(self, obj):
        return obj.definition_text[:60] + '...' if len(obj.definition_text) > 60 else obj.definition_text
    definition_text_short.short_description = 'Definition'


@admin.register(DefinitionEmbedding)
class DefinitionEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('definition', 'model_version', 'created_at')
    list_filter = ('model_version',)


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    list_display = ('content_type', 'object_id', 'field_name', 'language', 'translated_text_short')
    list_filter = ('language', 'field_name', 'content_type')

    def translated_text_short(self, obj):
        return obj.translated_text[:40] + '...' if len(obj.translated_text) > 40 else obj.translated_text
    translated_text_short.short_description = 'Translation'


@admin.register(MasteryLevel)
class MasteryLevelAdmin(admin.ModelAdmin):
    list_display = ('level_id', 'level_name', 'interval_days', 'points_to_promote')


@admin.register(UserWordProgress)
class UserWordProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'word', 'level', 'mastery_points', 'next_review_date', 'instructional_status')
    list_filter = ('level', 'instructional_status')
    search_fields = ('user__username', 'word__text')


@admin.register(MasteryLevelLog)
class MasteryLevelLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'word', 'old_level', 'new_level', 'timestamp')
    list_filter = ('old_level', 'new_level')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('word', 'question_type', 'lexile_score', 'generation_job')
    list_filter = ('question_type',)
    search_fields = ('word__text', 'question_text')
    filter_horizontal = ('suitable_levels',)


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_time', 'end_time')


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'is_correct', 'duration_seconds', 'answered_at')
    list_filter = ('is_correct',)


@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')


@admin.register(WordSet)
class WordSetAdmin(admin.ModelAdmin):
    list_display = ('title', 'unit_or_chapter', 'creator', 'is_public', 'created_at')
    list_filter = ('is_public', 'curriculum', 'level')
    search_fields = ('title', 'creator__username')
    filter_horizontal = ('words',)


@admin.register(StudentWordSetAssignment)
class StudentWordSetAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'word_set', 'assigned_by', 'assigned_at')


@admin.register(WordPack)
class WordPackAdmin(admin.ModelAdmin):
    list_display = ('label', 'word_set', 'order')


@admin.register(WordPackItem)
class WordPackItemAdmin(admin.ModelAdmin):
    list_display = ('word', 'pack', 'order')


@admin.register(PrimerCardContent)
class PrimerCardContentAdmin(admin.ModelAdmin):
    list_display = ('word', 'syllable_text')
    search_fields = ('word__text',)


@admin.register(MicroStory)
class MicroStoryAdmin(admin.ModelAdmin):
    list_display = ('pack', 'reading_level')


@admin.register(ClozeItem)
class ClozeItemAdmin(admin.ModelAdmin):
    list_display = ('word', 'pack', 'correct_answer', 'order')


@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    list_display = ('word', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(StudentPackCompletion)
class StudentPackCompletionAdmin(admin.ModelAdmin):
    list_display = ('user', 'pack', 'completed_at')


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'word_set', 'created_by', 'job_type', 'status', 'created_at')
    list_filter = ('status', 'job_type')
    readonly_fields = ('created_at', 'completed_at')


@admin.register(GenerationJobLog)
class GenerationJobLogAdmin(admin.ModelAdmin):
    list_display = ('job', 'step', 'status', 'duration_seconds', 'created_at')
    list_filter = ('step', 'status')
