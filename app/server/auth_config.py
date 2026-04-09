"""Email allow-list for SAML-authenticated users."""

import os


def load_allowed_emails() -> set[str]:
    raw = os.getenv("SAML_ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_email_allowed(email: str, allowed: set[str]) -> bool:
    if not email:
        return False
    return email.strip().lower() in allowed
