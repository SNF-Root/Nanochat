"""Email allow-list for SAML-authenticated users.

Env:
  SAML_ALLOWED_EMAILS_PATH  Path to YAML file. Supported shapes:
    - Root list: ["a@b.com", ...]
    - Mapping with "allowed_emails" or "emails" key holding that list
  SAML_ALLOWED_EMAILS  Optional comma-separated list merged with the YAML set (deprecated;
    prefer moving all addresses into the YAML file and unsetting this variable).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
_legacy_env_warned = False


def _emails_from_yaml_doc(data: Any) -> set[str]:
    if data is None:
        return set()
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("allowed_emails", "emails"):
            if key in data:
                items = data[key]
                break
        else:
            raise ValueError(
                "YAML must be a list of emails or a mapping with "
                '"allowed_emails" or "emails"'
            )
    else:
        raise ValueError("YAML root must be a list or a mapping")

    if not isinstance(items, list):
        raise ValueError('"allowed_emails" / "emails" must be a list')

    out: set[str] = set()
    for i, item in enumerate(items):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"Invalid email entry at index {i}: {item!r}")
        out.add(item.strip().lower())
    return out


def _load_emails_from_yaml_path(path: str) -> set[str]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(
            f"Cannot read SAML_ALLOWED_EMAILS_PATH={path!r}: {e}. "
            "In Docker, bind-mount your YAML (e.g. "
            "-v /etc/nano-chat/allowed_emails.yaml:/run/config/allowed_emails.yaml:ro) "
            "and set SAML_ALLOWED_EMAILS_PATH=/run/config/allowed_emails.yaml."
        ) from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML in SAML_ALLOWED_EMAILS_PATH={path!r}: {e}") from e
    try:
        return _emails_from_yaml_doc(data)
    except ValueError as e:
        raise RuntimeError(f"SAML_ALLOWED_EMAILS_PATH={path!r}: {e}") from e


def load_allowed_emails() -> set[str]:
    global _legacy_env_warned
    out: set[str] = set()
    path = os.getenv("SAML_ALLOWED_EMAILS_PATH", "").strip()
    if path:
        out |= _load_emails_from_yaml_path(path)
    raw = os.getenv("SAML_ALLOWED_EMAILS", "")
    if raw.strip():
        if not _legacy_env_warned:
            logger.warning(
                "SAML_ALLOWED_EMAILS is deprecated; merge these addresses into "
                "SAML_ALLOWED_EMAILS_PATH and remove SAML_ALLOWED_EMAILS."
            )
            _legacy_env_warned = True
        out |= {e.strip().lower() for e in raw.split(",") if e.strip()}
    return out


def is_email_allowed(email: str, allowed: set[str]) -> bool:
    if not email:
        return False
    return email.strip().lower() in allowed
