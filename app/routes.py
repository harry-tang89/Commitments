from flask import render_template, redirect, url_for, flash, request, abort, jsonify, send_from_directory, session
from urllib.parse import urlsplit
from datetime import datetime, time, timezone, date
from email.message import EmailMessage
import hashlib
import re
import secrets
import smtplib
from app import app
from app.forms import (
    RegistrationForm,
    LoginForm,
    ForgotPasswordForm,
    CommitmentForm,
    EmptyForm,
)
from flask_login import current_user, login_user, logout_user, login_required
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import db
from app.models import User, Commitment, commitment_collaborator


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_REGEX = re.compile(r"^\+?[0-9][0-9\-\s]{6,19}$")
CATEGORY_CHOICES = [
    ("general", "General"),
    ("study", "Study"),
    ("health", "Health"),
    ("travel", "Travel"),
]
CATEGORY_VALUES = {value for value, _label in CATEGORY_CHOICES}
PASSWORD_MIN_LENGTH = 8
GENERIC_RECOVERY_FAILURE = "We could not verify those details."
REGISTRATION_SESSION_KEY = "registration_email_verification"


def _normalize_datetime(dt: datetime) -> datetime:
    """
    Ensure a datetime is timezone-aware and represented in UTC.

    - If dt is naive (no tzinfo), we assume it is already UTC.
      (Alternative: treat naive as local time, but that requires a chosen timezone.)
    - If dt is aware, convert it to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _commitment_progress_percent(commitment: Commitment, now_utc: datetime) -> int:
    """
    Compute progress (%) from commitment.created_at to the end of commitment.deadline_date (UTC).

    Interpretation:
    - Progress is 0% at created_at
    - Progress is 100% at deadline_date 23:59:59.999999 UTC (end of that day)

    Edge cases handled:
    - If created_at is missing => 0%
    - If deadline is before/at created time => return 100% only if now >= deadline, else 0%
    """
    if commitment.created_at is None:
        return 0
    created_at_utc = _normalize_datetime(commitment.created_at)
    # Use "end of deadline day" as the deadline moment.
    deadline_utc = datetime.combine(
        commitment.deadline_date,
        time.max,
        tzinfo=timezone.utc,
    )
    total_seconds = (deadline_utc - created_at_utc).total_seconds()
    if total_seconds <= 0:
        return 100 if now_utc >= deadline_utc else 0

    elapsed_seconds = (now_utc - created_at_utc).total_seconds()
    progress_percent = int(round((elapsed_seconds / total_seconds) * 100))
    # Clamp to [0, 100]
    return max(0, min(100, progress_percent))


def _is_owner_or_collaborator(commitment: Commitment, user_id: int) -> bool:
    """
    True if the user is either:
    - the owner of the commitment, or
    - listed as a collaborator in the many-to-many relationship.
    """
    if commitment.user_id == user_id:
        return True
    return any(member.id == user_id for member in commitment.collaborators)


def _can_edit_commitment(commitment: Commitment) -> bool:
    """
    Editing rules: owner OR collaborator may edit.
    Uses Flask-Login's current_user.
    """
    return _is_owner_or_collaborator(commitment, current_user.id)


def _serialize_commitment_for_home(commitment: Commitment) -> dict:
    """
    Convert a Commitment model into a JSON-friendly dict for the home page UI.

    Notes:
    - We normalize category strings to lowercase.
    - `can_edit` depends on current_user permissions.
    - `can_delete` is stricter: owner only.
    """
    stored_category = (commitment.category or "").strip().lower()
    return {
        "id": commitment.id,
        "category": stored_category or "",
        "title": commitment.title,
        "description": commitment.description or "",
        "deadline_date": commitment.deadline_date.isoformat(),
        "created_at": commitment.created_at.isoformat() if commitment.created_at else None,
        "status": (commitment.status or "active").strip().lower(),
        "member_count": 1 + len(commitment.collaborators),
        "can_edit": _can_edit_commitment(commitment),
        "can_delete": commitment.user_id == current_user.id,
    }


def _normalize_contact(raw_contact: str) -> str:
    """
    Normalize a login/recovery identifier that may be either:
      - an email address (we lowercase it)
      - a phone number (we keep digits/punctuation as-is after strip)

    Why:
    - Emails are case-insensitive in practice -> lowercasing avoids duplicates/mismatches.
    - Phone numbers often need more advanced normalization (E.164), but this code does not do that.
    """
    contact = (raw_contact or "").strip()
    if "@" in contact:
        return contact.lower()
    return contact


def _is_valid_contact(contact: str) -> bool:
    """
    Validate identifier format against configured regex rules.

    Returns True if:
      - identifier matches EMAIL_REGEX, or
      - identifier matches MOBILE_REGEX

    Note:
    - This only checks *format*, not whether the identifier exists in the database.
    """
    return bool(EMAIL_REGEX.fullmatch(contact) or MOBILE_REGEX.fullmatch(contact))


def _find_user_by_contact_identifier(raw_contact: str) -> User | None:
    """
    Find a User by the contact identifier.

    Current behavior:
    - Normalizes identifier
    - Queries only User.email

    Important:
    - Even though validation allows phone numbers, this function does NOT look up a phone column.
      If you truly want phone support, you need a User.mobile field and query it too.
    """
    contact = _normalize_contact(raw_contact)
    if not contact:
        return None
    
    # Email-only lookup (phone numbers will never match unless you store them in User.email).
    return db.session.scalar(sa.select(User).where(User.email == contact))


def _build_registration_code_hash(email: str, code: str) -> str:
    payload = f"{app.config['SECRET_KEY']}:{email}:{code}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clear_registration_verification() -> None:
    session.pop(REGISTRATION_SESSION_KEY, None)


def _send_email_message(recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = app.config["MAIL_DEFAULT_SENDER"]
    message["To"] = recipient
    message.set_content(body)

    if app.config["MAIL_USE_SSL"]:
        with smtplib.SMTP_SSL(app.config["MAIL_HOST"], app.config["MAIL_PORT"]) as smtp:
            if app.config["MAIL_USERNAME"]:
                smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            smtp.send_message(message)
        return

    with smtplib.SMTP(app.config["MAIL_HOST"], app.config["MAIL_PORT"]) as smtp:
        if app.config["MAIL_USE_TLS"]:
            smtp.starttls()
        if app.config["MAIL_USERNAME"]:
            smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        smtp.send_message(message)


def _send_registration_verification_email(recipient: str, code: str) -> None:
    ttl_minutes = max(1, int(app.config["REGISTRATION_CODE_TTL_SECONDS"]) // 60)
    body = (
        "Your Commitments registration verification code is "
        f"{code}.\n\nThis code expires in {ttl_minutes} minutes."
    )
    _send_email_message(recipient, "Your Commitments verification code", body)


def _issue_registration_code(email: str) -> None:
    normalized_email = email.strip().lower()
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = int(datetime.now(timezone.utc).timestamp()) + int(
        app.config["REGISTRATION_CODE_TTL_SECONDS"]
    )
    session[REGISTRATION_SESSION_KEY] = {
        "email": normalized_email,
        "code_hash": _build_registration_code_hash(normalized_email, code),
        "expires_at": expires_at,
        "verified": False,
    }
    _send_registration_verification_email(normalized_email, code)


def _validate_registration_code(email: str, code: str) -> tuple[bool, str | None]:
    verification_state = session.get(REGISTRATION_SESSION_KEY) or {}
    normalized_email = email.strip().lower()
    normalized_code = (code or "").strip()

    if (
        app.config["DEV_REGISTRATION_CODE_BYPASS"]
        and normalized_code
        and normalized_code == app.config["DEV_REGISTRATION_CODE"]
    ):
        return True, None

    if verification_state.get("email") != normalized_email:
        return False, "Please request a new email verification code."
    if int(verification_state.get("expires_at", 0)) < int(datetime.now(timezone.utc).timestamp()):
        _clear_registration_verification()
        return False, "Your email verification code has expired. Request a new one."
    if verification_state.get("code_hash") != _build_registration_code_hash(normalized_email, normalized_code):
        return False, "Email verification code is incorrect."

    verification_state["verified"] = True
    session[REGISTRATION_SESSION_KEY] = verification_state
    return True, None


def _generate_unique_username(base_value: str) -> str:
    """
    Generate a username that is not already taken.

    Strategy:
    - Start with `seed` (or "user" if empty)
    - If taken, append a numeric suffix: seed2, seed3, seed4, ...

    Notes:
    - This performs one DB query per attempt.
    - For a high-traffic system you'd want a different strategy (or a UNIQUE constraint + retry).
    """
    base_username = (base_value or "").strip() or "user"

    candidate_username = base_username
    suffix = 1
    
    # Loop until we find a username that does not exist.
    while db.session.scalar(sa.select(User.id).where(User.username == candidate_username)) is not None:
        suffix += 1
        candidate_username = f"{base_username}{suffix}"
    return candidate_username


def _normalize_category(raw_category: str | None) -> str | None:
    """
    Normalize category input.

    Returns:
      - normalized category string in lowercase if valid
      - None if empty or invalid

    CATEGORY_VALUES is the set of allowed categories (e.g. {"general","study","health","travel"}).
    """
    category = (raw_category or "").strip().lower()
    if not category:
        return None
    if category not in CATEGORY_VALUES:
        return None
    return category


def _parse_commitment_payload(data: dict) -> tuple[dict | None, tuple[str, int] | None]:
    """
    Parse and validate the JSON payload for the "quick" commitment endpoints.

    Expected keys in `data`:
      - title (required, <= 140 chars)
      - deadline_date (required, ISO YYYY-MM-DD)
      - description (optional)
      - category (optional but if present must be allowed)

    Returns:
      - (payload_dict, None) on success
      - (None, (error_message, http_status_code)) on failure
    """
    category = _normalize_category(data.get("category"))
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    deadline_date_raw = (data.get("deadline_date") or "").strip()
    # deadline_date_raw is untrusted: it comes from client JSON.

    # --- validation rules ---
    if not title:
        return None, ("Title is required.", 400)
    if len(title) > 140:
        return None, ("Title must be 140 characters or fewer.", 400)
    if not deadline_date_raw:
        return None, ("Deadline date is required.", 400)

    # Parse the date string into a Python `date` object
    try:
        deadline_date_value = date.fromisoformat(deadline_date_raw)
    except ValueError:
        return None, ("Deadline date must be in YYYY-MM-DD format.", 400)
    
    # Prevent creating commitments that are already in the past
    if deadline_date_value < date.today():
        return None, ("Deadline date cannot be earlier than today.", 400)

    # Normalized payload used by the route handlers
    return {
        "category": category,
        "title": title,
        "description": description or None,
        "deadline_date": deadline_date_value,
    }, None


def _find_accessible_commitment(commitment_id: int, user_id: int) -> Commitment | None:
    """
    Fetch a commitment only if the user has access to it:
      - user is the owner (Commitment.user_id), OR
      - user is in the collaborators relationship
    """
    return db.session.scalar(
        sa.select(Commitment).where(
            Commitment.id == commitment_id,
            sa.or_(
                Commitment.user_id == user_id,
                Commitment.collaborators.any(User.id == user_id),
            ),
        )
    )


def _birth_fields_present(form: ForgotPasswordForm) -> bool:
    """
    Return True if the user filled all DOB fields required for recovery.
    """
    return bool(form.birth_day.data and form.birth_month.data and form.birth_year.data)


def _birth_matches_user(form: ForgotPasswordForm, user: User) -> bool:
    """
    Compare the DOB entered in the recovery form to the DOB stored on the user.

    Returns False if the user profile is missing DOB fields.
    """
    if user.birth_day is None or user.birth_month is None or user.birth_year is None:
        return False
    return (
        int(form.birth_day.data) == user.birth_day
        and int(form.birth_month.data) == user.birth_month
        and int(form.birth_year.data) == user.birth_year
    )


def _accessible_commitments_for_user(user_id: int) -> list[Commitment]:
    """
    Return all commitments a user can see:
      - commitments they own
      - commitments shared with them as collaborator

    Deduplication:
    - If a commitment somehow appears in both lists, we keep one.
    """
    owned = _owned_commitments_for_user(user_id)
    shared = _shared_commitments_for_user(user_id)
    seen = set()
    merged = []
    for commitment in owned + shared:
        if commitment.id in seen:
            continue
        seen.add(commitment.id)
        merged.append(commitment)
    return merged


def _owned_commitments_for_user(user_id: int) -> list[Commitment]:
    """
    Commitments where the user is the owner (Commitment.user_id == user_id).
    Ordered soonest deadline first.
    """
    return db.session.scalars(
        sa.select(Commitment)
        .where(Commitment.user_id == user_id)
        .order_by(Commitment.deadline_date.asc(), Commitment.created_at.asc())
    ).all()


def _shared_commitments_for_user(user_id: int) -> list[Commitment]:
    """
    Commitments the user collaborates on (many-to-many join table).
    Ordered soonest deadline first.
    """
    return db.session.scalars(
        sa.select(Commitment)
        .join(commitment_collaborator, commitment_collaborator.c.commitment_id == Commitment.id)
        .where(commitment_collaborator.c.user_id == user_id)
        .order_by(Commitment.deadline_date.asc(), Commitment.created_at.asc())
    ).all()


def _commitments_page_context(user_id: int, now_utc: datetime | None = None) -> dict:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    user_commitments = _owned_commitments_for_user(user_id)
    shared_commitments = _shared_commitments_for_user(user_id)
    all_commitments = user_commitments + shared_commitments
    commitment_progress = {
        commitment.id: _commitment_progress_percent(commitment, now_utc)
        for commitment in all_commitments
    }
    return {
        "commitments": user_commitments,
        "shared_commitments": shared_commitments,
        "commitment_progress": commitment_progress,
    }


@app.route("/")
@app.route("/index")
def index():
    """
    Home page.
    - If logged in: provide initial_commitments for client-side rendering
      (likely used to show commitment cards immediately).
    - If logged out: initial_commitments is empty.
    """
    initial_commitments = []
    if current_user.is_authenticated:
        combined = _accessible_commitments_for_user(current_user.id)
        initial_commitments = [
            _serialize_commitment_for_home(commitment)
            for commitment in combined
        ]

    return render_template(
        'index.html',
        title='Home',
        initial_commitments=initial_commitments,
        quick_categories=CATEGORY_CHOICES,
    )


@app.route("/settings")
def settings():
    return render_template("settings.html", title="Settings")


@app.route("/sw.js")
def service_worker():
    """
    Serve the Service Worker script.

    Why this exists:
    - Browsers require the service worker JS file to be served with a JS mimetype.
    - It's typically at /sw.js so the service worker can control the whole origin scope.
    """
    return send_from_directory(
        app.static_folder, 
        "sw.js", 
        mimetype="application/javascript"
        )


@app.route("/manifest.webmanifest")
def web_manifest():
    """
    Serve the Web App Manifest used for "Add to Home Screen" / PWA metadata.
    """
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login page + login form submission.

    GET:
      - Show the login page.

    POST:
      - Validate form.
      - Interpret the login field as either:
          * an email address, OR
          * a mobile number.
      - If credentials are valid, log the user in.
      - Redirect to "next" param (if safe) or home page.

    Security:
    - We must ensure `next` is a safe local URL (no external redirect).
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        # Only email/mobile login is allowed (username login disabled).
        login_id = (form.username.data or "").strip()
        if not _is_valid_contact(login_id):
            form.username.errors.append("Please enter a valid mobile number or email address.")
            return render_template('login.html', title='Sign In', form=form)

        user = _find_user_by_contact_identifier(login_id)
        # Reject invalid contact/password combinations.
        if user is None or not user.check_password(form.password.data):
            form.password.errors.append("Invalid mobile number/email or password.")
            return render_template('login.html', title='Sign In', form=form)
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    # GET or invalid POST: render page with form + any errors.
    return render_template('login.html', title='Sign In', form=form)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    Multi-step password recovery workflow, controlled by a hidden field: form.stage.

    Stages:
      1) "contact": user enters email/phone (format check only).
      2) "birth": user enters DOB, we verify it matches a user with that contact.
      3) "reset": user sets new password, we verify DOB again, then update password.
      4) "success": display success message after reset.

    The stage is advanced only if validation passes.
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = ForgotPasswordForm()
    stage = "contact"

    try:
        if form.validate_on_submit():
            # Normalize stage input (untrusted client input).
            stage = (form.stage.data or "contact").strip().lower()
            if stage not in {"contact", "birth", "reset", "success"}:
                stage = "contact"

            # Normalize and store contact in the form so it persists across steps.
            contact_identifier = _normalize_contact(form.contact.data or "")
            form.contact.data = contact_identifier

            # ---- Stage 1: contact entry ----
            if stage == "contact":
                if not contact_identifier:
                    form.contact.errors.append("Mobile number or email address is required.")
                elif not _is_valid_contact(contact_identifier):
                    form.contact.errors.append("Enter a valid mobile number or email address.")
                else:
                    stage = "birth"

            # ---- Stage 2: verify date of birth ----
            elif stage == "birth":
                user = _find_user_by_contact_identifier(contact_identifier)
                if not contact_identifier or not _is_valid_contact(contact_identifier):
                    form.contact.errors.append("Please enter your mobile number or email address again.")
                    stage = "contact"
                else:
                    if not _birth_fields_present(form):
                        form.birth_year.errors.append("Date of birth is required.")
                    elif (
                        user is None
                        or user.birth_day is None
                        or user.birth_month is None
                        or user.birth_year is None
                        or not _birth_matches_user(form, user)
                    ):
                        form.birth_year.errors.append(GENERIC_RECOVERY_FAILURE)
                    else:
                        stage = "reset"

            # ---- Stage 3: set new password ----
            elif stage == "reset":
                user = _find_user_by_contact_identifier(contact_identifier)
                if not contact_identifier or not _is_valid_contact(contact_identifier):
                    form.contact.errors.append("Please enter your mobile number or email address again.")
                    stage = "contact"
                elif not _birth_fields_present(form):
                    form.birth_year.errors.append("Please verify your date of birth first.")
                    stage = "birth"
                elif (
                    user is None
                    or user.birth_day is None
                    or user.birth_month is None
                    or user.birth_year is None
                    or not _birth_matches_user(form, user)
                ):
                    form.birth_year.errors.append(GENERIC_RECOVERY_FAILURE)
                    stage = "birth"
                elif not form.new_password.data:
                    form.new_password.errors.append("New password is required.")
                elif len(form.new_password.data) < PASSWORD_MIN_LENGTH:
                    form.new_password.errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
                elif form.new_password.data != form.new_password2.data:
                    form.new_password2.errors.append("Passwords must match.")
                else:
                    user.set_password(form.new_password.data)
                    db.session.commit()
                    stage = "success"

        elif request.method == "POST":
            stage = (request.form.get("stage") or "contact").strip().lower()
            if stage not in {"contact", "birth", "reset", "success"}:
                stage = "contact"
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database error during forgot-password flow")
        form.contact.errors.append("Database is not ready. Run migrations and try again.")
        stage = "contact"

    form.stage.data = stage
    return render_template('forgot_password.html', title='Forgot Password', form=form, stage=stage)


@app.route('/register/send-code', methods=['POST'])
def send_registration_code():
    if current_user.is_authenticated:
        return jsonify({"ok": False, "message": "You are already signed in."}), 400

    csrf_form = EmptyForm()
    if not csrf_form.validate_on_submit():
        return jsonify({"ok": False, "message": "Invalid request."}), 400

    email = (request.form.get("email") or "").strip().lower()
    if not EMAIL_REGEX.fullmatch(email):
        return jsonify({"ok": False, "message": "Enter a valid email address."}), 400

    try:
        existing_user_id = db.session.scalar(sa.select(User.id).where(User.email == email))
        if existing_user_id is not None:
            return jsonify({"ok": False, "message": "Email already registered. Please use a different email address."}), 400
        if not app.config["MAIL_ENABLED"]:
            return jsonify({"ok": False, "message": "Email sending is not configured on the server."}), 503

        _issue_registration_code(email)
    except SQLAlchemyError:
        app.logger.exception("Database error while preparing registration verification")
        db.session.rollback()
        return jsonify({"ok": False, "message": "Database is not ready. Run migrations and try again."}), 500
    except OSError:
        app.logger.exception("Email delivery failed for registration verification")
        _clear_registration_verification()
        return jsonify({"ok": False, "message": "We could not send the email verification code. Try again later."}), 502

    return jsonify({"ok": True, "message": "Verification code sent. Check your email inbox."})


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Account creation.

    Behavior:
    - If username is provided: use it.
    - If username is empty: generate a unique username from email prefix.

    Notes:
    - This route uses an IntegrityError catch for uniqueness collisions.
      (i.e., duplicate email or username)
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()

    try:
        if form.validate_on_submit():
            contact = _normalize_contact(form.email.data or "")
            verification_ok, verification_message = _validate_registration_code(
                contact,
                form.verification_code.data or "",
            )
            if not verification_ok:
                form.verification_code.errors.append(verification_message)
                return render_template('register.html', title='Create account', form=form)

            username_input = (form.username.data or "").strip()
            if username_input:
                username_value = username_input
            else:
                username_seed = contact
                if "@" in username_seed:
                    username_seed = username_seed.split("@", 1)[0]
                username_seed = re.sub(r"[^a-zA-Z0-9_.-]", "", username_seed)
                username_value = _generate_unique_username(username_seed)

            user = User(
                username=username_value,
                email=contact,
                birth_day=int(form.birth_day.data),
                birth_month=int(form.birth_month.data),
                birth_year=int(form.birth_year.data),
            )
            user.set_password(form.password.data)

            db.session.add(user)

            try:
                db.session.commit()
                _clear_registration_verification()
                login_user(user)
                return redirect(url_for('index'))

            except IntegrityError:
                db.session.rollback()
                form.username.errors.append("Username or email already exists.")
                return render_template('register.html', title='Create account', form=form)
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database error during registration")
        form.email.errors.append("Database is not ready. Run migrations and try again.")
        return render_template('register.html', title='Create account', form=form)

    return render_template('register.html', title='Create account', form=form)


@app.route('/logout')
def logout():
    """
    End the user's session and return to home page.
    """
    logout_user()
    return redirect(url_for('index'))


@app.route('/commitments')
@login_required
def commitments():
    """
    Commitments list page (HTML).

    Provides:
    - owned commitments
    - shared commitments
    - progress percent per commitment (id -> percent)
    - forms needed by the template
    - flag to open the create modal automatically (via query param)
    """
    action_form = EmptyForm()
    commitment_form = CommitmentForm()
    open_create_modal = request.args.get("open_create") == "1"
    context = _commitments_page_context(current_user.id)

    return render_template(
        'commitments.html',
        title='Commitments',
        commitments=context["commitments"],
        shared_commitments=context["shared_commitments"],
        action_form=action_form,
        commitment_form=commitment_form,
        open_create_modal=open_create_modal,
        commitment_progress=context["commitment_progress"],
    )


@app.route('/commitments', methods=['POST'])
@login_required
def create_commitment():
    """
    Create commitment via HTML form submission.

    If form invalid:
    - re-render commitments page with create modal open and errors visible.
    """
    form = CommitmentForm()
    if not form.validate_on_submit():
        action_form = EmptyForm()
        context = _commitments_page_context(current_user.id)
        return render_template(
            'commitments.html',
            title='Commitments',
            commitments=context["commitments"],
            shared_commitments=context["shared_commitments"],
            action_form=action_form,
            commitment_form=form,
            open_create_modal=True,
            commitment_progress=context["commitment_progress"],
        ), 400

    commitment = Commitment(
        user_id=current_user.id,
        category=_normalize_category(form.category.data),
        title=form.title.data.strip(),
        description=form.description.data.strip() if form.description.data else None,
        deadline_date=form.deadline_date.data,
        status='active',
    )
    db.session.add(commitment)
    db.session.commit()
    flash('Commitment created successfully.')
    return redirect(url_for('commitments'))


@app.route('/api/commitments/quick', methods=['POST'])
def quick_create_commitment():
    """
    Quick-create commitment from JSON.
    Used by client-side UI (e.g., home page quick add).

    If not authenticated:
    - returns 401 with message instructing client to store locally
    """
    data = request.get_json(silent=True) or {}
    payload, error = _parse_commitment_payload(data)
    if error is not None:
        message, status_code = error
        return jsonify({"ok": False, "message": message}), status_code

    if not current_user.is_authenticated:
        return jsonify(
            {
                "ok": False,
                "message": "Not logged in. Save this commitment in browser cache only.",
            }
        ), 401

    commitment = Commitment(
        user_id=current_user.id,
        category=payload["category"],
        title=payload["title"],
        description=payload["description"],
        deadline_date=payload["deadline_date"],
        status='active',
    )
    db.session.add(commitment)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "saved_to_db": True,
            "commitment": {
                "id": commitment.id,
                "category": commitment.category or "",
                "title": commitment.title,
                "description": commitment.description,
                "deadline_date": commitment.deadline_date.isoformat(),
                "status": commitment.status,
                "created_at": commitment.created_at.isoformat() if commitment.created_at else None,
                "member_count": 1,
                "can_edit": True,
                "can_delete": True,
            },
        }
    ), 201


@app.route('/api/commitments/<int:commitment_id>/quick', methods=['PATCH'])
@login_required
def quick_update_commitment(commitment_id):
    """
    Quick update a commitment from JSON.
    User must be owner or collaborator (enforced by query_commitment_accessible_to_user).
    """
    commitment = _find_accessible_commitment(commitment_id, current_user.id)
    if commitment is None:
        return jsonify({"ok": False, "message": "Commitment not found."}), 404

    data = request.get_json(silent=True) or {}
    payload, error = _parse_commitment_payload(data)
    if error is not None:
        message, status_code = error
        return jsonify({"ok": False, "message": message}), status_code

    commitment.title = payload["title"]
    commitment.category = payload["category"]
    commitment.description = payload["description"]
    commitment.deadline_date = payload["deadline_date"]
    db.session.commit()

    return jsonify({"ok": True, "commitment": _serialize_commitment_for_home(commitment)}), 200


@app.route('/api/commitments/<int:commitment_id>/complete', methods=['POST'])
@login_required
def quick_complete_commitment(commitment_id):
    """
    Mark a commitment as completed.
    """
    commitment = _find_accessible_commitment(commitment_id, current_user.id)
    if commitment is None:
        return jsonify({"ok": False, "message": "Commitment not found."}), 404

    commitment.status = "completed"
    db.session.commit()
    return jsonify({"ok": True, "commitment": _serialize_commitment_for_home(commitment)}), 200


@app.route('/api/commitments/<int:commitment_id>/recover', methods=['POST'])
@login_required
def quick_recover_commitment(commitment_id):
    """
    Set a commitment back to active (undo completion).
    """
    commitment = _find_accessible_commitment(commitment_id, current_user.id)
    if commitment is None:
        return jsonify({"ok": False, "message": "Commitment not found."}), 404

    commitment.status = "active"
    db.session.commit()
    return jsonify({"ok": True, "commitment": _serialize_commitment_for_home(commitment)}), 200


@app.route('/api/commitments/<int:commitment_id>/quick', methods=['DELETE'])
@login_required
def quick_delete_commitment(commitment_id):
    commitment = db.session.scalar(
        sa.select(Commitment).where(
            Commitment.id == commitment_id,
            Commitment.user_id == current_user.id,
        )
    )
    if commitment is None:
        return jsonify({"ok": False, "message": "Commitment not found."}), 404

    db.session.delete(commitment)
    db.session.commit()
    return jsonify({"ok": True}), 200


@app.route('/api/commitments/<int:commitment_id>/leave', methods=['POST'])
@login_required
def quick_leave_commitment(commitment_id):
    commitment = _find_accessible_commitment(commitment_id, current_user.id)
    if commitment is None:
        return jsonify({"ok": False, "message": "Commitment not found."}), 404

    if commitment.user_id == current_user.id:
        return jsonify({"ok": False, "message": "Owner cannot leave this commitment."}), 400

    member = next((user for user in commitment.collaborators if user.id == current_user.id), None)
    if member is None:
        return jsonify({"ok": False, "message": "You are not a member of this commitment."}), 400

    commitment.collaborators.remove(member)
    db.session.commit()
    return jsonify({"ok": True, "message": "You left the commitment."}), 200


@app.route('/api/commitments/<int:commitment_id>/members', methods=['GET', 'POST'])
@login_required
def quick_commitment_members(commitment_id):
    if request.method == 'GET':
        commitment = _find_accessible_commitment(commitment_id, current_user.id)
        if commitment is None:
            return jsonify({"ok": False, "message": "Commitment not found."}), 404

        members = [commitment.owner] + sorted(
            commitment.collaborators,
            key=lambda user: user.username.lower(),
        )
        return jsonify(
            {
                "ok": True,
                "commitment": {
                    "id": commitment.id,
                    "title": commitment.title,
                },
                "member_count": len(members),
                "members": [
                    {
                        "id": member.id,
                        "username": member.username,
                        "is_owner": member.id == commitment.owner.id,
                    }
                    for member in members
                ],
            }
        ), 200

    commitment = db.session.scalar(
        sa.select(Commitment).where(
            Commitment.id == commitment_id,
            Commitment.user_id == current_user.id,
        )
    )
    if commitment is None:
        return jsonify({"ok": False, "message": "Commitment not found."}), 404

    data = request.get_json(silent=True) or {}
    contact = _normalize_contact(data.get("contact") or "")
    if not contact:
        return jsonify({"ok": False, "message": "Mobile number or email address is required."}), 400
    if not _is_valid_contact(contact):
        return jsonify({"ok": False, "message": "Enter a valid mobile number or email address."}), 400

    member = _find_user_by_contact_identifier(contact)
    if member is None:
        return jsonify({"ok": False, "message": "No user found with that mobile number or email address."}), 404
    if member.id == current_user.id:
        return jsonify({"ok": False, "message": "You are already the owner of this commitment."}), 400
    if any(user.id == member.id for user in commitment.collaborators):
        return jsonify({"ok": False, "message": "This member is already added."}), 400

    commitment.collaborators.append(member)
    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "message": "Member added successfully.",
            "member_count": 1 + len(commitment.collaborators),
        }
    ), 200


@app.route('/api/commitments/sync-local', methods=['POST'])
def sync_local_commitments():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "message": "Login required."}), 401

    data = request.get_json(silent=True) or {}
    incoming = data.get("commitments")
    if not isinstance(incoming, list):
        return jsonify({"ok": False, "message": "commitments must be a list."}), 400

    existing_titles = {
        (title or "").strip().casefold()
        for title in db.session.scalars(
            sa.select(Commitment.title).where(Commitment.user_id == current_user.id)
        ).all()
        if title
    }

    created = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    created_items = []
    seen_payload_titles = set()

    for item in incoming[:100]:
        if not isinstance(item, dict):
            skipped_invalid += 1
            continue

        title = (item.get("title") or "").strip()
        category = _normalize_category(item.get("category"))
        description = (item.get("description") or "").strip()
        deadline_date_raw = (item.get("deadline_date") or "").strip()

        if not title or not deadline_date_raw or len(title) > 140:
            skipped_invalid += 1
            continue

        dedupe_key = title.casefold()
        if dedupe_key in existing_titles or dedupe_key in seen_payload_titles:
            skipped_duplicates += 1
            continue

        try:
            deadline_date_value = date.fromisoformat(deadline_date_raw)
        except ValueError:
            skipped_invalid += 1
            continue

        commitment = Commitment(
            user_id=current_user.id,
            category=category,
            title=title,
            description=description or None,
            deadline_date=deadline_date_value,
            status='active',
        )
        db.session.add(commitment)
        db.session.commit()

        existing_titles.add(dedupe_key)
        seen_payload_titles.add(dedupe_key)
        created += 1
        created_items.append(_serialize_commitment_for_home(commitment))

    return jsonify(
        {
            "ok": True,
            "created": created,
            "skipped_duplicates": skipped_duplicates,
            "skipped_invalid": skipped_invalid,
            "created_items": created_items,
        }
    ), 200


@app.route('/commitments/<int:commitment_id>/members')
@login_required
def commitment_members(commitment_id):
    commitment = db.session.get(Commitment, commitment_id)
    if commitment is None:
        abort(404)

    if not _is_owner_or_collaborator(commitment, current_user.id):
        abort(403)

    members = [commitment.owner] + sorted(
        commitment.collaborators,
        key=lambda user: user.username.lower(),
    )
    return render_template(
        'commitment_members.html',
        title='Commitment Members',
        commitment=commitment,
        members=members,
    )


@app.route('/commitments/<int:commitment_id>/delete', methods=['POST'])
@login_required
def delete_commitment(commitment_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)

    commitment = db.session.scalar(
        sa.select(Commitment).where(
            Commitment.id == commitment_id,
            Commitment.user_id == current_user.id,
        )
    )
    if commitment is None:
        abort(404)

    db.session.delete(commitment)
    db.session.commit()
    flash('Commitment deleted.')
    return redirect(url_for('commitments'))


@app.route("/commitments/<int:commitment_id>/toggle-status", methods=["POST"])
@login_required
def toggle_commitment_status(commitment_id):
    commitment = db.session.get(Commitment, commitment_id)

    if commitment is None or commitment.owner != current_user:
        flash("You are not allowed to update this commitment.")
        return redirect(url_for("commitments"))

    commitment.status = "complete" if commitment.status == "active" else "active"
    db.session.commit()

    flash("Commitment status updated.")
    return redirect(url_for("commitments"))


@app.route('/commitments/<int:commitment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_commitment(commitment_id):
    commitment = db.session.scalar(
        sa.select(Commitment).where(
            Commitment.id == commitment_id,
            Commitment.user_id == current_user.id,
        )
    )
    if commitment is None:
        abort(404)

    form = CommitmentForm(obj=commitment)
    if form.validate_on_submit():
        commitment.category = _normalize_category(form.category.data)
        commitment.title = form.title.data.strip()
        commitment.description = form.description.data.strip() if form.description.data else None
        commitment.deadline_date = form.deadline_date.data
        db.session.commit()
        flash('Commitment updated successfully.')
        return redirect(url_for('commitments'))

    return render_template(
        'edit_commitment.html',
        title='Edit Commitment',
        form=form,
        commitment=commitment,
    )
