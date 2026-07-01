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
    is_hidden = models.BooleanField(
        default=False,
        help_text='Hidden levels are used for scheduling but not shown in student mastery summaries.',
    )

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
    next_review_at = models.DateTimeField()
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    learning_speed = models.FloatField(
        default=1.0,
        help_text='Per-student-word adaptive multiplier for review intervals.',
    )
    instructional_status = models.CharField(
        max_length=20, choices=INSTRUCTIONAL_STATUS_CHOICES, default='READY',
    )

    class Meta:
        unique_together = ('user', 'word')
        indexes = [
            # Dashboard/practice "due for review" queries filter by user + next_review_at.
            models.Index(fields=['user', 'next_review_at']),
            # Instructional-status filtering (READY vs PENDING) scoped per user.
            models.Index(fields=['user', 'instructional_status']),
        ]

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
        REVERSE_DEFINITION_MC = 'REVERSE_DEFINITION_MC', 'Reverse Definition MC'
        SYNONYM_IN_CONTEXT_MC = 'SYNONYM_IN_CONTEXT_MC', 'Synonym in Context MC'
        REVERSE_SYNONYM_IN_CONTEXT_MC = 'REVERSE_SYNONYM_IN_CONTEXT_MC', 'Reverse Synonym in Context MC'
        APPLICATION_MC = 'APPLICATION_MC', 'Application MC'
        REVERSE_ASSOCIATION_MC = 'REVERSE_ASSOCIATION_MC', 'Reverse Association MC'
        REVERSE_COLLOCATION_MC = 'REVERSE_COLLOCATION_MC', 'Reverse Collocation MC'
        NUANCE_CONTRAST_MC = 'NUANCE_CONTRAST_MC', 'Nuance Contrast MC'

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
    retry_count = models.IntegerField(
        default=0,
        help_text='Number of scaffolded retry attempts after the initial wrong answer.',
    )
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Dashboard activity/accuracy queries filter by user (+ recency).
            models.Index(fields=['user', 'answered_at']),
            # "Frequent mistakes" / challenging-words queries filter user + is_correct.
            models.Index(fields=['user', 'is_correct']),
            # Per-word answer history lookups (e.g. struggle-word detection).
            models.Index(fields=['question', 'answered_at']),
        ]

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
    curriculum = models.ForeignKey(
        'Curriculum', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='levels',
        help_text='The program this level belongs to, if any.',
    )
    name = models.CharField(
        max_length=100,
        help_text='The grade or difficulty level, e.g., "Grade 2".',
    )
    order = models.IntegerField(
        default=0, help_text='An integer for sorting.',
    )

    class Meta:
        ordering = ['order', 'name']
        unique_together = [('curriculum', 'name')]

    def __str__(self):
        return self.name


class WordSet(models.Model):
    class GenerationStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        TO_GENERATE = 'TO_GENERATE', 'To Generate'
        GENERATION_REQUESTED = 'GENERATION_REQUESTED', 'Generation Requested'
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
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generation_requests',
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"'{self.title}' by {self.creator.username}"


class WordSetBookmark(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_set_bookmarks',
    )
    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'word_set')

    def __str__(self):
        return f"{self.user.username} bookmarked '{self.word_set.title}'"


class StudentWordSetAssignment(models.Model):
    class ContentType(models.TextChoices):
        GRAPHIC_NOVEL = 'graphic_novel', 'Graphic Novel'
        INFOGRAPHIC = 'infographic', 'Infographic'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='word_set_assignments',
    )
    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_word_sets',
    )
    content_type = models.CharField(
        max_length=20, choices=ContentType.choices, default=ContentType.GRAPHIC_NOVEL,
        help_text='Which instructional content format this student sees for the word set: '
                  'the graphic novel or the infographic.',
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
    class TextType(models.TextChoices):
        FICTION = 'fiction', 'Fiction'
        NARRATIVE_NONFICTION = 'narrative_nonfiction', 'Narrative Non-Fiction'

    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name='packs')
    label = models.CharField(max_length=100)
    text_type = models.CharField(
        max_length=30, choices=TextType.choices, default=TextType.FICTION,
    )
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


