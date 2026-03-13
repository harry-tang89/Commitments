import re


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
