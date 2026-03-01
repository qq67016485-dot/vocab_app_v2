from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


# =============================================================================
# CORE VOCABULARY MODELS
# =============================================================================

class Tag(models.Model):
    tag_name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.tag_name


class Word(models.Model):
    """Replaces v1 Term + WordMeaning. One record per word+POS combination."""
    text = models.CharField(max_length=100, db_index=True)
    part_of_speech = models.CharField(max_length=50, blank=True, default='')
    source_context = models.CharField(
        max_length=255, blank=True, default='',
        help_text='e.g., "From the book Cosmos"',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='words')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        pos = f" ({self.part_of_speech})" if self.part_of_speech else ""
        return f"{self.text}{pos}"


class WordDefinition(models.Model):
    """Replaces v1 Definition. FK now points to Word instead of WordMeaning."""
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='definitions')
    definition_text = models.TextField()
    example_sentence = models.TextField(blank=True, default='')
    lexile_score = models.IntegerField(
        null=True, blank=True,
        help_text='The estimated Lexile score for this definition and example.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['lexile_score']

    def __str__(self):
        lexile_str = f" ({self.lexile_score}L)" if self.lexile_score else ""
        return f"Def for '{self.word.text}'{lexile_str}: {self.definition_text[:40]}..."


class DefinitionEmbedding(models.Model):
    """Stores vector embeddings for semantic deduplication."""
    definition = models.OneToOneField(
        WordDefinition, on_delete=models.CASCADE, related_name='embedding',
    )
    embedding = models.JSONField(help_text='Vector embedding (list of floats)')
    model_version = models.CharField(max_length=50, default='Qwen/Qwen3-Embedding-8B')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Embedding for '{self.definition.word.text}'"


# =============================================================================
# TRANSLATION MODEL (Multi-language support)
# =============================================================================

class Translation(models.Model):
    """
    Generic translation for any model's text field.
    Uses Django's ContentType framework for polymorphic references.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    field_name = models.CharField(
        max_length=30,
        help_text='The field being translated, e.g. "definition_text", "example_sentence"',
    )
    language = models.CharField(max_length=10, choices=settings.SUPPORTED_LANGUAGES)
    translated_text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('content_type', 'object_id', 'field_name', 'language')
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Translation ({self.language}) for {self.field_name}"


# =============================================================================
# MASTERY & PROGRESS MODELS
# =============================================================================

class MasteryLevel(models.Model):
    level_id = models.IntegerField(primary_key=True)
    level_name = models.CharField(max_length=50)
    interval_days = models.IntegerField(help_text='Days to wait for next review at this level')
    points_to_promote = models.IntegerField(help_text='Points needed to graduate from this level')

    def __str__(self):
        return self.level_name


class UserWordProgress(models.Model):
    """Replaces v1 UserMeaningMastery. FK points to Word instead of WordMeaning."""
    INSTRUCTIONAL_STATUS_CHOICES = [
        ('READY', 'Ready'),
        ('PENDING', 'Pending Instruction'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_progress',
    )
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='user_progress')
    level = models.ForeignKey(MasteryLevel, on_delete=models.PROTECT)
    mastery_points = models.IntegerField(default=0)
    next_review_date = models.DateField()
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    instructional_status = models.CharField(
        max_length=20, choices=INSTRUCTIONAL_STATUS_CHOICES, default='READY',
    )

    class Meta:
        unique_together = ('user', 'word')

    def __str__(self):
        return f"{self.user.username}'s progress on '{self.word.text}'"


class MasteryLevelLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mastery_logs',
    )
    word = models.ForeignKey(Word, on_delete=models.CASCADE)
    old_level = models.ForeignKey(MasteryLevel, related_name='logs_as_old', on_delete=models.PROTECT)
    new_level = models.ForeignKey(MasteryLevel, related_name='logs_as_new', on_delete=models.PROTECT)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username}: {self.old_level} -> {self.new_level} ({self.word.text})"


# =============================================================================
# QUESTION & PRACTICE MODELS
# =============================================================================

class Question(models.Model):
    class QuestionType(models.TextChoices):
        DEFINITION_MC_SINGLE = 'DEFINITION_MC_SINGLE', 'Definition MC (Single Ans)'
        DEFINITION_TRUE_FALSE = 'DEFINITION_TRUE_FALSE', 'Definition True/False'
        DEFINITION_MATCHING = 'DEFINITION_MATCHING', 'Definition Matching'
        SYNONYM_MC_SINGLE = 'SYNONYM_MC_SINGLE', 'Synonym MC (Single Ans)'
        SYNONYM_MC_MULTI = 'SYNONYM_MC_MULTI', 'Synonym MC (Multi Ans)'
        SYNONYM_MATCHING = 'SYNONYM_MATCHING', 'Synonym Matching'
        ANTONYM_MC_SINGLE = 'ANTONYM_MC_SINGLE', 'Antonym MC (Single Ans)'
        ANTONYM_MATCHING = 'ANTONYM_MATCHING', 'Antonym Matching'
        CONTEXT_MC_SINGLE = 'CONTEXT_MC_SINGLE', 'Context MC (Single Ans)'
        CONTEXT_FILL_IN_BLANK = 'CONTEXT_FILL_IN_BLANK', 'Context Fill-in-Blank'
        SPELLING_FILL_IN_BLANK = 'SPELLING_FILL_IN_BLANK', 'Spelling Fill-in-Blank'
        WORD_FORM_FILL_IN_BLANK = 'WORD_FORM_FILL_IN_BLANK', 'Word Form Fill-in-Blank'
        WORD_FORM_MC = 'WORD_FORM_MC', 'Word Form MC'
        SENTENCE_SCRAMBLE = 'SENTENCE_SCRAMBLE', 'Sentence Scramble'
        DIALOGUE_COMPLETION_MC = 'DIALOGUE_COMPLETION_MC', 'Dialogue Completion MC'
        ODD_ONE_OUT_MC_SINGLE = 'ODD_ONE_OUT_MC_SINGLE', 'Odd One Out MC (Single Ans)'
        CONNOTATION_SORTING = 'CONNOTATION_SORTING', 'Connotation Sorting'
        COLLOCATION_MC_SINGLE = 'COLLOCATION_MC_SINGLE', 'Collocation MC (Single Ans)'
        COLLOCATION_FILL_IN_BLANK = 'COLLOCATION_FILL_IN_BLANK', 'Collocation Fill-in-Blank'
        COLLOCATION_MATCHING = 'COLLOCATION_MATCHING', 'Collocation Matching'
        CONCEPTUAL_ASSOCIATION_MC_SINGLE = 'CONCEPTUAL_ASSOCIATION_MC_SINGLE', 'Conceptual Association MC (Single Ans)'

    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=50, choices=QuestionType.choices)
    question_text = models.TextField()
    options = models.JSONField(null=True, blank=True)
    correct_answers = models.JSONField()
    explanation = models.TextField(blank=True, default='')
    example_sentence = models.TextField(
        blank=True, default='',
        help_text='A sentence demonstrating the word usage in context.',
    )
    lexile_score = models.IntegerField(
        null=True, blank=True,
        help_text='The estimated Lexile score for the question text.',
    )
    difficulty_index = models.FloatField(
        null=True, blank=True,
        help_text='P-Value: Proportion of users who answered correctly.',
    )
    discrimination_index = models.FloatField(
        null=True, blank=True,
        help_text='How well the question differentiates high/low-performing users.',
    )
    suitable_levels = models.ManyToManyField(MasteryLevel, related_name='questions', blank=True)
    generation_job = models.ForeignKey(
        'GenerationJob', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_questions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_question_type_display()} for '{self.word.text}'"


class PracticeSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions',
    )
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Session for {self.user.username} at {self.start_time.strftime('%Y-%m-%d %H:%M')}"


class UserAnswer(models.Model):
    session = models.ForeignKey(
        PracticeSession, on_delete=models.CASCADE,
        related_name='answers', null=True, blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='answers',
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    user_answer = models.TextField(null=True, blank=True)
    is_correct = models.BooleanField()
    duration_seconds = models.IntegerField(
        null=True, blank=True, help_text='Time in seconds taken to answer',
    )
    answer_switches = models.IntegerField(
        default=0,
        help_text='Number of times the user changed their answer before submitting.',
    )
    answered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = 'Correct' if self.is_correct else 'Incorrect'
        return f"Answer by {self.user.username} for question {self.question_id} ({status})"


# =============================================================================
# CURRICULUM & WORD SET MODELS
# =============================================================================

class Curriculum(models.Model):
    name = models.CharField(
        max_length=200, unique=True,
        help_text='The top-level program or series, e.g., "Wonders Reading".',
    )

    def __str__(self):
        return self.name


class Level(models.Model):
    name = models.CharField(
        max_length=100, unique=True,
        help_text='The grade or difficulty level, e.g., "Grade 2".',
    )
    order = models.IntegerField(
        default=0, help_text='An integer for sorting.',
    )

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class WordSet(models.Model):
    class GenerationStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        TO_GENERATE = 'TO_GENERATE', 'To Generate'
        GENERATING = 'GENERATING', 'Generating'
        GENERATED = 'GENERATED', 'Generated'

    title = models.CharField(max_length=200, help_text='The title of the book, article, or unit.')
    unit_or_chapter = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    source_text = models.TextField(
        blank=True, default='',
        help_text='Optional passage text for LLM context during generation.',
    )
    target_lexile = models.IntegerField(default=650, help_text='Target Lexile reading level.')
    input_words = models.JSONField(
        null=True, blank=True,
        help_text='Raw word list entered by teacher, pending generation.',
    )
    input_source_title = models.CharField(max_length=300, blank=True, default='')
    input_source_chapter = models.CharField(max_length=300, blank=True, default='')
    generation_status = models.CharField(
        max_length=20,
        choices=GenerationStatus.choices,
        default=GenerationStatus.DRAFT,
    )
    curriculum = models.ForeignKey(
        Curriculum, on_delete=models.SET_NULL, null=True, blank=True, related_name='word_sets',
    )
    level = models.ForeignKey(
        Level, on_delete=models.SET_NULL, null=True, blank=True, related_name='word_sets',
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_word_sets',
    )
    is_public = models.BooleanField(default=False, help_text='If true, visible to other teachers.')
    words = models.ManyToManyField(Word, blank=True, related_name='word_sets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.unit_or_chapter:
            return f"'{self.title} - {self.unit_or_chapter}' by {self.creator.username}"
        return f"'{self.title}' by {self.creator.username}"


class StudentWordSetAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_set_assignments',
    )
    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_word_sets',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'word_set')

    def __str__(self):
        return f"{self.user.username} assigned '{self.word_set.title}'"


# =============================================================================
# INSTRUCTIONAL LAYER MODELS
# =============================================================================

class WordPack(models.Model):
    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name='packs')
    label = models.CharField(max_length=100)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.label} ({self.word_set.title})"


class WordPackItem(models.Model):
    pack = models.ForeignKey(WordPack, on_delete=models.CASCADE, related_name='items')
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='pack_items')
    order = models.IntegerField(default=0)

    class Meta:
        unique_together = ('pack', 'word')
        ordering = ['order']

    def __str__(self):
        return f"{self.word.text} in {self.pack.label}"


class PrimerCardContent(models.Model):
    word = models.OneToOneField(Word, on_delete=models.CASCADE, related_name='primer_content')
    syllable_text = models.CharField(max_length=200, help_text='e.g., "vo·cab·u·la·ry"')
    image_url = models.URLField(blank=True, default='')
    audio_url = models.URLField(blank=True, default='')
    kid_friendly_definition = models.TextField()
    example_sentence = models.TextField()

    def __str__(self):
        return f"Primer for '{self.word.text}'"


class MicroStory(models.Model):
    pack = models.ForeignKey(WordPack, on_delete=models.CASCADE, related_name='stories')
    story_text = models.TextField(help_text='Target words wrapped in **word** markers')
    reading_level = models.IntegerField(help_text='Lexile score')

    class Meta:
        ordering = ['reading_level']

    def __str__(self):
        return f"Story for {self.pack.label} (Lexile {self.reading_level})"


class ClozeItem(models.Model):
    pack = models.ForeignKey(WordPack, on_delete=models.CASCADE, related_name='cloze_items')
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='cloze_items')
    sentence_text = models.TextField(help_text='Sentence with _______ blank')
    correct_answer = models.CharField(max_length=200)
    distractors = models.JSONField(help_text='List of 2 distractor strings')
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Cloze for '{self.word.text}' in {self.pack.label}"


class GeneratedImage(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = 'PENDING_REVIEW', 'Pending Review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='generated_images')
    image = models.ImageField(upload_to='generated_images/', blank=True)
    prompt_used = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_REVIEW)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for '{self.word.text}' ({self.status})"


class StudentPackCompletion(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pack_completions',
    )
    pack = models.ForeignKey(WordPack, on_delete=models.CASCADE, related_name='completions')
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'pack')

    def __str__(self):
        return f"{self.user.username} completed {self.pack.label}"


# =============================================================================
# GENERATION PIPELINE MODELS
# =============================================================================

class GenerationJob(models.Model):
    class JobType(models.TextChoices):
        FULL_PIPELINE = 'FULL_PIPELINE', 'Full Pipeline'
        QUESTIONS_ONLY = 'QUESTIONS_ONLY', 'Questions Only'
        INSTRUCTIONAL_ONLY = 'INSTRUCTIONAL_ONLY', 'Instructional Only'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        PARTIALLY_COMPLETED = 'PARTIALLY_COMPLETED', 'Partially Completed'

    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name='generation_jobs')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='generation_jobs',
    )
    job_type = models.CharField(
        max_length=30, choices=JobType.choices, default=JobType.FULL_PIPELINE,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)

    input_words = models.JSONField(help_text='Raw word list from teacher')
    input_source_title = models.CharField(max_length=300, blank=True, default='')
    input_source_chapter = models.CharField(max_length=300, blank=True, default='')
    input_source_text = models.TextField(blank=True, default='')
    target_lexile = models.IntegerField(default=650)
    target_language = models.CharField(
        max_length=10, choices=settings.SUPPORTED_LANGUAGES, default='zh-CN',
    )

    words_created = models.IntegerField(default=0)
    questions_created = models.IntegerField(default=0)
    primer_cards_created = models.IntegerField(default=0)
    stories_created = models.IntegerField(default=0)
    cloze_items_created = models.IntegerField(default=0)
    images_created = models.IntegerField(default=0)

    error_message = models.TextField(blank=True, default='')
    last_completed_step = models.CharField(
        max_length=30, blank=True, default='',
        help_text='Last pipeline step that completed successfully.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Job {self.pk} ({self.get_status_display()}) for '{self.word_set.title}'"


class GenerationJobLog(models.Model):
    class Step(models.TextChoices):
        WORD_LOOKUP = 'WORD_LOOKUP', 'Word Lookup'
        DEDUP = 'DEDUP', 'Deduplication'
        TRANSLATION = 'TRANSLATION', 'Translation'
        QUESTION_GEN = 'QUESTION_GEN', 'Question Generation'
        PACK_CREATION = 'PACK_CREATION', 'Pack Creation'
        PRIMER_GEN = 'PRIMER_GEN', 'Primer Generation'
        STORY_CLOZE_GEN = 'STORY_CLOZE_GEN', 'Story & Cloze Generation'
        IMAGE_GEN = 'IMAGE_GEN', 'Image Generation'

    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name='logs')
    step = models.CharField(max_length=30, choices=Step.choices)
    status = models.CharField(
        max_length=30,
        choices=GenerationJob.Status.choices,
        default=GenerationJob.Status.PENDING,
    )
    input_data = models.JSONField(null=True, blank=True)
    output_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    duration_seconds = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Log: {self.get_step_display()} ({self.get_status_display()})"