class GraphicNovel(models.Model):
    class Channel(models.TextChoices):
        FIVE_PAGE = '5page', '5-Page'
        SIX_PAGE = '6page', '6-Page'

    pack = models.ForeignKey(
        WordPack, on_delete=models.CASCADE, related_name='graphic_novels',
    )
    channel = models.CharField(
        max_length=10, choices=Channel.choices, default=Channel.FIVE_PAGE,
        help_text='Vestigial: always "5page". Superseded by candidate_index; kept as a dead column pending removal.',
    )
    candidate_index = models.IntegerField(
        default=0,
        help_text='Which generated candidate (0..N-1) this novel is for the pack. '
                  'Multiple candidates are generated per pack so an admin can pick the best.',
    )
    is_selected = models.BooleanField(
        default=False,
        help_text='True for the one candidate chosen by an admin. Only selected '
                  'novels are shown to students. No candidate selected = pack not yet published.',
    )
    title = models.CharField(max_length=200)
    synopsis = models.TextField(help_text='Story synopsis for character/scene continuity')
    characters = models.JSONField(
        default=list,
        help_text='Character visual reference list for cross-page consistency',
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Lexi Legends metadata: away team, age band, Vault framing, review artifact',
    )
    style_prompt = models.TextField(help_text='Art style directive used for all pages')
    reading_level = models.IntegerField(help_text='Lexile score')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('pack', 'candidate_index')

    def __str__(self):
        return (
            f"Graphic novel cand {self.candidate_index}"
            f"{' [selected]' if self.is_selected else ''} for {self.pack.label}: {self.title}"
        )


class GraphicNovelPage(models.Model):
    class GenerationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    novel = models.ForeignKey(GraphicNovel, on_delete=models.CASCADE, related_name='pages')
    page_number = models.IntegerField()
    image = models.ImageField(upload_to='graphic_novels/', blank=True)
    edited_image = models.ImageField(
        upload_to='graphic_novels/',
        blank=True,
        help_text='Admin-edited variant of the page image; the original is preserved in `image`.',
    )
    use_edited_image = models.BooleanField(
        default=False,
        help_text='When True (and an edited image exists), the edited variant is shown everywhere.',
    )
    image_jpeg = models.ImageField(
        upload_to='graphic_novels/',
        blank=True,
        help_text='Lightweight JPEG companion of `image`, served to students to save bandwidth.',
    )
    edited_image_jpeg = models.ImageField(
        upload_to='graphic_novels/',
        blank=True,
        help_text='Lightweight JPEG companion of `edited_image`, served to students to save bandwidth.',
    )
    prompt_used = models.TextField(blank=True)
    generation_status = models.CharField(
        max_length=20,
        choices=GenerationStatus.choices,
        default=GenerationStatus.PENDING,
    )
    generation_attempts = models.IntegerField(default=0)
    generation_error = models.TextField(blank=True, default='')
    generation_started_at = models.DateTimeField(null=True, blank=True)
    generation_completed_at = models.DateTimeField(null=True, blank=True)
    panel_count = models.IntegerField(help_text='Number of panels on this page (1-4)')
    layout_description = models.TextField(blank=True)
    panel_descriptions = models.JSONField(
        default=list,
        help_text='Per-panel metadata for accessibility/tooltips',
    )
    characters_featured = models.JSONField(
        default=list,
        blank=True,
        help_text='Canonical character names appearing on this page',
    )
    setting_key = models.CharField(max_length=80, blank=True, default='')
    vault_zone = models.CharField(max_length=80, blank=True, default='')
    is_vault_page = models.BooleanField(default=False)
    vocab_words_used = models.JSONField(
        default=list,
        help_text='All vocab words appearing on this page',
    )
    is_review_page = models.BooleanField(
        default=False,
        help_text='True for the final vocabulary review page',
    )

    class Meta:
        ordering = ['page_number']
        unique_together = ('novel', 'page_number')

    def __str__(self):
        return f"{self.novel.title} page {self.page_number}"

    @property
    def display_image(self):
        """The image variant currently selected for display (edited or original)."""
        if self.use_edited_image and self.edited_image:
            return self.edited_image
        return self.image

    @property
    def has_edited_image(self):
        return bool(self.edited_image)

    @property
    def student_image(self):
        """The lightweight JPEG variant shown to students.

        Mirrors `display_image`'s original/edited choice but prefers the JPEG
        companion, falling back to the PNG when no JPEG exists yet (legacy rows
        or pages awaiting backfill).
        """
        if self.use_edited_image and self.edited_image:
            return self.edited_image_jpeg or self.edited_image
        return self.image_jpeg or self.image


