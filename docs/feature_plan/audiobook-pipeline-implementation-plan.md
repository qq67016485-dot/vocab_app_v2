# Audiobook Pipeline — Implementation Plan (Phase 1)

> **Status: IMPLEMENTED 2026-06-07** — phase 1 is built and verified working (novel 50, 6/6 pages, via the Vector TTS proxy). The TTS endpoint uses dedicated `GEMINI_TTS_*` settings (the plan's `settings.GEMINI_API_KEY` assumption was wrong — that key is empty in this deployment). See `docs/PROJECT_CONTEXT.md` → "Read-Along Audiobook" and `CLAUDE.md` for the as-built description; this file is kept as the design record.

Goal: generate a read-along audio track for a completed graphic novel, **one stitched audio file per page**, on demand (admin-triggered per novel), using `gemini-2.5-pro-preview-tts`. Each speech event (one narration box or one dialogue line) is rendered as its own single-voice TTS call, then concatenated into a per-page file with pauses. No per-event timing metadata in this phase.

This phase delivers backend generation + storage + admin trigger/poll + serving the URL to students. Frontend playback UI in the reader is a thin follow-on.

## Decisions locked (from user)
- Trigger: **separate on-demand job**, not a 9th pipeline step. Runs on a completed novel.
- Multi-speaker: **per-event single-voice calls** (ignore Gemini's 2-speaker mode entirely — simpler, max voice consistency).
- Output: **one stitched audio file per page**, no timing JSON yet.

## Verified facts (checked against live code, not assumed)
- Spoken text lives verbatim in `GraphicNovelPage.panel_descriptions` — a list of `{panel_number, narration, dialogue:[{speaker,text}], vocab_words, scene_description, alt_text}`. This matches the rendered images (confirmed by image-vs-script audit). **No OCR needed.**
- Cast is Leo, Amara, Mei, Hugo + `narrator` + story-specific speakers. `novel.metadata['age_band']` is `'9yo'`/`'12yo'`.
- `google-genai` SDK (already installed) exposes `types.SpeechConfig / VoiceConfig / PrebuiltVoiceConfig` and `GenerateContentConfig(response_modalities, speech_config)`. TTS returns **raw PCM (24kHz, 16-bit, mono)** in `response.candidates[0].content.parts[0].inline_data.data`.
- **No pydub / ffmpeg on the box.** Stitching uses the stdlib `wave` module: all clips share one PCM format, so we concat frames + insert silence and emit a single `.wav`. Zero native deps.
- The project's `call_gemini` routes through an OpenAI-compatible proxy when `GEMINI_BASE_URL` is set; that proxy does **not** do audio. TTS must use the **native `genai.Client`** path directly (like `_call_gemini_native`), always with `settings.GEMINI_API_KEY`.
- Async pattern to mirror: `_run_page_image_edit` / `EditGraphicNovelPageImageView` (validate sync → set RUNNING → daemon thread → poll status endpoint). DB hygiene via `_close_old_connections_if_safe`.

## Voice mapping (prebuilt Gemini voices)
Stable per-character assignment so a voice never drifts between pages:
- Narrator: `Sulafat` (warm) for 9yo / `Charon` (informative) for 12yo
- Leo: `Puck` (upbeat)
- Amara: `Kore` (firm/measured)
- Mei: `Fenrir` (excitable)
- Hugo: `Aoede` (breezy-gentle) — candidate; finalize during testing
- Story-specific speakers: deterministic fallback by hashing the speaker name into a small "supporting voices" pool (e.g. Zephyr, Leda, Orus), so the same character keeps one voice within a novel.
Voice table lives in a new `constants.py` block; tone/age is steered via a natural-language style prefix prepended to the line text (the bible's AGE_PRESENTATION rules), not by switching voices.

## New model: `GraphicNovelPageAudio`
One row per page (1:1 with `GraphicNovelPage`), kept separate from the page so audio is fully optional/regenerable and never risks the image rows.
```
page          OneToOneField(GraphicNovelPage, related_name='audio', on_delete=CASCADE)
audio         FileField(upload_to='graphic_novel_audio/', blank=True)   # stitched .wav
duration_ms   IntegerField(default=0)
voice_manifest JSONField(default=dict)  # {events:[{speaker,voice,source,chars}], age_band} for debugging/regeneration
status        CharField(choices=PENDING/RUNNING/COMPLETED/FAILED, default=PENDING)
attempts      IntegerField(default=0)
error         TextField(blank=True, default='')
started_at / completed_at  DateTimeField(null=True)
created_at / updated_at
```
Migration `0032_graphic_novel_page_audio`. (WAV is large but fine for phase 1; an MP3/Opus pass can come later once ffmpeg is available — noted, not blocking.)

## New service package: `services/audiobook/`
Keep files small per the repo's house style:
- `constants.py` — voice map, age style prefixes, pause durations (from the bible: 0.2-0.4s inter-dialogue, 0.4-0.7s post-narration, page-end longer; 9yo uses longer end), PCM format constants (24000 Hz, 16-bit, mono).
- `events.py` — `build_page_events(page)`: walk `panel_descriptions` in panel order → ordered list of speech events `{speaker, speaker_type, text, source, vocab_words, pause_after_ms}`. Pure function, unit-testable, no I/O.
- `voices.py` — `voice_for(speaker, age_band, novel)`: resolve a speaker to a prebuilt voice name (hero map → supporting pool fallback).
- `tts_client.py` — `synthesize(text, voice_name, style_prefix) -> pcm_bytes`: native `genai.Client` TTS call; retries once; returns raw PCM. Isolated so it's the only Gemini-audio touch point.
- `stitch.py` — `stitch_pcm(clips, pauses, fmt) -> wav_bytes` and `silence(ms)`: stdlib `wave`, concatenate + insert silence, return WAV bytes + total duration_ms.
- `generator.py` — `generate_page_audio(page)`: events → per-event synth → stitch → save file + manifest + duration on the `GraphicNovelPageAudio` row, set terminal status. `generate_novel_audio(novel_id)`: loop pages (skip review page unless trivially supported), continue-on-failure per page like the image step, return summary.

## Views + URLs (mirror the image-edit async pattern)
In `generation_views.py`:
- `_run_novel_audio(novel_id)` — daemon-thread worker; `_close_old_connections_if_safe()` guard; calls `generate_novel_audio`.
- `GenerateGraphicNovelAudioView` — `POST /api/graphic-novels/{novel_id}/generate-audio/` (admin). Validates the novel has pages with completed images, refuses if audio already RUNNING (409), creates/resets `PENDING` audio rows, spawns the thread, returns **202**.
- `GraphicNovelAudioStatusView` — `GET /api/graphic-novels/{novel_id}/audio-status/` (admin). Returns per-page `{page_number, status, audio_url, duration_ms, error}` for polling.
- Optional per-page regenerate `POST /api/graphic-novel-pages/{page_id}/regenerate-audio/` (admin) reusing the same worker for one page.
- Register routes in `urls.py` next to the existing graphic-novel-page routes.

## Student serving
In `instructional_service.py`, add `'audio_url'` to each entry in `pages_data` (`page.audio.audio.url` if a COMPLETED audio row exists else `''`). Backward compatible — empty string when no audio yet.

## Admin UI (thin)
In `GraphicNovelPageEditor.jsx` (already the per-page admin surface): a "Generate audio" / "Regenerate audio" button per novel + per page, an `<audio controls>` element when `audio_url` is present, and a `pollUntilDone`-style poller against `audio-status/` (the file already has a shared poll helper from the redraw work). No new page component needed.

## Testing
- Unit: `build_page_events` ordering + pause assignment; `voice_for` determinism + hero/supporting fallback; `stitch_pcm` (silence length math, header correctness via `wave` round-trip).
- Mock the Gemini TTS client (`tts_client.synthesize`) so generator/view tests run offline — return short fixed PCM. Assert: row goes RUNNING→COMPLETED, file saved, duration>0, continue-on-failure marks one page FAILED without aborting siblings, 409 when already running, 202 on trigger.
- One **manual, real-key** smoke test (documented, not in CI) to confirm the native TTS call + voices actually sound right and PCM assumptions (24kHz/16-bit/mono) hold — this is the one assumption I could not verify without calling the API.

## Risks / open items
- **PCM format assumption**: 24kHz/16-bit/mono is the documented Gemini TTS output; confirmed by SDK types but not by a live call here. `tts_client` will read the actual `inline_data.mime_type` (e.g. `audio/L16;rate=24000`) and parse rate from it rather than hardcoding, so a mismatch degrades gracefully.
- **WAV size**: phase-1 acceptable; revisit compression when ffmpeg/pydub is available on the server.
- **Cost/latency**: a 6-page novel is ~15-30 TTS calls; the daemon-thread + poll pattern keeps the worker free, same as image edit.
- Voice picks (esp. Hugo) are first-draft; finalize in the manual smoke test.

## Out of scope (phase 1)
Per-event timing metadata / panel highlight sync, 2-speaker batching, MP3/Opus encoding, auto-advance reader, ambience/SFX layering (the bible's richer production targets are deferred).

## Build order
1. Model + migration (`GraphicNovelPageAudio`, `0032`).
2. `services/audiobook/` (constants, events, voices, stitch — all unit-tested offline first; tts_client last).
3. `generator.py` wiring.
4. Views + URLs + status polling.
5. `instructional_service.py` `audio_url`.
6. Admin UI button + `<audio>` + poller.
7. Tests green; one manual real-key smoke test.
8. Update CLAUDE.md, PROJECT_CONTEXT, CHANGELOG, and the audiobook bible's "from plan to built" note; add a memory entry.
