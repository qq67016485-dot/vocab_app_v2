"""
Shared test fixtures for generation pipeline tests.

Sample LLM response data used across all generation test modules.
"""

# Sample LLM response data used across tests
WORD_LOOKUP_RESPONSE = {
    "words": [
        {
            "term": "bright",
            "part_of_speech": "adjective",
            "definition": "Giving out or reflecting a lot of light; shining.",
            "example_sentence": "The bright stars lit up the night sky.",
            "lexile_score": 600,
            "source_context": "From test book",
        },
        {
            "term": "discover",
            "part_of_speech": "verb",
            "definition": "To find something for the first time.",
            "example_sentence": "She wanted to discover new places.",
            "lexile_score": 650,
            "source_context": "From test book",
        },
    ]
}

TRANSLATION_RESPONSE = {
    "translations": [
        {
            "term": "bright",
            "source_field": "definition_text",
            "source_text": "Giving out or reflecting a lot of light; shining.",
            "translated_text": "bright definition translation",
        },
        {
            "term": "bright",
            "source_field": "example_sentence",
            "source_text": "The bright stars lit up the night sky.",
            "translated_text": "bright example translation",
        },
        {
            "term": "discover",
            "source_field": "definition_text",
            "source_text": "To find something for the first time.",
            "translated_text": "discover definition translation",
        },
        {
            "term": "discover",
            "source_field": "example_sentence",
            "source_text": "She wanted to discover new places.",
            "translated_text": "discover example translation",
        },
    ]
}

QUESTION_RESPONSE = {
    "generated_question_sets": [
        {
            "term": "bright",
            "questions": [
                {
                    "question_type": "DEFINITION_MC_SINGLE",
                    "question_text": "What does 'bright' mean?",
                    "options": ["Shining", "Dark", "Quiet", "Slow"],
                    "correct_answers": ["Shining"],
                    "explanation": "Bright means giving out light.",
                    "example_sentence": "The sun is very bright today.",
                    "lexile_score": 600,
                },
            ],
        },
    ],
}

PRIMER_RESPONSE = {
    "primer_cards": [
        {
            "term": "bright",
            "syllable_text": "bright",
            "kid_friendly_definition": "Something that shines a lot.",
            "example_sentence": "The bright sun makes me happy!",
        },
        {
            "term": "discover",
            "syllable_text": "dis-cov-er",
            "kid_friendly_definition": "To find something new.",
            "example_sentence": "I want to discover what is inside the box.",
        },
    ]
}

STORY_CLOZE_RESPONSE = {
    "micro_story": {
        "story_text": "The **bright** sun rose over the hills. Maya wanted to **discover** what was in the cave.",
        "reading_level": 650,
    },
    "cloze_items": [
        {
            "term": "bright",
            "sentence_text": "The _______ light woke me up early.",
            "correct_answer": "bright",
            "distractors": ["dark", "quiet"],
        },
        {
            "term": "discover",
            "sentence_text": "Scientists _______ new species every year.",
            "correct_answer": "discover",
            "distractors": ["ignore", "forget"],
        },
    ],
}

GRAPHIC_NOVEL_CLOZE_RESPONSE = {
    "cloze_items": [
        {
            "term": "bright",
            "sentence_text": "The _______ light woke me up early.",
            "correct_answer": "bright",
            "distractors": ["dark", "quiet"],
        },
        {
            "term": "discover",
            "sentence_text": "Scientists _______ new species every year.",
            "correct_answer": "discover",
            "distractors": ["ignore", "forget"],
        },
    ],
}