class GraphicNovelPageAudio(models.Model):
    """Stitched read-along audio for one graphic novel page (generated on demand)."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    page = models.OneToOneField(
        GraphicNovelPage, on_delete=models.CASCADE, related_name='audio',
    )
    audio = models.FileField(
        upload_to='graphic_novel_audio/', blank=True,
        help_text='Stitched WAV file for the page read-along (source of truth).',
    )
    audio_mp3 = models.FileField(
        upload_to='graphic_novel_audio_mp3/', blank=True,
        help_text='Compressed MP3 companion of the WAV, served to students.',
    )
    duration_ms = models.IntegerField(default=0)
    voice_manifest = models.JSONField(
        default=dict, blank=True,
        help_text='Per-event voice assignments used during generation, for debugging / regen.',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    attempts = models.IntegerField(default=0)
    error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Audio for {self.page}"

    @property
    def student_audio(self):
        """The lightweight audio served to students.

        Prefers the compressed MP3 companion, falling back to the source WAV
        when no MP3 exists yet (legacy rows or pages awaiting backfill). Mirrors
        the PNG/JPEG `student_image` pattern: WAV stays the source of truth for
        admin/review, students get the smaller file.
        """
        return self.audio_mp3 or self.audio


class Infographic(models.Model):
    """A single-page educational infographic — an alternative to the graphic novel.

    Neutral instructional style (no Lexi Legends canon): one rendered image plus a
    short explanatory text and structured per-word entries. Like GraphicNovel, each
    pack generates ``GRAPHIC_NOVEL_CANDIDATE_COUNT`` candidates and an admin selects
    one to publish; only the selected candidate is shown to students. The single
    image variant/JPEG-companion fields mirror GraphicNovelPage (an infographic is
    always one page, so there is no separate page table).
    """

    class GenerationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    pack = models.ForeignKey(
        WordPack, on_delete=models.CASCADE, related_name='infographics',
    )
    candidate_index = models.IntegerField(
        default=0,
        help_text='Which generated candidate (0..N-1) this infographic is for the '
                  'pack. Multiple candidates are generated so an admin can pick the best.',
    )
    is_selected = models.BooleanField(
        default=False,
        help_text='True for the one candidate chosen by an admin. Only selected '
                  'infographics are shown to students. No candidate selected = not yet published.',
    )
    title = models.CharField(max_length=200)
    intro_text = models.TextField(
        blank=True, default='',
        help_text='Short text explaining the infographic, shown to students alongside the image.',
    )
    content = models.JSONField(
        default=dict, blank=True,
        help_text='Structured infographic layout: per-word entries (term, definition, '
                  'example, visual idea) plus theme/layout notes.',
    )
    style_prompt = models.TextField(
        blank=True, default='',
        help_text='Art/design directive used to render the infographic image.',
    )
    reading_level = models.IntegerField(default=650, help_text='Lexile score')
    metadata = models.JSONField(default=dict, blank=True)

    # Image (mirrors GraphicNovelPage: original + edited variant + JPEG companions).
    image = models.ImageField(upload_to='infographics/', blank=True)
    edited_image = models.ImageField(
        upload_to='infographics/', blank=True,
        help_text='Admin-edited variant; the original is preserved in `image`.',
    )
    use_edited_image = models.BooleanField(default=False)
    image_jpeg = models.ImageField(
        upload_to='infographics/', blank=True,
        help_text='Lightweight JPEG companion of `image`, served to students.',
    )
    edited_image_jpeg = models.ImageField(
        upload_to='infographics/', blank=True,
        help_text='Lightweight JPEG companion of `edited_image`, served to students.',
    )
    prompt_used = models.TextField(blank=True, default='')
    generation_status = models.CharField(
        max_length=20, choices=GenerationStatus.choices,
        default=GenerationStatus.PENDING,
    )
    generation_attempts = models.IntegerField(default=0)
    generation_error = models.TextField(blank=True, default='')
    generation_started_at = models.DateTimeField(null=True, blank=True)
    generation_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('pack', 'candidate_index')

    def __str__(self):
        return (
            f"Infographic cand {self.candidate_index}"
            f"{' [selected]' if self.is_selected else ''} for {self.pack.label}: {self.title}"
        )

    @property
    def display_image(self):
        """The image variant currently selected for display (edited or original)."""
        if self.use_edited_image and self.edited_image:
            return self.edited_image
        return self.image

    @property
    def has_edited_image(self):
        return bool(self.edited_image)

    @property
    def student_image(self):
        """The lightweight JPEG variant shown to students (falls back to PNG)."""
        if self.use_edited_image and self.edited_image:
            return self.edited_image_jpeg or self.edited_image
        return self.image_jpeg or self.image


class ClozeItem(models.Model):
    pack = models.ForeignKey(WordPack, on_delete=models.CASCADE, related_name='cloze_items')
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='cloze_items')
    novel = models.ForeignKey(
        'GraphicNovel', on_delete=models.CASCADE, related_name='cloze_items',
        null=True, blank=True,
        help_text='Graphic novel candidate this cloze was staged for. See the active-set '
                  'note below.',
    )
    infographic = models.ForeignKey(
        'Infographic', on_delete=models.CASCADE, related_name='cloze_items',
        null=True, blank=True,
        help_text='Infographic candidate this cloze was staged for. See the active-set '
                  'note below.',
    )
    sentence_text = models.TextField(help_text='Sentence with _______ blank')
    correct_answer = models.CharField(max_length=200)
    distractors = models.JSONField(help_text='List of 2 distractor strings')
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Cloze for '{self.word.text}' in {self.pack.label}"

    # Active/promoted cloze (the set students practice) has BOTH `novel` and
    # `infographic` NULL. A non-NULL `novel` OR `infographic` marks a staged
    # candidate row, hidden until that candidate is selected. Selecting either a
    # graphic novel or an infographic candidate promotes its staged rows by
    # re-creating them with both FKs NULL (prior active rows deleted first), so
    # whichever content type is published last owns the shared active set — fine,
    # since cloze is medium-agnostic vocabulary practice.


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
    content_types = models.JSONField(
        default=list, blank=True,
        help_text="Instructional content types to generate, e.g. "
                  "['graphic_novel', 'infographic']. Empty/legacy = graphic novel only. "
                  "A content type's pipeline steps are skipped when it is not listed.",
    )

    words_created = models.IntegerField(default=0)
    questions_created = models.IntegerField(default=0)
    primer_cards_created = models.IntegerField(default=0)
    stories_created = models.IntegerField(default=0)
    graphic_novels_created = models.IntegerField(default=0)
    infographics_created = models.IntegerField(default=0)
    cloze_items_created = models.IntegerField(default=0)

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
        GRAPHIC_NOVEL_SCRIPT = 'GRAPHIC_NOVEL_SCRIPT', 'Graphic Novel Script'
        GRAPHIC_NOVEL_IMAGES = 'GRAPHIC_NOVEL_IMAGES', 'Graphic Novel Images'
        INFOGRAPHIC_DESIGN = 'INFOGRAPHIC_DESIGN', 'Infographic Design'
        INFOGRAPHIC_IMAGE = 'INFOGRAPHIC_IMAGE', 'Infographic Image'
        GRAPHIC_NOVEL_6PAGE_SCRIPT = 'GN_6PAGE_SCRIPT', 'Graphic Novel 6-Page Script'
        GRAPHIC_NOVEL_6PAGE_IMAGES = 'GN_6PAGE_IMAGES', 'Graphic Novel 6-Page Images'

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


# =============================================================================
# LLM CONFIGURATION MODELS
# =============================================================================

class LLMSite(models.Model):
    class ProviderType(models.TextChoices):
        GEMINI_NATIVE = 'gemini_native', 'Gemini (Native)'
        OPENAI_COMPATIBLE = 'openai_compatible', 'OpenAI-Compatible'
        ANTHROPIC = 'anthropic', 'Anthropic'

    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(
        max_length=300, blank=True, default='',
        help_text='Leave blank for native SDK default endpoint.',
    )
    api_key_env_var = models.CharField(
        max_length=100,
        help_text='Environment variable name holding the API key.',
    )
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'LLM Site'

    def __str__(self) -> str:
        return f"{self.name} ({self.get_provider_type_display()})"

    def resolve_api_key(self) -> str:
        import os
        return os.environ.get(self.api_key_env_var, '')


class LLMConfigSet(models.Model):
    """A named collection of per-step LLM configs. Exactly one set is active at
    a time; the pipeline reads step configs from the active set. Sets are seeded
    (3 of them) by migration — there is no create/delete in the app."""
    name = models.CharField(max_length=100)
    position = models.PositiveSmallIntegerField(
        unique=True,
        help_text='Stable display/sort order (1-based).',
    )
    is_active = models.BooleanField(
        default=False,
        help_text='Exactly one set is active; the pipeline uses it.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'LLM Config Set'
        ordering = ['position']

    def __str__(self) -> str:
        return f"{self.name}{' (active)' if self.is_active else ''}"


class LLMStepConfig(models.Model):
    class StepKey(models.TextChoices):
        WORD_LOOKUP = 'word_lookup', 'Word Lookup'
        TRANSLATION = 'translation', 'Translation'
        QUESTION_GEN = 'question_gen', 'Question Generation'
        PRIMER_GEN = 'primer_gen', 'Primer Generation'
        PACK_CREATION = 'pack_creation', 'Pack Grouping'
        GN_TEAM_SELECTION = 'gn_team_selection', 'GN: Team Selection'
        GN_ROUTER_PREMISES = 'gn_router_premises', 'GN: Router Premises'
        GN_PREMISE_SCORING = 'gn_premise_scoring', 'GN: Premise Scoring'
        GN_CLOZE_GEN = 'gn_cloze_gen', 'GN: Cloze Generation'
        GN_BEAT_SHEET = 'gn_beat_sheet', 'GN: Beat Sheet'
        GN_FINAL_SCRIPT = 'gn_final_script', 'GN: Final Script'
        IG_DESIGN = 'ig_design', 'Infographic: Design'
        IG_CLOZE_GEN = 'ig_cloze', 'Infographic: Cloze Generation'
        AUDIOBOOK_DIRECTOR = 'audiobook_director', 'Audiobook: Voice Director'

    config_set = models.ForeignKey(
        LLMConfigSet, on_delete=models.CASCADE, related_name='step_configs',
    )
    step_key = models.CharField(max_length=30, choices=StepKey.choices)
    primary_site = models.ForeignKey(
        LLMSite, on_delete=models.PROTECT, related_name='primary_steps',
    )
    primary_model = models.CharField(max_length=100)
    fallback_site = models.ForeignKey(
        LLMSite, on_delete=models.PROTECT, related_name='fallback_steps',
    )
    fallback_model = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'LLM Step Configuration'
        verbose_name_plural = 'LLM Step Configurations'
        unique_together = ('config_set', 'step_key')

    def __str__(self) -> str:
        return f"{self.config_set.name}/{self.get_step_key_display()} → {self.primary_model}"
