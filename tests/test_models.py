from app import db
from app.models import User


def test_password_hash_is_stored_and_can_be_verified():
    """
    This test verifies three important security behaviors:

    1) When we "set" a password, the app stores a *hash* (not the raw password).
    2) The correct password validates successfully.
    3) An incorrect password does not validate.

    In other words: password -> hashed password stored -> check_password verifies.
    """

    # Create a new user object in memory (NOT yet saved to the database).
    # Using realistic-looking values makes the intent clear.
    new_user = User(username="alice", email="alice@example.com")

    # This should NOT store "secret123" anywhere directly.
    # A typical implementation hashes the password (e.g., PBKDF2/bcrypt/argon2)
    # and stores the hash string in new_user.password_hash.
    raw_password = "secret123"
    new_user.set_password(raw_password)

    # Persist the user record to the database so we test the real storage path.
    db.session.add(new_user)
    db.session.commit()

    # -------------------------------------------------------------------------
    # Assertions (checks)
    # -------------------------------------------------------------------------

    # 1) Ensure the stored value is NOT the plain password.
    # If this failed, it would mean the password is being stored insecurely.
    assert new_user.password_hash != raw_password

    # 2) The correct password should pass verification.
    # check_password() typically hashes the input and compares it to password_hash.
    assert new_user.check_password(raw_password)

    # 3) A wrong password should fail verification.
    wrong_password = "wrong-password"
    assert not new_user.check_password(wrong_password)
