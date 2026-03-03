import sqlalchemy as sa
import re
from datetime import datetime, date
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
    HiddenField,
    TextAreaField,
    DateField,
    SelectField,
)
from wtforms.validators import (
    ValidationError,
    DataRequired,
    EqualTo,
    Optional,
)
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import User


# Keep contact validation rules in one place so routes/forms stay consistent.
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_REGEX = re.compile(r"^\+?[0-9][0-9\-\s]{6,19}$")


def _build_birth_choices() -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """Build DOB dropdown choices shared by registration and password reset forms."""
    day_choices = [("", "Day")] + [(str(day), str(day)) for day in range(1, 32)]
    month_choices = [("", "Month")] + [(str(month), str(month)) for month in range(1, 13)]
    current_year = datetime.now().year
    year_choices = [("", "Year")] + [
        (str(year), str(year)) for year in range(current_year, current_year - 120, -1)
    ]
    return day_choices, month_choices, year_choices


def _populate_birth_choice_fields(form: FlaskForm) -> None:
    day_choices, month_choices, year_choices = _build_birth_choices()
    form.birth_day.choices = day_choices
    form.birth_month.choices = month_choices
    form.birth_year.choices = year_choices


class LoginForm(FlaskForm):
    username = StringField("Mobile number or email address", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


class RegistrationForm(FlaskForm):
    username = StringField("Usernamer (optional)", validators=[Optional()])
    email = StringField("Mobile number or email address", validators=[DataRequired()])
    birth_day = SelectField("Day", choices=[], validators=[Optional()])
    birth_month = SelectField("Month", choices=[], validators=[Optional()])
    birth_year = SelectField("Year", choices=[], validators=[Optional()])
    password = PasswordField("Password", validators=[DataRequired()])
    password2 = PasswordField(
        "Repeat Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Continue")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _populate_birth_choice_fields(self)

    def validate_username(self, username):
        value = (username.data or "").strip()
        if not value:
            return
        try:
            user_id = db.session.scalar(sa.select(User.id).where(User.username == value))
        except SQLAlchemyError:
            raise ValidationError("Database is not ready. Run migrations and try again.")
        if user_id is not None:
            raise ValidationError("Username already taken. Please choose a different one.")

    def validate_email(self, email):
        value = email.data.strip()
        if not EMAIL_REGEX.fullmatch(value) and not MOBILE_REGEX.fullmatch(value):
            raise ValidationError("Enter a valid mobile number or email address.")

        normalized = value.lower() if "@" in value else value
        try:
            user_id = db.session.scalar(sa.select(User.id).where(User.email == normalized))
        except SQLAlchemyError:
            raise ValidationError("Database is not ready. Run migrations and try again.")
        if user_id is not None:
            raise ValidationError("Email already registered. Please use a different email address.")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        has_birth = bool(self.birth_day.data and self.birth_month.data and self.birth_year.data)
        if not has_birth:
            message = "Date of birth is required."
            if not self.birth_day.data:
                self.birth_day.errors.append(message)
            if not self.birth_month.data:
                self.birth_month.errors.append(message)
            if not self.birth_year.data:
                self.birth_year.errors.append(message)
            is_valid = False
        return is_valid


class ForgotPasswordForm(FlaskForm):
    stage = HiddenField(default="contact")
    contact = StringField("Mobile number or email address", validators=[Optional()])
    birth_day = SelectField("Day", choices=[], validators=[Optional()])
    birth_month = SelectField("Month", choices=[], validators=[Optional()])
    birth_year = SelectField("Year", choices=[], validators=[Optional()])
    new_password = PasswordField("New Password", validators=[Optional()])
    new_password2 = PasswordField(
        "Repeat Password",
        validators=[Optional(), EqualTo("new_password", message="Passwords must match.")],
    )
    submit = SubmitField("Continue")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _populate_birth_choice_fields(self)


class CommitmentForm(FlaskForm):
    category = SelectField(
        "Category",
        choices=[
            ("", "Select a category"),
            ("general", "General"),
            ("study", "Study"),
            ("health", "Health"),
            ("travel", "Travel"),
        ],
        default="",
        validators=[Optional()],
    )
    title = StringField("Title", validators=[DataRequired()])
    description = TextAreaField("Description", validators=[Optional()])
    deadline_date = DateField("Deadline Date", validators=[DataRequired()], format="%Y-%m-%d")
    submit = SubmitField("Create Commitment")

    def validate_deadline_date(self, deadline_date):
        if deadline_date.data is None:
            return
        if deadline_date.data < date.today():
            raise ValidationError("Deadline date cannot be earlier than today.")


class EmptyForm(FlaskForm):
    submit = SubmitField("Submit")
