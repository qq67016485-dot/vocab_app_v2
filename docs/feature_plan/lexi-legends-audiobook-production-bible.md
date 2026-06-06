# Lexi Legends Audiobook Production Bible

Status: Phase 1-2 production companion
Canonical sources: `docs/feature_plan/lexi-legends-setting-bible.md`, `backend/data/canon/lexi-legends-cast-bible.md`, the per-hero image sheets in `backend/data/canon/script-character-sheets.md`, and the team-selection summaries in `backend/data/canon/team-selector-summaries.md`
Created: 2026-05-20
Last updated: 2026-06-07 — synced to current canon (Folio and Shades removed; cast is Leo, Amara, Mei, Hugo; Ink VFX replaced by Lexi Mini summons; provider decided)

## Canon Changes Since Creation (read first)

This bible was written on 2026-05-20. The graphic novel pipeline has since changed in ways that affect audio. The sections below have been updated to match, but the headline changes are:

- **Folio is gone.** The origami-owl guide is no longer part of canon. All Folio voice direction, the `folio` speaker type, and Folio pronunciation entries have been removed. Vocabulary clarification now happens only through the script itself (a hero's dialogue/narration), never a separate guide voice.
- **Shades are gone.** The antagonist "Shade" concept was removed. Shade ambience/SFX and the "don't make Shades sound like horror" rule no longer apply.
- **Cast is exactly four heroes:** Leo, Amara, Mei, Hugo (`canon_service.LEXI_CHARACTERS`). Their voice profiles below are current.
- **Ink VFX → Lexi Mini summons.** Writing a vocab word with a hero's tool can summon a temporary creature that acts out the word's meaning (hard cap 0–1 per story). Minis are *silent visual* events — they have no dialogue and are not voiced. Tools: Leo = cyan wax crayon, Amara = golden quill, Mei = multicolor marker, Hugo = orange carpenter's pencil.
- **Page format is 5 or 6 pages,** chosen deterministically from the pack's word count (>4 words → 6 pages). `GraphicNovel.Channel` is `FIVE_PAGE`/`SIX_PAGE`; `metadata['page_count']` records the length. Audio is generated per stored page.

## Purpose

This production bible defines the future read-along audiobook direction for Lexi Legends graphic novels. The target experience is an immersive, high-production audio track that learners can play while reading the comic pages.

The goal is not flat text-to-speech. The goal is clear pronunciation, expressive character performance, light scene atmosphere, and audio timing that helps the learner follow the page.

## Current Provider Note

Selected provider/model (2026-06-07): **Gemini 2.5 Pro Preview TTS** (`gemini-2.5-pro-preview-tts`) for the read-along audio. Google's Gemini speech-generation docs describe controllable native TTS suitable for audiobook-style use, list Gemini 2.5 Flash Preview TTS and Gemini 2.5 Pro Preview TTS as supported TTS models, and note that multi-speaker TTS supports **up to 2 speakers per request** (see the two-speaker strategy in Micro-Segmentation Workflow). Re-verify model name, voice list, and the 2-speaker limit against the current docs at implementation time, since preview models change.

The project already routes Gemini through `vocabulary/services/llm_service.py` (`call_gemini`), with optional `GEMINI_BASE_URL` proxy support; the TTS path can follow the same key/proxy resolution. Note that `call_gemini` is JSON-only — TTS will need its own audio-returning call path, not the existing text wrapper.

Reference: https://ai.google.dev/gemini-api/docs/speech-generation

This bible is provider-aware but not provider-locked. The production rules should still apply if the implementation uses a different TTS provider later.

## Production Target

Audio style:
- Immersive multi-cast or radio-play read-along.
- Narrator plus distinct character performances.
- Light ambience and restrained sound effects.
- Page-level audio tracks that sync with graphic novel pages.
- Panel-aware pacing with short pauses that let the learner's eyes move.
- Clear pronunciation and prosody for vocabulary acquisition.

Do not produce:
- Flat monotone narration.
- Overly theatrical chaos that distracts from reading.
- Background sound that covers words.
- Extra dialogue not present in the graphic novel text.
- Character voices that mock accents or learner identities.

## Source Of Truth

All audiobook text should derive from `GraphicNovel` and `GraphicNovelPage` rows (verified against the live schema, `vocabulary/models.py`):

`GraphicNovel`:
- `title`
- `synopsis`
- `characters` (list of `{name, visual_description}`)
- `style_prompt`
- `metadata` (e.g. `age_band` = `'9yo'` / `'12yo'`, `away_team`, `page_count`, `vault_framing`, `review_artifact_type`)

`GraphicNovelPage`:
- `page_number`
- `panel_count`
- `layout_description`
- `panel_descriptions` — the per-panel list; **this is the spoken-text source.** Each entry holds: `panel_number`, `narration`, `dialogue` (list of `{speaker, text}`), `vocab_words`, `scene_description`, `alt_text`, and an optional `vocab_highlight_note`.
- `characters_featured`
- `vocab_words_used`
- `is_review_page`

Note the audio system reads `dialogue[*].speaker` / `dialogue[*].text` and `narration` straight from `panel_descriptions` — those fields match the final-script artifact verbatim, so no OCR of the rendered images is needed. The audio system may add direction, pauses, ambience, and emotional tags, but it must not invent new plot content or change the transcript.

## Age Presentation Audio Rules

Each generated pack should choose one Age Presentation presentation for the whole story: 9 years old or 12 years old. The visual and audio age band must match.

### 9 years old Audio Presentation

Target listener: around age 9.

Performance style:
- More playful, direct, open, and emotionally readable.
- Clearer emotional tags.
- Slightly slower pacing.
- More warmth in narration.
- Vocabulary words get gentle emphasis and clean pronunciation.
- Sound effects are simple and concrete.

Story audio tone:
- Wonder, humor, discovery, encouragement, clear problem-solving.
- Shorter emotional beats and more obvious transitions.

### 12 years old Audio Presentation

Target listener: around age 12.

Performance style:
- More nuanced, confident, witty, tactical, or emotionally subtle.
- Slightly faster pacing when appropriate, but never rushed.
- More cinematic ambience.
- Vocabulary emphasis is natural and context-driven.
- Character performances can carry subtext.

Story audio tone:
- Mystery, strategy, social tension, identity, layered choices.
- More room for pauses, suspense, and quiet emotional beats.

## Read-Along Timing

The audio should support the visual reading experience.

Timing defaults:
- Short pause between dialogue turns: 0.2 to 0.4 seconds.
- Pause after narration before dialogue: 0.4 to 0.7 seconds.
- Panel gutter pause: 1.0 to 1.5 seconds.
- Page-end pause: 1.5 to 2.5 seconds.
- Review page item pause: 0.7 to 1.0 seconds between word entries.

Age Presentation timing:
- 9 years old: prefer the longer end of timing ranges.
- 12 years old: use shorter pauses when the scene is active, longer pauses for suspense or emotional weight.

Do not auto-advance so quickly that the learner cannot inspect the art.

## Audio Event Model

Future implementation should slice each page into ordered speech events.

Suggested speech event fields:

```json
{
  "page_number": 1,
  "panel_number": 2,
  "event_index": 4,
  "speaker": "Leo",
  "speaker_type": "recurring_hero",
  "AGE_PRESENTATION": "9 years old",
  "text": "I think this word belongs here.",
  "source": "dialogue",
  "vocab_words": ["belongs"],
  "scene_context": "Leo crouches near a flickering sign in a moon market.",
  "performance_intent": "curious, building confidence",
  "pause_after_ms": 350
}
```

Speaker types:
- `narrator`
- `recurring_hero` (Leo, Amara, Mei, Hugo)
- `story_specific_character`
- `ambient_or_sfx`

A Lexi Mini summon is a silent visual creature, not a speaker — it never produces a speech event. Any spoken line during a summon belongs to a hero or narrator.

## Audio Director Prompt Structure

Every generated speech event should be converted into a rich audio prompt.

Recommended structure:

```text
# AUDIO PROFILE
Speaker: Leo
Age Presentation presentation: 9 years old
Voice direction: Bright, creative, eager, slightly impulsive, friendly.

## THE SCENE
Panel context: Leo crouches near a flickering sign in a moon market.
Mood: Curious, tense but safe.
Visual style: Premium animated graphic novel with cyan graffiti Ink.

### DIRECTOR'S NOTES
Read the line with quick curiosity. Leo is realizing the word might solve the sign problem. Keep the pronunciation of the target word clear. Do not add extra words.

#### TRANSCRIPT
[curious, quietly excited] "I think this word belongs here."
```

The director step should create performance direction, not new story content.

## Recurring Voice Profiles

### Narrator

Core role:
- Guides the learner through captions and scene-setting.
- Should be warm, clear, and emotionally present without stealing focus from characters.

narrator (9 years old):
- Gentle, inviting, slightly slower.
- Reads with clear transitions and a sense of wonder.
- Emphasizes target vocabulary lightly when first encountered.

narrator (12 years old):
- Warm but more cinematic.
- Can carry suspense, humor, and quiet emotional nuance.
- Uses natural emphasis instead of overt teaching tone.

Do not:
- Sound like a test proctor.
- Over-explain definitions unless the text itself does.
- Add commentary outside the script.

### Leo

Core voice:
- Creative, bright, energetic, friendly.
- Speaks in quick images and playful observations.
- Can admit confusion without embarrassment.

Leo (9 years old):
- Slightly higher energy, more open excitement.
- Quick but not hard to understand.
- Emotional range: amazed, sheepish, determined, proud, worried-then-brave.
- Performance tags: `[excited]`, `[trying an idea]`, `[oops, then hopeful]`, `[with a grin]`.

Leo (12 years old):
- Still energetic, but more intentional and witty.
- Less breathless, more rhythmic.
- Emotional range: confident, clever, amused, vulnerable, focused.
- Performance tags: `[dryly amused]`, `[focused]`, `[quietly impressed]`, `[confident but careful]`.

Vocabulary performance:
- When Leo uses a target word, he should sound like he is testing how it fits.
- If he misjudges a word, the performance can show realization, not shame.

### Amara

Core voice:
- Thoughtful, precise, calm, observant.
- Speaks with careful word choice.
- Can be quietly funny.

Amara (9 years old):
- Curious and careful.
- Warm clarity, with audible discovery when she notices a clue.
- Emotional range: intrigued, cautious, delighted, concerned, brave.
- Performance tags: `[softly curious]`, `[noticing a clue]`, `[carefully]`, `[with quiet excitement]`.

Amara (12 years old):
- Composed, precise, subtly dry.
- Can carry mystery and intellectual confidence.
- Emotional range: focused, skeptical, satisfied, quietly urgent, protective.
- Performance tags: `[measured]`, `[dryly]`, `[piecing it together]`, `[low and certain]`.

Vocabulary performance:
- Target words should sound exact and intentional.
- Amara is good for subtle distinctions and definitions-in-context.

### Mei

Core voice:
- Fast, alert, kinetic, route-smart, confident.
- Speaks in action, timing, direction, handoffs, and tactical observations.
- Friendly competitive energy.
- Current visual/audio cue: Mei has one glowing multicolor marker; marker-cap taps are singular, quick, and rhythmic rather than a paired-marker sound.

Mei (9 years old):
- Energetic and reactive.
- Big emotional reads, but keep diction clean.
- Emotional range: excited, impatient, surprised, triumphant, worried, loyal.
- Performance tags: `[breathless]`, `[ready to move]`, `[urgent but clear]`, `[laughing]`.

Mei (12 years old):
- Sharper, more tactical, still fast.
- Controlled urgency, route awareness, and quick wit.
- Emotional range: focused, strategic, teasing, intense, relieved.
- Performance tags: `[quick and tactical]`, `[under her breath]`, `[focused sprint]`, `[sharp whisper]`.

Vocabulary performance:
- Even in fast scenes, target words must remain clean and intelligible.
- Mei can model that speed works best with accuracy, timing, and a signal others can follow.

### Hugo

Core voice:
- Gentle, grounded, warm, practical.
- Speaks concretely and carefully, often through building, testing, weight, fairness, and safety language.
- Carries reassurance without sounding timid.

Hugo (9 years old):
- Gentle and a little self-conscious.
- Slight pauses before difficult words can model careful thinking.
- Emotional range: uncertain, helpful, worried, relieved, quietly proud.
- Performance tags: `[carefully]`, `[checking himself]`, `[soft but steady]`, `[relieved]`.

Hugo (12 years old):
- Warm, steady, quietly confident.
- Slower than Mei or Leo, but never dull.
- Emotional range: calm under pressure, protective, thoughtful, proud, sincere.
- Performance tags: `[steady]`, `[reassuring]`, `[testing the weak point]`, `[thinking it through]`, `[quiet confidence]`.

Vocabulary performance:
- Hugo is the best model for struggling productively with a word.
- If he asks for clarification, the tone should normalize learning, not embarrassment.

## Story-Specific Character Voices

Story-specific characters may have distinct voices, but their profiles should stay simple.

Minimum voice profile:
- Age or age read.
- Role in story.
- Energy level.
- Accent policy if relevant.
- Emotional function.
- One performance note.

Rules:
- Do not create caricature accents.
- Do not use accent as a joke.
- Keep supporting voices secondary to the selected recurring heroes.
- If the character speaks only once, prefer a clear simple voice over elaborate performance.

## Canonical Pronunciation Guide

Use clear American English pronunciation unless a future pack explicitly chooses another supported English variety.

- Lexi Legends: LEK-see LEH-jends
- The Vault: thuh VAWLT
- Leo: LEE-oh
- Amara: ah-MAH-rah
- Mei: MAY
- Hugo: HYOO-goh
- Ink: INK
- Lexi Mini: LEK-see MIN-ee
- Lexi Minis: LEK-see MIN-eez
- Story Realm: STOH-ree RELM
- Story Realms: STOH-ree RELMZ

Vocabulary pronunciation:
- Target words should be pronounced clearly the first time they appear.
- If a target word has multiple accepted pronunciations, choose one and keep it consistent across the pack.
- If a target word is emotionally performed, the word must remain intelligible.

## Ambience And Sound Effects

Use ambience like a light production layer, not a movie soundtrack.

Allowed:
- Soft room tone.
- Gentle Vault ambience: soft page turns, low catalog-line hum, subtle platform glow, quiet page-screen shimmer, faint upper-dome paper-light shimmer.
- Realm ambience: market murmur, rain, distant crowd, wind, machine hum, water, footsteps.
- Lexi Mini summon effects (only when a summon actually occurs, 0–1 per story): a soft Ink-bloom shimmer as the creature forms and a gentle dissolve as it fades — matched to the hero's tool (Leo's cyan crayon, Amara's golden quill, Mei's multicolor marker, Hugo's orange carpenter's pencil). Keep these under any spoken line; never let a summon sound cover a vocabulary word.

