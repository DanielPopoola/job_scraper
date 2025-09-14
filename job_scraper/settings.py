import os
from pathlib import Path

import environ

env = environ.Env(
    DEBUG = (bool, False)
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Create log directories
LOGS_DIR = BASE_DIR / 'logs'
LOG_FOLDERS = [
    'linkedin', 
    'indeed', 
    'orchestrator', 
    'pipeline',
]
for folder in LOG_FOLDERS:
    (LOGS_DIR / folder).mkdir(parents=True, exist_ok=True)

environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = [env('ALLOWED_HOSTS')]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'scraper',
    'api',
    'dashboard',
    'rest_framework',
    'django_filters',
    'drf_spectacular',
    'drf_spectacular_sidecar',
]


REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'job_scraper.urls'

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

WSGI_APPLICATION = 'job_scraper.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': env.db()
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'linkedin_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'linkedin/scraper.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 2,
            'formatter': 'verbose',
        },
        'indeed_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'indeed/scraper.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 2,
            'formatter': 'verbose',
        },
        'orchestrator_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'orchestrator/orchestrator.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 2,
            'formatter': 'verbose',
        },
        'pipeline_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'pipeline/pipeline.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 2,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'LinkedInScraper': {
            'handlers': ['linkedin_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'IndeedScraper': {
            'handlers': ['indeed_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'JobScrapingOrchestrator': {
            'handlers': ['orchestrator_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Log all pipeline components to the same file
        'JobProcessingPipeline': {
            'handlers': ['pipeline_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'JobDataCleaner': {
            'handlers': ['pipeline_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'JobDataNormalizer': {
            'handlers': ['pipeline_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'JobDuplicateDetector': {
            'handlers': ['pipeline_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