GRAPHIC_NOVEL_RESPONSE = {
    "title": "The Bright Discovery",
    "synopsis": "Maya follows a bright signal into a cave and discovers a hidden workshop.",
    "characters": [
        {"name": "Leo", "visual_description": "Leo wears a bright red hoodie and carries a cyan wax crayon."},
        {"name": "Amara", "visual_description": "Amara wears a purple and gold cloak and carries a golden quill."},
    ],
    "style_prompt": "Bright middle-grade comic art with clear panel borders.",
    "reading_level": 650,
    "pages": [
        {
            "page_number": 1,
            "panel_count": 2,
            "layout_description": "Two equal panels side by side.",
            "characters_featured": ["Leo"],
            "setting_key": "the_vault",
            "vault_zone": "map_platform",
            "is_vault_page": True,
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "Maya sees a bright light in the hills.",
                    "narration": "A bright signal flashed above the ridge.",
                    "dialogue": [],
                    "vocab_words": ["bright"],
                    "vocab_highlight_note": "Render 'bright' in glowing gold.",
                    "alt_text": "Maya sees a bright light.",
                },
                {
                    "panel_number": 2,
                    "scene_description": "Maya enters a cave with a notebook.",
                    "narration": "",
                    "dialogue": [{"speaker": "Maya", "text": "I will discover the source."}],
                    "vocab_words": ["discover"],
                    "vocab_highlight_note": "Render 'discover' in glowing gold.",
                    "alt_text": "Maya enters a cave.",
                },
            ],
        },
        {
            "page_number": 2,
            "panel_count": 2,
            "layout_description": "One wide panel over one narrow panel.",
            "characters_featured": ["Leo"],
            "setting_key": "story_realm",
            "vault_zone": "",
            "is_vault_page": False,
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "The cave door slides shut behind Maya.",
                    "narration": "The problem grew bigger.",
                    "dialogue": [],
                    "vocab_words": [],
                    "vocab_highlight_note": "",
                    "alt_text": "The cave door closes.",
                },
                {
                    "panel_number": 2,
                    "scene_description": "Maya studies a glowing machine.",
                    "narration": "",
                    "dialogue": [{"speaker": "Maya", "text": "This clue is bright enough to follow."}],
                    "vocab_words": ["bright"],
                    "vocab_highlight_note": "Render 'bright' in glowing gold.",
                    "alt_text": "Maya studies a glowing machine.",
                },
            ],
        },
        {
            "page_number": 3,
            "panel_count": 2,
            "layout_description": "Two stacked panels.",
            "characters_featured": ["Leo"],
            "setting_key": "story_realm",
            "vault_zone": "",
            "is_vault_page": False,
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "Maya tries the wrong lever.",
                    "narration": "Her first plan failed.",
                    "dialogue": [],
                    "vocab_words": [],
                    "vocab_highlight_note": "",
                    "alt_text": "Maya pulls a lever.",
                },
                {
                    "panel_number": 2,
                    "scene_description": "Sparks flash across the workshop.",
                    "narration": "",
                    "dialogue": [{"speaker": "Maya", "text": "I need to discover the real pattern."}],
                    "vocab_words": ["discover"],
                    "vocab_highlight_note": "Render 'discover' in glowing gold.",
                    "alt_text": "Sparks flash in the workshop.",
                },
            ],
        },
        {
            "page_number": 4,
            "panel_count": 3,
            "layout_description": "One large action panel with two small reaction panels.",
            "characters_featured": ["Leo", "Amara"],
            "setting_key": "story_realm",
            "vault_zone": "",
            "is_vault_page": False,
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "Maya aims the bright signal at the lock.",
                    "narration": "",
                    "dialogue": [{"speaker": "Maya", "text": "The bright signal shows the way."}],
                    "vocab_words": ["bright"],
                    "vocab_highlight_note": "Render 'bright' in glowing gold.",
                    "alt_text": "Maya points the signal at the lock.",
                },
                {
                    "panel_number": 2,
                    "scene_description": "Gears begin to turn.",
                    "narration": "The workshop answered.",
                    "dialogue": [],
                    "vocab_words": [],
                    "vocab_highlight_note": "",
                    "alt_text": "Gears turn.",
                },
                {
                    "panel_number": 3,
                    "scene_description": "The exit opens.",
                    "narration": "",
                    "dialogue": [],
                    "vocab_words": [],
                    "vocab_highlight_note": "",
                    "alt_text": "The exit opens.",
                },
            ],
        },
        {
            "page_number": 5,
            "panel_count": 2,
            "layout_description": "Two calm resolution panels.",
            "characters_featured": ["Leo"],
            "setting_key": "the_vault",
            "vault_zone": "field_desk",
            "is_vault_page": True,
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "Maya steps into daylight.",
                    "narration": "Maya had made a bright discovery.",
                    "dialogue": [],
                    "vocab_words": ["bright", "discover"],
                    "vocab_highlight_note": "Render 'bright' and 'discovery' in glowing gold.",
                    "alt_text": "Maya exits the cave.",
                },
                {
                    "panel_number": 2,
                    "scene_description": "Maya sketches the workshop in her notebook.",
                    "narration": "",
                    "dialogue": [{"speaker": "Maya", "text": "Now others can discover it too."}],
                    "vocab_words": ["discover"],
                    "vocab_highlight_note": "Render 'discover' in glowing gold.",
                    "alt_text": "Maya draws in her notebook.",
                },
            ],
        },
    ],
    "vocab_anchors": {
        "bright": {
            "anchor_type": "visible_referent",
            "anchor_text": "A glowing signal panel labeled BRIGHT lights the cave door.",
        },
        "discover": {
            "anchor_type": "demonstrated_action",
            "anchor_sketch": "Maya peels back a panel to DISCOVER the hidden switch.",
            "anchor_text": "Maya peels back a panel to DISCOVER the hidden switch.",
        },
    },
}

