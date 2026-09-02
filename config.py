from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env', override=False)


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on', 'si'}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _resolve_path(raw_value: str | None, default: Path) -> str:
    if not raw_value:
        return str(default.resolve())
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return str(candidate.resolve())


def _normalize_base_path(raw_value: str | None) -> str:
    value = (raw_value or '').strip()
    if not value or value == '/':
        return ''
    if not value.startswith('/'):
        value = f'/{value}'
    return value.rstrip('/')


class Config:
    APP_NAME = 'DXT Conta'
    APP_VERSION = '1.1.0-base'
    APP_DESCRIPTION = 'Sistema de gestión contable, tesorería y control operativo'

    ENV = os.getenv('FLASK_ENV', os.getenv('APP_ENV', 'development')).strip().lower()
    DEBUG = _get_bool('FLASK_DEBUG', ENV == 'development')
    TESTING = False

    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
    BASE_PATH = _normalize_base_path(os.getenv('BASE_PATH'))
    APPLICATION_ROOT = '/'

    HOST = os.getenv('FLASK_HOST', '127.0.0.1')
    PORT = _get_int('FLASK_PORT', 5000)
    PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'https' if ENV == 'production' else 'http')
    TRUST_PROXY = _get_bool('TRUST_PROXY', ENV == 'production')

    DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
    DB_PORT = _get_int('DB_PORT', 5432)
    DB_NAME = os.getenv('DB_NAME', 'dxtsys')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
    DB_SCHEMA = os.getenv('DB_SCHEMA', 'contabilidad')

    SESSION_TIMEOUT_SECONDS = _get_int('SESSION_TIMEOUT_SECONDS', _get_int('SESSION_TIMEOUT', 3600))
    SESSION_COOKIE_NAME = os.getenv('SESSION_COOKIE_NAME', 'dxt_conta_session')
    SESSION_COOKIE_SECURE = _get_bool('SESSION_COOKIE_SECURE', ENV == 'production')
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_PATH = '/'
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=SESSION_TIMEOUT_SECONDS)
    SESSION_PERMANENT = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_REFRESH_EACH_REQUEST = False

    MAX_UPLOAD_SIZE_MB = _get_int('MAX_UPLOAD_SIZE_MB', _get_int('MAX_UPLOAD_SIZE', 16))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    STATIC_FOLDER = _resolve_path(os.getenv('STATIC_FOLDER'), BASE_DIR / 'static')
    DXT_CONTA_DATA_DIR = _resolve_path(os.getenv('DXT_CONTA_DATA_DIR'), BASE_DIR.parent / 'dxt-conta-data')
    UPLOAD_FOLDER = _resolve_path(os.getenv('UPLOAD_FOLDER'), Path(DXT_CONTA_DATA_DIR) / 'uploads')
    LOGO_FOLDER = _resolve_path(os.getenv('LOGO_FOLDER'), Path(DXT_CONTA_DATA_DIR) / 'logo')
    LOGIN_LOGO_FILENAME = os.getenv('LOGIN_LOGO_FILENAME', 'dxt_logo.jpg')
    SIDEBAR_LOGO_FILENAME = os.getenv('SIDEBAR_LOGO_FILENAME', LOGIN_LOGO_FILENAME)
    STATIC_CACHE_SECONDS = _get_int('STATIC_CACHE_SECONDS', 2592000)

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_TO_FILE = _get_bool('LOG_TO_FILE', True)
    LOG_DIR = _resolve_path(os.getenv('LOG_DIR'), BASE_DIR / 'logs')
    LOG_FILE = os.getenv('LOG_FILE', './logs/dxt_conta.log')
    LOG_MAX_BYTES = _get_int('LOG_MAX_BYTES', 5242880)
    LOG_BACKUP_COUNT = _get_int('LOG_BACKUP_COUNT', 5)

    ENABLE_HSTS = _get_bool('ENABLE_HSTS', ENV == 'production')
    HSTS_MAX_AGE = _get_int('HSTS_MAX_AGE', 31536000)

    LOGIN_MAX_ATTEMPTS = _get_int('LOGIN_MAX_ATTEMPTS', 5)
    LOGIN_ATTEMPT_WINDOW_SECONDS = _get_int('LOGIN_ATTEMPT_WINDOW_SECONDS', 900)
    LOGIN_LOCKOUT_SECONDS = _get_int('LOGIN_LOCKOUT_SECONDS', 600)

    TURNSTILE_ENABLED = _get_bool('TURNSTILE_ENABLED', True)
    TURNSTILE_MODE = os.getenv('TURNSTILE_MODE', 'placeholder').strip().lower()
    TURNSTILE_SITE_KEY = os.getenv('TURNSTILE_SITE_KEY', '1x00000000000000000000AA')
    TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '1x0000000000000000000000000000000AA')
    TURNSTILE_VERIFY_TIMEOUT_SECONDS = _get_int('TURNSTILE_VERIFY_TIMEOUT_SECONDS', 5)
    TURNSTILE_PLACEHOLDER_TOKEN = os.getenv('TURNSTILE_PLACEHOLDER_TOKEN', 'placeholder-pass')
    TURNSTILE_PLACEHOLDER_LABEL = os.getenv('TURNSTILE_PLACEHOLDER_LABEL', 'No soy un robot (modo temporal)')

    CONTA_ALLOWED_ROLE_IDS = tuple(
        int(item.strip())
        for item in os.getenv('CONTA_ALLOWED_ROLE_IDS', '9,10,11').split(',')
        if item.strip().isdigit()
    )

    TIMEZONE = os.getenv('TIMEZONE', 'America/La_Paz')

    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'X-Permitted-Cross-Domain-Policies': 'none',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    }


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    ENABLE_HSTS = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DB_NAME = os.getenv('DB_NAME_TEST', 'dxtsys_test')


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}


def get_config(config_name: str | None = None):
    selected = (config_name or os.getenv('FLASK_ENV', 'development')).strip().lower()
    return config_by_name.get(selected, DevelopmentConfig)
