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
    'DIAMOND':  {'min_level': 81, 'max_level': 100, 'xp_per_level': 600, 'color': '#B9F2FF'},
    'CHAMPION': {'min_level': 101, 'max_level': 999, 'xp_per_level': 700, 'color': '#D1B0F7'},
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

# Qwen 2.5 Embedding API
QWEN_API_KEY = env('QWEN_API_KEY', default='')
QWEN_BASE_URL = env('QWEN_BASE_URL', default='')

# =============================================================================
# GENERATION PIPELINE CONFIG
# =============================================================================
EMBEDDING_SIMILARITY_THRESHOLD = 0.92
GENERATION_WORDS_PER_PACK = 5
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