Avoid:
- Loud music over speech.
- Startling jump sounds.
- Realistic weapon sounds.
- Comedic noises that undercut emotion.
- Too many effects in a vocabulary-heavy line.

Age Presentation ambience:
- 9 years old: simpler, warmer, more concrete effects.
- 12 years old: subtler, more atmospheric, more suspense-friendly.

## Vocabulary Audio Reinforcement

Audio should help learners connect word sound, meaning, and context.

Rules:
- Target words should be cleanly pronounced.
- Emotional delivery should reinforce meaning when natural.
- Do not over-enunciate every target word like a drill.
- Do not add definitions unless they are already part of the script (e.g. an in-context appositive a hero speaks).
- Use performance to carry meaning: if a character says "wheeze," the breath can be strained, but the word must still be clear.

Useful techniques:
- Slight emphasis on first occurrence.
- Tone matching the word meaning.
- Short pause after an important target word if the panel invites reflection.
- Subtle sound effect tied to Ink or action, never covering the word.

## Micro-Segmentation Workflow

Future production can use this pipeline:

1. Parse page metadata into panel order.
2. Slice each narration and dialogue item into speech events.
3. Map every speaker to a recurring or story-specific voice profile.
4. Generate rich audio prompts for each event using the Audio Director step.
5. Render each event with the selected TTS provider.
6. Insert dialogue, panel, and page pauses.
7. Stitch events into one page-level audio file.
8. Store page-level audio and optional timing metadata.
9. Let the reader UI play, pause, replay, and eventually auto-advance.

