"""
Integration-style tests for authentication and commitments.

These tests use Flask's test client to:
- Register a user
- Log in (valid and invalid)
- Create a Commitment (and verify it is saved correctly)
- Verify that protected pages require login
"""

from datetime import date, timedelta

import sqlalchemy as sa

from app import app, db
from app.models import Commitment, User


# -----------------------------------------------------------------------------
# Helper functions (test utilities)
# -----------------------------------------------------------------------------
def create_user_in_db(
    username: str = "testuser",
    email: str = "test@example.com",
    plaintext_password: str = "password123",
    birth_day: int | None = None,
    birth_month: int | None = None,
    birth_year: int | None = None,
) -> User:
    """
    Create and persist a User row in the test database.

    Why this exists:
    - Many tests need a user in the DB first (e.g., to test login).
    - Centralizing creation avoids repeating the same setup code.
    """
    user_record = User(
        username=username,
        email=email,
        birth_day=birth_day,
        birth_month=birth_month,
        birth_year=birth_year,
    )

    # IMPORTANT: set_password should HASH the password and store the hash.
    # We never store plaintext passwords in the database.
    user_record.set_password(plaintext_password)

    # Persist to the DB so it can be found/used by the app during requests.
    db.session.add(user_record)
    db.session.commit()
    return user_record


def login_as_user(
    http_client,
    username: str = "testuser",
    plaintext_password: str = "password123",
):
    """
    Log in via the /login route using the Flask test client.

    follow_redirects=True:
    - Many apps redirect after login (302 -> /index or similar).
    - Setting True makes the client "follow" redirects so the final response is 200.
    """
    return http_client.post(
        "/login",
        data={
            "username": username,
            "password": plaintext_password,
            # Many login forms include a "remember me" checkbox.
            # Some apps treat "y" as checked.
            "remember_me": "y",
        },
        follow_redirects=True,
    )


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

def test_register_route_creates_user_in_database(http_client):
    """
    GIVEN: A user submits the registration form.
    WHEN:  POST /register is called with valid data.
    THEN:  The response is successful, and a User row exists in the database.
    """
    captured_code: dict[str, str] = {}

    def fake_send_verification_email(recipient: str, code: str) -> None:
        captured_code["recipient"] = recipient
        captured_code["code"] = code

    app.config["MAIL_ENABLED"] = True
    import app.routes as routes_module

    original_sender = routes_module._send_registration_verification_email
    routes_module._send_registration_verification_email = fake_send_verification_email
    try:
        send_code_response = http_client.post(
            "/register/send-code",
            data={"email": "newuser@example.com"},
        )
        assert send_code_response.status_code == 200
        assert captured_code["code"]

        register_response = http_client.post(
            "/register",
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "verification_code": captured_code["code"],
                "birth_day": "1",
                "birth_month": "1",
                "birth_year": "2000",
                "password": "securepass",
                "password2": "securepass",  # typical "confirm password" field
            },
            follow_redirects=True,
        )
    finally:
        routes_module._send_registration_verification_email = original_sender

    # Query the database directly to verify persistence.
    created_user = db.session.scalar(
        sa.select(User).where(User.username == "newuser")
    )

    assert register_response.status_code == 200
    assert created_user is not None


def test_register_page_uses_create_account_heading(http_client):
    """
    GIVEN: A visitor opens the registration page.
    WHEN:  GET /register is requested.
    THEN:  The page renders successfully and shows the expected heading text.
    """
    response = http_client.get("/register")

    assert response.status_code == 200
    assert b"Create account" in response.data


def test_register_requires_email_verification_code(http_client):
    response = http_client.post(
        "/register",
        data={
            "username": "newuser",
            "email": "newuser@example.com",
            "verification_code": "123456",
            "birth_day": "1",
            "birth_month": "1",
            "birth_year": "2000",
            "password": "securepass",
            "password2": "securepass",
        },
        follow_redirects=True,
    )

    created_user = db.session.scalar(
        sa.select(User).where(User.username == "newuser")
    )

    assert response.status_code == 200
    assert b"Please request a new email verification code." in response.data
    assert created_user is None