GRAPHIC_NOVEL_TEAM_RESPONSE = {
    "selected_away_team": ["Leo", "Amara"],
    "vault_framing": True,
    "team_rationale": "Leo brings action and Amara brings careful clue-reading.",
}

GRAPHIC_NOVEL_ROUTER_RESPONSE = {
    "audience_age_band": "upper elementary",
    "tone": "playful suspense",
    "genre": "science adventure",
    "story_engine": "mini mystery",
    "visual_potential": "High",
    "hard_to_integrate_words": [],
    "routing_modules": {
        "age_voice_module": "upper-elementary-playful",
        "reading_level_module": "lexile-450-600",
        "story_engine_module": "mini-mystery",
        "genre_world_module": "science-adventure-cave",
        "vocab_module": "words-as-clues",
    },
    "premises": [
        {
            "id": "premise_1",
            "title": "The Bright Discovery",
            "story_engine": "mini mystery",
            "premise": "Maya follows a signal into a cave and must solve the workshop lock.",
            "central_thread": "The cave door closes.",
            "protagonist_goal": "Escape and understand the signal.",
            "visual_hooks": ["glowing cave door"],
            "page_count_rationale": "A short mystery resolves cleanly in five pages.",
            "page_count": 5,
            "complexity_budget": {
                "locations": ["cave entrance", "workshop"],
                "secondary_characters": [],
                "problem_thread": "Maya must reopen the cave door so she can return home.",
            },
            "total_ink_activations_planned": 0,
            "mini_justification": None,
            "vocab_integration_plan": [
                {
                    "term": "bright",
                    "story_role": "clue",
                    "integration_mode": "visual_clue",
                    "uses_direct_ink": False,
                    "pedagogical_anchor": {
                        "anchor_type": "visible_referent",
                        "anchor_sketch": "A glowing lamp on the door is labeled BRIGHT so readers see the meaning.",
                    },
                },
                {
                    "term": "discover",
                    "story_role": "solution action",
                    "integration_mode": "reasoning",
                    "uses_direct_ink": False,
                    "pedagogical_anchor": {
                        "anchor_type": "demonstrated_action",
                        "anchor_sketch": "Maya peels back a panel and DISCOVERS the hidden switch on screen.",
                    },
                },
            ],
            "flatness_risk": "low",
        },
        {
            "id": "premise_2",
            "title": "Signal Rescue",
            "story_engine": "rescue mission",
            "premise": "Maya follows a trapped signal and uses the bright clue to rescue a workshop bot.",
            "central_thread": "A helper bot is trapped behind a locked door.",
            "protagonist_goal": "Rescue the bot.",
            "visual_hooks": ["sparking robot behind glass"],
            "page_count_rationale": "Rescue arc fits five pages without rushing.",
            "page_count": 5,
            "complexity_budget": {
                "locations": ["cave path", "workshop"],
                "secondary_characters": ["helper bot"],
                "problem_thread": "Maya must free the helper bot trapped behind the door.",
            },
            "total_ink_activations_planned": 0,
            "mini_justification": None,
            "vocab_integration_plan": [
                {
                    "term": "bright",
                    "story_role": "signal",
                    "integration_mode": "visual_clue",
                    "uses_direct_ink": False,
                    "pedagogical_anchor": {
                        "anchor_type": "visible_referent",
                        "anchor_sketch": "A BRIGHT signal lamp pulses on the bot's chest, framed for the reader.",
                    },
                },
                {
                    "term": "discover",
                    "story_role": "hidden route",
                    "integration_mode": "character_action",
                    "uses_direct_ink": False,
                    "pedagogical_anchor": {
                        "anchor_type": "demonstrated_action",
                        "anchor_sketch": "Maya kneels and DISCOVERS a hidden vent leading to the bot.",
                    },
                },
            ],
            "flatness_risk": "low",
        },
        {
            "id": "premise_3",
            "title": "The Cave Switch",
            "story_engine": "invention mishap",
            "premise": "Maya triggers an old machine and must discover how to stop the bright overload.",
            "central_thread": "The old machine overloads.",
            "protagonist_goal": "Stop the overload.",
            "visual_hooks": ["glowing gears"],
            "page_count_rationale": "Invention mishap and Mini summon need a sixth page to breathe.",
            "page_count": 6,
            "complexity_budget": {
                "locations": ["cave entrance", "machine room"],
                "secondary_characters": [],
                "problem_thread": "Maya must shut down the machine before it overloads.",
            },
            "total_ink_activations_planned": 1,
            "mini_justification": "Maya summons a Lexi Mini that physically demonstrates DISCOVER by uncovering the hidden shut-off switch.",
            "vocab_integration_plan": [
                {
                    "term": "bright",
                    "story_role": "warning",
                    "integration_mode": "world_logic",
                    "uses_direct_ink": False,
                    "pedagogical_anchor": {
                        "anchor_type": "visible_referent",
                        "anchor_sketch": "BRIGHT warning lights flare across the gears as the overload starts.",
                    },
                },
                {
                    "term": "discover",
                    "story_role": "solution action",
                    "integration_mode": "lexi_mini_summon",
                    "uses_direct_ink": True,
                    "pedagogical_anchor": {
                        "anchor_type": "demonstrated_action",
                        "anchor_sketch": "A Lexi Mini lifts a panel to DISCOVER the shut-off switch beneath.",
                    },
                },
            ],
            "flatness_risk": "medium",
        },
    ],
}