Two-speaker limitation strategy:
- If the TTS provider supports only two speakers per request, generate smaller events or two-speaker chunks.
- Keep narrator and a character in one chunk when useful.
- For scenes with more than two speakers, generate separate line slices and stitch them.
- Preserve voice consistency by using stable speaker profiles and provider voice selections.

## Page-Level Output Target

Future page audio should aim for:
- One audio file per graphic novel page.
- Optional timing metadata for panel-level highlighting later.
- Audio duration appropriate to page complexity.
- No recurring cost per student playback after generation.

Suggested future metadata:

```json
{
  "page_number": 1,
  "audio_url": "/media/graphic_novel_audio/page_1.mp3",
  "duration_ms": 42000,
  "events": [
    {
      "panel_number": 1,
      "speaker": "Narrator",
      "start_ms": 0,
      "end_ms": 5200,
      "text": "The Vault was quieter than usual."
    }
  ]
}
```

## Rich Prompt Capsules

### AUDIO_STYLE_CANON

Produce an immersive read-along audiobook for a Lexi Legends graphic novel. Use exact narration and dialogue from the page metadata. Add performance direction, light ambience, clear pronunciation, and panel-aware pacing, but do not invent new dialogue or plot content. The audio should feel like a polished radio-play companion to the comic, with readable speech always more important than effects.