def test_register_allows_dev_bypass_code(http_client):
    original_bypass_enabled = app.config["DEV_REGISTRATION_CODE_BYPASS"]
    original_bypass_code = app.config["DEV_REGISTRATION_CODE"]
    app.config["DEV_REGISTRATION_CODE_BYPASS"] = True
    app.config["DEV_REGISTRATION_CODE"] = "000000"

    try:
        response = http_client.post(
            "/register",
            data={
                "username": "bypassuser",
                "email": "bypass@example.com",
                "verification_code": "000000",
                "birth_day": "1",
                "birth_month": "1",
                "birth_year": "2000",
                "password": "securepass",
                "password2": "securepass",
            },
            follow_redirects=True,
        )
    finally:
        app.config["DEV_REGISTRATION_CODE_BYPASS"] = original_bypass_enabled
        app.config["DEV_REGISTRATION_CODE"] = original_bypass_code

    created_user = db.session.scalar(
        sa.select(User).where(User.username == "bypassuser")
    )

    assert response.status_code == 200
    assert created_user is not None


def test_login_with_wrong_password_shows_error_message(http_client):
    """
    GIVEN: A user exists in the database.
    WHEN:  They attempt to log in with an incorrect password.
    THEN:  The response contains an "Invalid username or password" message.
    """
    # Arrange: create a real user in the DB with a known correct password.
    create_user_in_db(
        username="bob",
        email="bob@example.com",
        plaintext_password="correct-password",
    )

    # Act: attempt login with the wrong password.
    login_response = http_client.post(
        "/login",
        data={"username": "bob", "password": "wrong-password"},
        follow_redirects=True,
    )

    # Assert: still 200 because we followed redirects to the final page,
    # and the page should display an error message.
    assert login_response.status_code == 200

    # response.data is bytes, so we compare against a bytes literal (b"...").
    assert b"Invalid username or password" in login_response.data


def test_forgot_password_flow_updates_password(http_client):
    """
    GIVEN: A user with known contact and birth date exists.
    WHEN:  They complete the three-step forgot-password flow
           (contact -> birth verification -> password reset).
    THEN:  The password is updated and the user can sign in with the new password.
    """
    # Arrange: create an account with birth-date data required by recovery flow.
    create_user_in_db(
        username="recoveruser",
        email="recover@example.com",
        plaintext_password="old-password-123",
        birth_day=15,
        birth_month=8,
        birth_year=1998,
    )

    # Step 1: submit contact identifier (email/username) to begin recovery.
    contact_step = http_client.post(
        "/forgot-password",
        data={
            "stage": "contact",
            "contact": "recover@example.com",
        },
        follow_redirects=True,
    )
    assert contact_step.status_code == 200
    assert b"Verify your date of birth" in contact_step.data

    # Step 2: verify date of birth for identity confirmation.
    birth_step = http_client.post(
        "/forgot-password",
        data={
            "stage": "birth",
            "contact": "recover@example.com",
            "birth_day": "15",
            "birth_month": "8",
            "birth_year": "1998",
        },
        follow_redirects=True,
    )
    assert birth_step.status_code == 200
    assert b"Set a new password" in birth_step.data

    # Step 3: provide and confirm the new password.
    reset_step = http_client.post(
        "/forgot-password",
        data={
            "stage": "reset",
            "contact": "recover@example.com",
            "birth_day": "15",
            "birth_month": "8",
            "birth_year": "1998",
            "new_password": "new-password-123",
            "new_password2": "new-password-123",
        },
        follow_redirects=True,
    )
    assert reset_step.status_code == 200
    assert b"Password updated. Please sign in." in reset_step.data

    # Final assertion: login succeeds with updated credentials.
    login_with_new_password = http_client.post(
        "/login",
        data={
            "username": "recoveruser",
            "password": "new-password-123",
        },
        follow_redirects=True,
    )
    assert login_with_new_password.status_code == 200
    assert b"Logout" in login_with_new_password.data


