# Vocab App v2

A K-8 vocabulary learning platform with AI-generated instructional content, adaptive spaced repetition, and role-based access for admins, teachers, and students.

## Features

**AI Content Generation Pipeline**
- Automated word lookup, deduplication, and translation (10+ languages)
- Question generation (15 per word across 28 question types)
- Thematic pack creation with primer cards
- Graphic novel scripts (Gemini 6-call planning pipeline) and cinematic images (GPT-Image-2)
- Per-step resume on failure, stale job detection

**Instructional Flow**
- Primer cards with images and syllable breakdowns
- Graphic novel reader (16:9 landscape pages with vocabulary overlay)
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
| `ANTHROPIC_API_KEY` | Anthropic API key (reserved for fallback / future Claude steps) |
| `ANTHROPIC_BASE_URL` | Optional proxy URL for Anthropic API |
| `OPENAI_API_KEY` | OpenAI API key (image generation) |
| `OPENAI_BASE_URL` | Optional proxy URL for OpenAI API |
| `QWEN_API_KEY` | SiliconFlow API key (Qwen3 embeddings) |

## Project Documentation

- [Architecture & API Reference](docs/PROJECT_CONTEXT.md)
- [Changelog](docs/CHANGELOG.md)
- [Beta Improvements Checklist](BETA_IMPROVEMENTS.md)

## License

Private — all rights reserved.