GRAPHIC_NOVEL_SCORING_RESPONSE = {
    "scores": [
        {
            "premise_id": "premise_1",
            "narrative_clarity": 5,
            "visual_potential": 5,
            "vocabulary_integration": 5,
            "pedagogical_clarity": 5,
            "character_fit": 5,
            "total": 25,
            "flatness_risk": "low",
            "notes": "Strong agency.",
        },
        {
            "premise_id": "premise_2",
            "narrative_clarity": 4,
            "visual_potential": 5,
            "vocabulary_integration": 4,
            "pedagogical_clarity": 4,
            "character_fit": 4,
            "total": 21,
            "flatness_risk": "low",
            "notes": "Strong but less mysterious.",
        },
        {
            "premise_id": "premise_3",
            "narrative_clarity": 4,
            "visual_potential": 4,
            "vocabulary_integration": 4,
            "pedagogical_clarity": 4,
            "character_fit": 4,
            "total": 20,
            "flatness_risk": "medium",
            "notes": "Useful but more familiar.",
        },
    ],
    "winning_premise_id": "premise_1",
    "winning_premise": GRAPHIC_NOVEL_ROUTER_RESPONSE["premises"][0],
    "confidence": 0.9,
    "judge_notes": "Best cause/effect story.",
}

GRAPHIC_NOVEL_BEAT_RESPONSE = {
    "beat_sheet": [
        {
            "page": 1,
            "story_beat": "setup + inciting incident",
            "page_turn_question": "What is inside?",
            "emotional_change": "curious -> shocked",
            "vocab_words": ["bright"],
            "characters_featured": ["Leo"],
            "setting_key": "the_vault",
            "vault_zone": "map_platform",
            "is_vault_page": True,
            "why_this_page_matters": "Introduces clue.",
        },
        {
            "page": 2,
            "story_beat": "problem becomes bigger",
            "page_turn_question": "How can Maya escape?",
            "emotional_change": "shocked -> worried",
            "vocab_words": ["bright"],
            "characters_featured": ["Leo"],
            "setting_key": "story_realm",
            "vault_zone": "",
            "is_vault_page": False,
            "why_this_page_matters": "Raises stakes.",
        },
        {
            "page": 3,
            "story_beat": "failed attempt",
            "page_turn_question": "What pattern matters?",
            "emotional_change": "worried -> focused",
            "vocab_words": ["discover"],
            "characters_featured": ["Leo"],
            "setting_key": "story_realm",
            "vault_zone": "",
            "is_vault_page": False,
            "why_this_page_matters": "Shows complication.",
        },
        {
            "page": 4,
            "story_beat": "action solves problem",
            "page_turn_question": "Will the door open?",
            "emotional_change": "focused -> brave",
            "vocab_words": ["bright"],
            "characters_featured": ["Leo", "Amara"],
            "setting_key": "story_realm",
            "vault_zone": "",
            "is_vault_page": False,
            "why_this_page_matters": "Climax.",
        },
        {
            "page": 5,
            "story_beat": "resolution + vocabulary reuse",
            "page_turn_question": "Who will see it next?",
            "emotional_change": "brave -> proud",
            "vocab_words": ["bright", "discover"],
            "characters_featured": ["Leo"],
            "setting_key": "the_vault",
            "vault_zone": "field_desk",
            "is_vault_page": True,
            "why_this_page_matters": "Resolves story.",
        },
    ],
    "vocab_roles": {"bright": "clue", "discover": "solution action"},
    "total_ink_activations_planned": 0,
    "ink_usage": [
        {
            "term": "bright",
            "page": 1,
            "uses_direct_ink": False,
            "purpose": "Bright is a visual clue.",
        },
        {
            "term": "discover",
            "page": 3,
            "uses_direct_ink": False,
            "purpose": "Discover describes Leo reasoning through the pattern.",
        },
    ],
    "review_artifact_type": "Vault clue board",
    "quality_notes": {
        "words_affecting_plot": ["bright", "discover"],
        "protagonist_agency": "Maya solves the lock herself.",
        "anti_flatness_guard": "Words drive clues and action.",
    },
}


