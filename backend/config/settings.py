import os
import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'corsheaders',

    'users.apps.UsersConfig',
    'vocabulary',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': env.db(),
}

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.CustomUser'

# CORS — v2 runs on port 5174
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5174',
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5174',
]

# Session cookie hardening. CsrfExemptSessionAuthentication bypasses DRF's CSRF
# check, so the SameSite policy is the cross-site defense — set it explicitly
# rather than relying on Django's implicit default. 'Lax' blocks the cookie on
# cross-site POST/fetch while keeping top-level GET navigation working. Secure
# cookies follow DEBUG (off locally over http, on in production behind TLS).
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'config.authentication.CsrfExemptSessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# =============================================================================
# TIER CONFIG (XP / Level progression)
# =============================================================================
TIER_CONFIG = {
    'BRONZE':   {'min_level': 1,  'max_level': 20, 'xp_per_level': 200, 'color': '#CD7F32'},
    'SILVER':   {'min_level': 21, 'max_level': 40, 'xp_per_level': 300, 'color': '#C0C0C0'},
    'GOLD':     {'min_level': 41, 'max_level': 60, 'xp_per_level': 400, 'color': '#FFD700'},
    'PLATINUM': {'min_level': 61, 'max_level': 80, 'xp_per_level': 500, 'color': '#E5E4E2'},
    'DIAMOND':  {'min_level': 81, 'max_level': 999, 'xp_per_level': 600, 'color': '#B9F2FF'},
}

# =============================================================================
# SUPPORTED LANGUAGES (for Translation model)
# =============================================================================
SUPPORTED_LANGUAGES = [
    ('zh-CN', 'Chinese (Simplified)'),
    ('zh-TW', 'Chinese (Traditional)'),
    ('ja', 'Japanese'),
    ('ko', 'Korean'),
    ('es', 'Spanish'),
    ('vi', 'Vietnamese'),
    ('th', 'Thai'),
    ('ar', 'Arabic'),
    ('pt', 'Portuguese'),
    ('fr', 'French'),
]

# =============================================================================
# LLM API KEYS
# =============================================================================
ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY', default='')
ANTHROPIC_BASE_URL = env('ANTHROPIC_BASE_URL', default='')
GEMINI_API_KEY = env('GEMINI_API_KEY', default='')
GEMINI_BASE_URL = env('GEMINI_BASE_URL', default='')

# Text-to-speech (Gemini native TTS). Kept separate from the text Gemini config
# because TTS needs the native generateContent API with audio modality, which an
# OpenAI-compatible text proxy usually does not serve. Falls back to the main
# Gemini key when its own key is unset. Leave TTS_BASE_URL empty to hit Google
# directly; set it to a proxy that supports the native Gemini TTS endpoint.
GEMINI_TTS_API_KEY = env('GEMINI_TTS_API_KEY', default='')
GEMINI_TTS_BASE_URL = env('GEMINI_TTS_BASE_URL', default='')
GEMINI_TTS_MODEL = env('GEMINI_TTS_MODEL', default='gemini-2.5-pro-preview-tts')

# Image generation API (OpenAI GPT-Image-2)
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
OPENAI_BASE_URL = env('OPENAI_BASE_URL', default='')

# Embedding API (SiliconFlow — Qwen3-Embedding-8B)
QWEN_API_KEY = env('QWEN_API_KEY', default='')
QWEN_BASE_URL = env('QWEN_BASE_URL', default='https://api.siliconflow.cn/v1/embeddings')
QWEN_EMBEDDING_MODEL = env('QWEN_EMBEDDING_MODEL', default='Qwen/Qwen3-Embedding-8B')
QWEN_EMBEDDING_DIMENSIONS = env.int('QWEN_EMBEDDING_DIMENSIONS', default=1024)

# =============================================================================
# GENERATION PIPELINE CONFIG
# =============================================================================
EMBEDDING_SIMILARITY_THRESHOLD = 0.92
GENERATION_WORDS_PER_PACK = 6
GENERATION_DEFAULT_LEXILE = 650
GENERATION_QUESTION_TYPES = [
    'DEFINITION_MC_SINGLE',
    'DEFINITION_TRUE_FALSE',
    'SYNONYM_MC_SINGLE',
    'ANTONYM_MC_SINGLE',
    'CONTEXT_MC_SINGLE',
    'CONTEXT_FILL_IN_BLANK',
    'SPELLING_FILL_IN_BLANK',
    'WORD_FORM_FILL_IN_BLANK',
    'COLLOCATION_MC_SINGLE',
    'CONCEPTUAL_ASSOCIATION_MC_SINGLE',
]

# =============================================================================
# LOGGING
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'vocabulary': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
