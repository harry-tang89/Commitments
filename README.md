# Commitments

Commitments is a Flask web application for creating, tracking, and sharing commitments. It supports account registration, password recovery, guest-mode quick entry, collaboration, and basic PWA features.

## Documentation

- Technical documentation: [docs/technical-documentation.md](docs/technical-documentation.md)
- User documentation: [docs/user-documentation.md](docs/user-documentation.md)

## Local Setup

1. Create and activate a virtual environment.

   macOS / Linux:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   Windows PowerShell:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install dependencies.

   ```bash
   python -m pip install --upgrade pip
   python -m pip install -r app/requirements.txt
   ```

3. Set the Flask entry point.

   macOS / Linux:
   ```bash
   export FLASK_APP=run.py
   ```

   Windows PowerShell:
   ```powershell
   $env:FLASK_APP = "run.py"
   ```

4. Apply database migrations.

   ```bash
   python -m flask db upgrade
   ```

5. Start the development server.

   ```bash
   python -m flask run
   ```

6. Open `http://127.0.0.1:5000`.

## Useful Commands

Run tests:

```bash
pytest
```

Create a new migration after schema changes:

```bash
python -m flask db migrate -m "describe change"
```

Apply the latest migration:

```bash
python -m flask db upgrade
```

## Environment Notes

- If `DATABASE_URL` is not set, the app uses a local SQLite database at `app/app.db`.
- Email verification requires SMTP settings such as `MAIL_HOST` and `MAIL_DEFAULT_SENDER`.
- In local development, registration code bypass is enabled by default unless the app is running in production mode.
