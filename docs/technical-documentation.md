# Technical Documentation

## Overview

Commitments is a Flask web application for creating, tracking, and sharing personal commitments. It supports:

- Account registration with email verification
- Login and password recovery
- Personal and shared commitments
- Guest-mode commitment creation on the landing page
- Progressive Web App support through a manifest and service worker

## Technology Stack

- Backend: Flask
- Forms and CSRF: Flask-WTF / WTForms
- Database ORM: Flask-SQLAlchemy with SQLAlchemy 2 style models
- Database migrations: Flask-Migrate / Alembic
- Authentication: Flask-Login
- Testing: Pytest
- Frontend: Jinja templates, vanilla JavaScript, Bulma CSS, custom CSS

## Project Structure

```text
Commitments/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── forms.py
│   ├── models.py
│   ├── routes.py
│   ├── requirements.txt
│   ├── static/
│   │   ├── manifest.webmanifest
│   │   ├── sw.js
│   │   ├── styles/main.css
│   │   └── icons/
│   └── templates/
├── migrations/
├── tests/
├── run.py
└── README.md
```

## Application Architecture

### Initialization

`app/__init__.py` creates the Flask application and initializes:

- `SQLAlchemy` for persistence
- `Migrate` for schema migrations
- `LoginManager` for session-based authentication

The application uses a simple single-app layout instead of the blueprint pattern.

### Configuration

`app/config.py` contains environment-driven runtime configuration. Important settings:

- `SECRET_KEY`: Flask session signing key
- `DATABASE_URL`: database connection string
- `SESSION_COOKIE_SECURE`, `REMEMBER_COOKIE_SECURE`: security flags that default to safer production behavior
- `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`: SMTP configuration
- `REGISTRATION_CODE_TTL_SECONDS`: registration code expiry window
- `DEV_REGISTRATION_CODE_BYPASS` and `DEV_REGISTRATION_CODE`: local-development shortcut for registration

If `DATABASE_URL` is not set, the app falls back to SQLite at `app/app.db`.

## Data Model

### User

Defined in `app/models.py`.

Key fields:

- `id`
- `username` (unique)
- `email` (unique)
- `birth_day`
- `birth_month`
- `birth_year`
- `password_hash`

Key behavior:

- `set_password(password)`: stores a hashed password
- `check_password(password)`: verifies a password against the hash

### Commitment

Defined in `app/models.py`.

Key fields:

- `id`
- `user_id`: owner reference
- `category`: optional, one of `general`, `study`, `health`, `travel`
- `title`
- `description`
- `deadline_date`
- `status`
- `created_at`

### Commitment Collaborators

The many-to-many relationship is stored in the `commitment_collaborator` association table.

This enables:

- One owner per commitment
- Many collaborators per commitment
- Shared visibility and edit access for collaborators

## Authentication and Recovery Flows

### Registration

The registration workflow is split into two parts:

1. `POST /register/send-code` validates the email and sends a 6-digit verification code.
2. `GET/POST /register` validates the code, creates the user, and logs them in.

Verification state is stored in the Flask session rather than the database.

### Login

`GET/POST /login` accepts a contact identifier and password.

Current implementation details:

- The UI says users can enter a mobile number or email address.
- Validation accepts email and phone-number-like formats.
- The lookup currently checks `User.email` only.

This means email login works, but phone login is not backed by a dedicated database field yet.

### Password Recovery

`GET/POST /forgot-password` is a staged flow:

1. Contact entry
2. Date-of-birth verification
3. Password reset
4. Success state

The implementation avoids disclosing whether an account exists during the first step.

## Commitments Functionality

### HTML Pages

- `/` and `/index`: landing page with quick-create UI
- `/settings`: settings page; for signed-in users preferences are stored on the `User` record and reused across devices
- `/commitments`: full commitments page for authenticated users
- `/commitments/<id>/edit`: edit a commitment
- `/commitments/<id>/members`: view members for a commitment

### JSON Endpoints

- `GET /api/settings`: fetch the signed-in user's saved settings
- `PATCH /api/settings`: update the signed-in user's saved settings
- `GET /api/commitments/events`: stream real-time commitment change notifications for signed-in users via SSE
- `POST /api/commitments/quick`: quick-create commitment
- `PATCH /api/commitments/<id>/quick`: quick-update commitment
- `DELETE /api/commitments/<id>/quick`: owner-only delete
- `POST /api/commitments/<id>/complete`: mark complete
- `POST /api/commitments/<id>/recover`: mark active again
- `POST /api/commitments/<id>/leave`: collaborator leaves a shared commitment
- `GET /api/commitments/<id>/members`: list members
- `POST /api/commitments/<id>/members`: add a member
- `POST /api/commitments/sync-local`: sync guest commitments into the database after login

### Permissions

Permission rules are implemented in helper functions in `app/routes.py`.

- Owners can edit and delete their commitments.
- Collaborators can view and edit shared commitments.
- Collaborators cannot delete commitments they do not own.
- Owners cannot leave their own commitments.

## Guest Mode and PWA Behavior

On the landing page, unauthenticated users can create commitments locally in browser storage.

Behavior:

- Guest commitments are not written to the server
- The quick-create endpoint returns `401` with a message instructing the frontend to keep data in browser cache only
- After login, the app can sync local commitments into the database

PWA-related files:

- `app/static/manifest.webmanifest`
- `app/static/sw.js`

## Validation Rules

Important validation implemented in `app/forms.py` and `app/routes.py`:

- Titles are required and limited to 140 characters
- Deadline dates cannot be in the past
- Categories are restricted to the predefined list
- Registration requires email verification
- Password reset requires a matching stored date of birth

## Database and Migrations

The project uses Alembic migrations through Flask-Migrate.

Common commands:

```bash
python -m flask db upgrade
python -m flask db migrate -m "describe change"
python -m flask db downgrade
```

Migration files are stored in `migrations/versions/`.

## Local Development Setup

### Prerequisites

- Python 3.11+ is a reasonable target for this codebase
- `pip`
- A virtual environment tool

### Install and Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r app/requirements.txt
export FLASK_APP=run.py
python -m flask db upgrade
python -m flask run
```

Open `http://127.0.0.1:5000`.

### Optional Mail Configuration

For real registration emails, set:

```bash
export MAIL_HOST=...
export MAIL_PORT=587
export MAIL_USERNAME=...
export MAIL_PASSWORD=...
export MAIL_DEFAULT_SENDER=...
```

For local development without SMTP, the registration bypass is enabled by default unless the app is in production mode.

## Testing

Tests live in `tests/` and use a dedicated SQLite database file.

Run:

```bash
pytest
```

Covered areas include:

- Home page rendering
- Registration flow
- Password hashing
- Login behavior
- Forgot-password flow
- Commitment creation and selected API routes

## Known Implementation Notes

- The app uses an app-global Flask instance rather than an application factory.
- Login and recovery forms describe phone support, but user lookup currently uses email only.
- The current application model, forms, and tests use `deadline_date`.
- `toggle_commitment_status` uses `"complete"` while the quick API uses `"completed"`, so status naming is not fully consistent.

These are good candidates for future cleanup if the project is still evolving.