def test_forgot_password_contact_step_does_not_disclose_account_existence(http_client):
    """
    GIVEN: No account exists for the submitted contact.
    WHEN:  The user starts forgot-password with a syntactically valid contact.
    THEN:  The flow should move to DOB verification without exposing whether
           the contact exists.
    """
    response = http_client.post(
        "/forgot-password",
        data={
            "stage": "contact",
            "contact": "unknown@example.com",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Verify your date of birth" in response.data
    assert b"We could not find an account with that mobile number or email address." not in response.data


def test_post_commitment_creates_commitment_row(http_client):
    """
    GIVEN: A logged-in user.
    WHEN:  They submit the create-commitment form (POST /commitments).
    THEN:  A Commitment row is created in the database with cleaned fields
           (e.g., stripped whitespace) and linked to that user.
    """
    # Arrange: user must exist and be logged in, otherwise /commitments may reject.
    create_user_in_db()
    login_as_user(http_client)

    # This creates a date 7 days from today, formatted as YYYY-MM-DD,
    # which is a common HTML date input format.
    target_date_iso = (date.today() + timedelta(days=7)).isoformat()

    # Act: submit a new commitment.
    create_response = http_client.post(
        "/commitments",
        data={
            # Intentionally include extra whitespace to test that the app trims input.
            "title": "  Finish sprint work  ",
            "description": "  Update backend tests  ",
            "target_date": target_date_iso,
        },
        follow_redirects=True,
    )

    # Assert: verify the record was saved, and that whitespace was stripped.
    saved_commitment = db.session.scalar(
        sa.select(Commitment).where(Commitment.title == "Finish sprint work")
    )

    assert create_response.status_code == 200
    assert saved_commitment is not None

    # Confirms that description also got trimmed by the app (if your app does that).
    assert saved_commitment.description == "Update backend tests"

    # Confirms the commitment is linked to some user record (logged-in user).
    assert saved_commitment.user_id is not None


def test_commitments_page_redirects_to_login_when_logged_out(http_client):
    """
    GIVEN: No user is logged in.
    WHEN:  They request a protected page (GET /commitments).
    THEN:  The app redirects them to the login page (302 redirect).
    """
    # follow_redirects=False means we stop at the redirect response,
    # so we can assert it is a 302 and inspect the Location header.
    response = http_client.get("/commitments", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_quick_commitment_api_returns_401_when_logged_out(http_client):
    """
    GIVEN: No authenticated session.
    WHEN:  POST /api/commitments/quick is called.
    THEN:  The API rejects the request with HTTP 401 and ok=False JSON.
    """
    response = http_client.post(
        "/api/commitments/quick",
        json={
            "title": "Cache-only goal",
            "description": "Not logged in",
            "target_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 401
    payload = response.get_json()
    assert payload is not None
    assert payload["ok"] is False


def test_quick_commitment_api_creates_row_when_logged_in(http_client):
    """
    GIVEN: A logged-in user.
    WHEN:  They call POST /api/commitments/quick with valid payload.
    THEN:  The API returns 201, reports DB persistence, and a Commitment row exists.
    """
    # Arrange: authenticated user context.
    create_user_in_db()
    login_as_user(http_client)

    # Act: create a commitment through JSON API.
    target_date_iso = (date.today() + timedelta(days=5)).isoformat()
    response = http_client.post(
        "/api/commitments/quick",
        json={
            "title": "Quick API Commitment",
            "description": "Saved in DB",
            "target_date": target_date_iso,
        },
    )

    # Assert via database lookup and API contract checks.
    saved_commitment = db.session.scalar(
        sa.select(Commitment).where(Commitment.title == "Quick API Commitment")
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload is not None
    assert payload["ok"] is True
    assert payload["saved_to_db"] is True
    assert saved_commitment is not None


def test_sync_local_commitments_creates_only_non_duplicate_titles(http_client):
    """
    GIVEN: A logged-in user already has one commitment title in DB.
    WHEN:  They sync local commitments including one duplicate and one new title.
    THEN:  Only the new title is inserted, and duplicate count is reported.
    """
    # Arrange: create authenticated user and pre-existing row.
    user = create_user_in_db()
    login_as_user(http_client)

    existing = Commitment(
        user_id=user.id,
        title="Existing Title",
        description="Already there",
        target_date=date.today() + timedelta(days=1),
        status="active",
    )
    db.session.add(existing)
    db.session.commit()

    # Act: sync a mixed payload (duplicate + new commitment).
    response = http_client.post(
        "/api/commitments/sync-local",
        json={
            "commitments": [
                {
                    "title": "Existing Title",
                    "description": "Should be skipped",
                    "target_date": (date.today() + timedelta(days=2)).isoformat(),
                },
                {
                    "title": "New Local Goal",
                    "description": "Should be created",
                    "target_date": (date.today() + timedelta(days=3)).isoformat(),
                },
            ]
        },
    )

    # Assert: only non-duplicate commitment is saved.
    created = db.session.scalar(
        sa.select(Commitment).where(
            Commitment.user_id == user.id,
            Commitment.title == "New Local Goal",
        )
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload["ok"] is True
    assert payload["created"] == 1
    assert payload["skipped_duplicates"] == 1
    assert created is not None


def test_sync_local_commitments_requires_login(http_client):
    """
    GIVEN: No logged-in user.
    WHEN:  POST /api/commitments/sync-local is called.
    THEN:  The endpoint responds with HTTP 401 Unauthorized.
    """
    response = http_client.post(
        "/api/commitments/sync-local",
        json={"commitments": []},
    )

    assert response.status_code == 401