def build_six_page_beat_response():
    """Beat response with 6 entries — matches GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[6]."""
    extra_page = {
        "page": 6,
        "story_beat": "denouement + final reuse",
        "page_turn_question": None,
        "emotional_change": "proud -> reflective",
        "vocab_words": ["discover"],
        "characters_featured": ["Leo"],
        "setting_key": "the_vault",
        "vault_zone": "field_desk",
        "is_vault_page": True,
        "why_this_page_matters": "Final reflection.",
    }
    return {
        **GRAPHIC_NOVEL_BEAT_RESPONSE,
        "beat_sheet": list(GRAPHIC_NOVEL_BEAT_RESPONSE["beat_sheet"]) + [extra_page],
    }


def build_six_page_script_response():
    """Final script response with 6 story pages."""
    extra_page = {
        "page_number": 6,
        "panel_count": 1,
        "layout_description": "Single quiet reflection panel.",
        "characters_featured": ["Leo"],
        "setting_key": "the_vault",
        "vault_zone": "field_desk",
        "is_vault_page": True,
        "panels": [
            {
                "panel_number": 1,
                "scene_description": "Maya pins her notes to the discovery wall.",
                "narration": "Maya filed her bright discovery for the next team.",
                "dialogue": [],
                "vocab_words": ["bright", "discover"],
                "vocab_highlight_note": "Render 'bright' and 'discover' in glowing gold.",
                "alt_text": "Maya pins notes to the wall.",
            },
        ],
    }
    return {
        **GRAPHIC_NOVEL_RESPONSE,
        "pages": list(GRAPHIC_NOVEL_RESPONSE["pages"]) + [extra_page],
    }
