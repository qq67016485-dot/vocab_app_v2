QUESTION_TYPE_TO_SKILL_TAG = {
    'DEFINITION_MC_SINGLE': 'definition_recall',
    'DEFINITION_TRUE_FALSE': 'definition_recall',
    'DEFINITION_MATCHING': 'definition_recall',
    'REVERSE_DEFINITION_MC': 'definition_recall',
    'CONTEXT_MC_SINGLE': 'context_nuance',
    'CONTEXT_FILL_IN_BLANK': 'context_nuance',
    'CONNOTATION_SORTING': 'context_nuance',
    'APPLICATION_MC': 'context_nuance',
    'REVERSE_ASSOCIATION_MC': 'context_nuance',
    'SYNONYM_MC_SINGLE': 'synonym_antonym',
    'SYNONYM_MC_MULTI': 'synonym_antonym',
    'SYNONYM_MATCHING': 'synonym_antonym',
    'SYNONYM_IN_CONTEXT_MC': 'synonym_antonym',
    'REVERSE_SYNONYM_IN_CONTEXT_MC': 'synonym_antonym',
    'ANTONYM_MC_SINGLE': 'synonym_antonym',
    'ANTONYM_MATCHING': 'synonym_antonym',
    'ODD_ONE_OUT_MC_SINGLE': 'synonym_antonym',
    'NUANCE_CONTRAST_MC': 'synonym_antonym',
    'WORD_FORM_MC': 'word_forms',
    'WORD_FORM_FILL_IN_BLANK': 'word_forms',
    'SENTENCE_SCRAMBLE': 'syntax_grammar',
    'DIALOGUE_COMPLETION_MC': 'context_nuance',
    'SPELLING_FILL_IN_BLANK': 'spelling',
    'COLLOCATION_MC_SINGLE': 'collocation_usage',
    'COLLOCATION_FILL_IN_BLANK': 'collocation_usage',
    'COLLOCATION_MATCHING': 'collocation_usage',
    'REVERSE_COLLOCATION_MC': 'collocation_usage',
    'CONCEPTUAL_ASSOCIATION_MC_SINGLE': 'conceptual_association',
    'SENTENCE_WRITE_GUIDED': 'sentence_production',
    'SENTENCE_WRITE_OPEN': 'sentence_production',
}

QUESTION_TYPE_TO_PATTERN = {
    'DEFINITION_MC_SINGLE': 'Definition Recall',
    'DEFINITION_TRUE_FALSE': 'Definition Recall',
    'REVERSE_DEFINITION_MC': 'Definition Recall',
    'CONTEXT_MC_SINGLE': 'Context & Nuance',
    'APPLICATION_MC': 'Context & Nuance',
    'REVERSE_ASSOCIATION_MC': 'Context & Nuance',
    'SYNONYM_MC_SINGLE': 'Synonym & Antonym',
    'SYNONYM_IN_CONTEXT_MC': 'Synonym & Antonym',
    'REVERSE_SYNONYM_IN_CONTEXT_MC': 'Synonym & Antonym',
    'ANTONYM_MC_SINGLE': 'Synonym & Antonym',
    'ODD_ONE_OUT_MC_SINGLE': 'Synonym & Antonym',
    'NUANCE_CONTRAST_MC': 'Synonym & Antonym',
    'WORD_FORM_MC': 'Word Forms',
    'WORD_FORM_FILL_IN_BLANK': 'Word Forms',
    'SENTENCE_SCRAMBLE': 'Syntax & Grammar',
    'DIALOGUE_COMPLETION_MC': 'Context & Nuance',
    'SPELLING_FILL_IN_BLANK': 'Spelling',
    'CONTEXT_FILL_IN_BLANK': 'Context & Nuance',
    'COLLOCATION_MC_SINGLE': 'Collocation & Usage',
    'REVERSE_COLLOCATION_MC': 'Collocation & Usage',
    'CONCEPTUAL_ASSOCIATION_MC_SINGLE': 'Conceptual Association',
    'SENTENCE_WRITE_GUIDED': 'Sentence Production',
    'SENTENCE_WRITE_OPEN': 'Sentence Production',
}

# Mastery level per question type (avoids asking the LLM to output suitable_mastery_levels).
QUESTION_TYPE_LEVEL = {
    # Level 1 – Recognition
    'DEFINITION_MC_SINGLE': 1,
    'DEFINITION_TRUE_FALSE': 1,
    'REVERSE_DEFINITION_MC': 1,
    # Level 2 – Relationships
    'SYNONYM_MC_SINGLE': 2,
    'SYNONYM_IN_CONTEXT_MC': 2,
    'REVERSE_SYNONYM_IN_CONTEXT_MC': 2,
    'ANTONYM_MC_SINGLE': 2,
    'CONCEPTUAL_ASSOCIATION_MC_SINGLE': 2,
    # Level 3 – Context & Application
    'CONTEXT_MC_SINGLE': 3,
    'APPLICATION_MC': 3,
    'REVERSE_ASSOCIATION_MC': 3,
    'DIALOGUE_COMPLETION_MC': 3,
    # Level 4 – Nuance & Usage
    'WORD_FORM_MC': 4,
    'COLLOCATION_MC_SINGLE': 4,
    'REVERSE_COLLOCATION_MC': 4,
    # Level 5 – Deep Comparison
    'ODD_ONE_OUT_MC_SINGLE': 5,
    'NUANCE_CONTRAST_MC': 5,
    # Productive sentence writing — gated at the top of the ladder. Guided
    # (more scaffolding) enters at L4; Open (freer) at L5. See
    # docs/feature_plan/design-sentence-writing-questions.md.
    'SENTENCE_WRITE_GUIDED': 4,
    'SENTENCE_WRITE_OPEN': 5,
}
