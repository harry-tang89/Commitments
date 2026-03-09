import os
import secrets
from datetime import timedelta

# Absolute path to the directory that contains THIS file (the config file).
# Useful for building paths like "sqlite:////.../app.db" in a consistent way.
PROJECT_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))

# Read the runtime environment from common env vars.
# - FLASK_ENV was used a lot historically
# - ENV is another commonly used convention
#
# We normalize the value by stripping whitespace and lowercasing it so that:
#   " Production " -> "production"
APP_ENVIRONMENT = (os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "").strip().lower()

# Convenience flag: treat the app as production only if the environment is exactly "production".
# This is used to choose secure defaults for cookies.
IS_PRODUCTION_ENV = APP_ENVIRONMENT == "production"


def _read_bool_env_var(var_name: str, default: bool) -> bool:
    """
    Read an environment variable and interpret it as a boolean.

    Examples of values treated as True (case-insensitive):
        "1", "true", "yes", "on"

    Anything else (including "0", "false", "no", "off", random text) is treated as False.

    Why this helper exists:
      - Environment variables are always strings.
      - This gives consistent parsing for feature flags like SESSION_COOKIE_SECURE.
    """
    raw_value = os.environ.get(var_name)
    if raw_value is None:
        # If the variable is not set at all, fall back to the provided default.
        return default
    
    normalized_value = raw_value.strip().lower()
    return normalized_value in {"1", "true", "yes", "on"}

class AppConfig:
    """
    Application configuration for a Flask app.

    In Flask, this class is commonly loaded with:
        app.config.from_object(AppConfig)

    Notes:
      - Values can come from environment variables, which is standard for deployments.
      - Cookie flags are set to safer defaults in production.
    """

    # SECRET_KEY is used by Flask to:
    # - sign session cookies
    # - protect against tampering
    #
    # Best practice:
    # - In production, you SHOULD set SECRET_KEY as an environment variable.
    # - Locally/dev, we generate a strong random key automatically.
    #
    # WARNING:
    # - If you do NOT set SECRET_KEY in production and your app restarts,
    #   existing sessions/cookies may become invalid because the key changes.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    # SQLALCHEMY_DATABASE_URI tells Flask-SQLAlchemy how to connect to the database.
    #
    # Priority:
    # 1) DATABASE_URL env var (common on Heroku / Render / many hosts)
    # 2) Fallback to a local SQLite database file app.db inside this project directory
    DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(PROJECT_ROOT_DIR, "app.db")
    )

     # --- Session cookie configuration ---
    #
    # SESSION_COOKIE_SECURE:
    #   - True means the browser will ONLY send the cookie over HTTPS.
    #   - In production, this should almost always be True (assuming HTTPS).
    #   - In local development (http://localhost), it’s often False so cookies work.
    SESSION_COOKIE_SECURE = _read_bool_env_var("SESSION_COOKIE_SECURE", IS_PRODUCTION_ENV)

    # Prevent JavaScript from reading the session cookie (helps mitigate XSS attacks).
    SESSION_COOKIE_HTTPONLY = True
    
    # Controls cross-site cookie sending behavior:
    # - "Lax" is a good default for many apps: blocks most CSRF-ish cross-site requests
    #   while still allowing normal navigation.
    # - Consider "Strict" for higher security or "None" when using cross-site iframes,
    #   but "None" requires Secure=True.
    SESSION_COOKIE_SAMESITE = "Lax"
    
    # --- "Remember me" cookie configuration ---
    #
    # If you use Flask-Login's "remember me" feature, this controls how long the
    # user stays logged in via the remember cookie.
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    
    # Same idea as SESSION_COOKIE_SECURE but for the remember-me cookie.
    REMEMBER_COOKIE_SECURE = _read_bool_env_var("REMEMBER_COOKIE_SECURE", IS_PRODUCTION_ENV)
    
    # Prevent JavaScript from reading the remember cookie.
    REMEMBER_COOKIE_HTTPONLY = True
    
    # Same cross-site policy for the remember cookie.
    REMEMBER_COOKIE_SAMESITE = "Lax"

    MAIL_HOST = os.environ.get("MAIL_HOST", "").strip()
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_USE_TLS = _read_bool_env_var("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _read_bool_env_var("MAIL_USE_SSL", False)
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "").strip()
    MAIL_ENABLED = bool(MAIL_HOST and MAIL_DEFAULT_SENDER)
    REGISTRATION_CODE_TTL_SECONDS = int(os.environ.get("REGISTRATION_CODE_TTL_SECONDS", "600"))
    DEV_REGISTRATION_CODE_BYPASS = _read_bool_env_var("DEV_REGISTRATION_CODE_BYPASS", not IS_PRODUCTION_ENV)
    DEV_REGISTRATION_CODE = os.environ.get("DEV_REGISTRATION_CODE", "000000").strip()

    # Flask-SQLAlchemy expects this exact config key name, so we map our readable name
    # back to the expected one.
    SQLALCHEMY_DATABASE_URI = DATABASE_URI