### AGE_PRESENTATION_AUDIO_RULES

9 years old audio targets listeners around age 9: playful, direct, warm, emotionally readable, slightly slower, with clear target-word pronunciation. 12 years old audio targets listeners around age 12: nuanced, confident, cinematic, subtly witty or tactical when appropriate, with natural vocabulary emphasis. Use one age band consistently across the pack.

### VOICE_PROFILE_CANON

Narrator: warm, clear, emotionally present, never test-like. Leo: bright, creative, energetic, friendly; 9 years old is openly excited, 12 years old is witty and intentional. Amara: thoughtful, precise, calm; 9 years old is curious and careful, 12 years old is composed and subtly dry. Mei: fast, alert, kinetic, and route-smart; 9 years old is reactive and energetic, 12 years old is tactical, controlled, and aware of who can follow the signal. Hugo: gentle, grounded, practical, and builder-minded; 9 years old is careful and a little self-conscious, 12 years old is steady, test-oriented, and quietly confident.

### AUDIO_DIRECTOR_PROMPT_TEMPLATE

Use this structure for each speech event:

```text
# AUDIO PROFILE
Speaker: {speaker}
Age Presentation presentation: {nine_or_twelve_years_old}
Voice direction: {voice_profile}

## THE SCENE
Panel context: {scene_description}
Mood: {mood}
Visual style: {style_prompt}

### DIRECTOR'S NOTES
{emotional_direction}
Keep target words clear: {vocab_words}
Do not add, remove, or rewrite transcript words.

#### TRANSCRIPT
{emotional_tags} "{exact_text}"
```

### PAUSE_RULES

Use 0.2 to 0.4 seconds between dialogue turns, 0.4 to 0.7 seconds after narration before dialogue, 1.0 to 1.5 seconds between panels, 1.5 to 2.5 seconds at page end, and 0.7 to 1.0 seconds between review page word entries. 9 years old tracks should generally use the longer end of these ranges.

### SAFETY_AND_QUALITY_RULES

Do not add unscripted plot content. Do not mock accents. Do not use loud effects over speech. Do not rush target vocabulary. Do not use background music or ambience that reduces intelligibility. Do not voice a Lexi Mini — summons are silent visual events.

## Production Acceptance Checklist

Before implementing audiobook generation, confirm:
- The provider/model capability has been rechecked against current official docs.
- Each pack has one age band: 9 years old or 12 years old.
- Every recurring speaker maps to a stable voice profile.
- Every story-specific speaker has a minimal voice profile.
- Speech events preserve exact script text.
- Target words remain intelligible.
- Panel and page pauses support visual reading.
- Ambience and SFX are light enough for ESL comprehension.
- Generated page audio can be replayed without re-generating.
