# Vocab App v2

A K-8 vocabulary learning platform with AI-generated instructional content, adaptive spaced repetition, and role-based access for admins, teachers, and students.

## Features

**AI Content Generation Pipeline**
- Automated word lookup, deduplication, and translation (10+ languages)
- Question generation (15 per word across 28 question types)
- Thematic pack creation with primer cards
- Graphic novel scripts (Gemini 6-call planning pipeline) and cinematic images (GPT-Image-2) — 3 candidate novels per pack, admin picks one to publish
- Per-step resume on failure, stale job detection

**Instructional Flow**
- Primer cards with images and syllable breakdowns
- Graphic novel reader (16:9 landscape pages with vocabulary overlay) with optional read-along audio playback (per-page Listen/Pause + Auto-read toggle)
- Read-along audiobook: per-page narrated audio generated on demand via Gemini TTS (admin-triggered); served to students as a compressed MP3
- Cloze quiz (fill-in-the-blank) for comprehension check
- Pack completion tracking before words enter practice

**Spaced Repetition Practice**
- 7 mastery levels with response-quality-aware scheduling
- Adaptive learning speed (EMA-based)
- XP and tier progression (Bronze → Diamond)
- Practice streaks with freeze rewards

**Teacher Tools**
- Student roster with 3-day activity snapshots
- Bulk student creation (up to 10)
- Word set management and assignment
- Student groups and progress tracking

**Admin Tools**
- Full generation wizard (pipeline, questions-only, instructional-only)
- Generation status polling with per-page image progress
- Graphic novel candidate review: 3 candidates per pack, select one to publish (gates student visibility + cloze)
- Per-page graphic novel image editing with original/edited variant selection
- Resume failed pipelines

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.2, Django REST Framework 3.16, Python |
| Frontend | React 19, Vite 7, React Router 7 |
| Database | MySQL |
| AI/LLM | Google Gemini (text + script), OpenAI GPT-Image-2 (images), Qwen3 Embeddings (dedup) |
| Auth | Session-based with CSRF |
| Testing | pytest, pytest-django, factory-boy |

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- MySQL 8.0+

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your database and API credentials

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8001
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:5174` and proxies API requests to `localhost:8001`.

### Running Tests

```bash
cd backend
pytest
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | MySQL connection string |
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Debug mode (True/False) |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `GEMINI_API_KEY` | Gemini API key (text generation; also used as auth when routing through `GEMINI_BASE_URL`) |
| `GEMINI_BASE_URL` | Optional — OpenAI-compatible proxy URL for Gemini (e.g., `https://api.b.ai/v1`). When set, `call_gemini` uses the OpenAI SDK against this base URL. |
| `GEMINI_TTS_API_KEY` | Optional — API key for read-along audiobook TTS. Falls back to `GEMINI_API_KEY` if unset. |
| `GEMINI_TTS_BASE_URL` | Optional — proxy that serves the **native** Gemini TTS (`generateContent` audio) endpoint. Leave empty to call Google directly. Kept separate from `GEMINI_BASE_URL` because an OpenAI-compatible text proxy usually does not serve audio. |
| `GEMINI_TTS_MODEL` | Optional — TTS model name (default `gemini-2.5-pro-preview-tts`). |
| `ANTHROPIC_API_KEY` | Anthropic API key (reserved for fallback / future Claude steps) |
| `ANTHROPIC_BASE_URL` | Optional proxy URL for Anthropic API |
| `OPENAI_API_KEY` | OpenAI API key (image generation) |
| `OPENAI_BASE_URL` | Optional proxy URL for OpenAI API |
| `QWEN_API_KEY` | SiliconFlow API key (Qwen3 embeddings) |

## Project Documentation

- [Architecture & API Reference](docs/PROJECT_CONTEXT.md)
- [Changelog](docs/CHANGELOG.md)
- [Beta Improvements Checklist](BETA_IMPROVEMENTS.md)

## Production Deployment

The app is deployed on a bare Ubuntu 24.04 server (nginx + gunicorn + MySQL 8).

| Component | Detail |
|-----------|--------|
| URL | http://106.52.164.47 |
| Server | Tencent Cloud, 2 vCPU / 3.6 GB RAM |
| Web server | nginx 1.24 — serves React `dist/`, proxies `/api` + `/admin`, serves `/media` + `/static` |
| App server | gunicorn 3 workers, systemd unit `vocab.service`, socket at `/run/vocab/vocab.sock` |
| Database | MySQL 8, database `vocab_app` |

**Redeploy after code change (on server):**
```bash
cd ~/vocab_app_v2/backend && source venv/bin/activate
python manage.py migrate                    # if migrations changed
python manage.py collectstatic --noinput    # if static files changed
sudo systemctl restart vocab
```

Frontend change: `npm run build` locally, then scp the new `frontend/dist/` to the server.

**Next steps:** add a domain name and HTTPS via Certbot, then configure the LLM sites + per-step models in the admin LLM Config UI at `/teacher/llm-config` (three editable config sets; pick which one is active).

## License

Private — all rights reserved.
