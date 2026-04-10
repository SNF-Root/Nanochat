"""
Stanford SAML (SP) settings for python3-saml (OneLogin SAML Toolkit).

Env:
  SAML_SP_ENTITY_ID       SP entity ID (default https://nano-chat.su.domains/saml/metadata)
  SAML_SP_ACS_URL         Assertion Consumer Service URL (POST)
  SAML_IDP_ENTITY_ID      IdP entity ID from Stanford metadata
  SAML_IDP_SSO_URL        IdP single sign-on URL
  SAML_IDP_X509_CERT      IdP signing cert PEM (use \\n for newlines) OR
  SAML_IDP_X509_CERT_PATH path to PEM file
  SAML_STRICT             "true"/"false" (default true)
  SAML_DEBUG              "true"/"false" (default false)
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from onelogin.saml2.auth import OneLogin_Saml2_Auth


def _load_idp_x509_cert() -> str:
    path = os.getenv("SAML_IDP_X509_CERT_PATH", "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            raise RuntimeError(
                f"Cannot read SAML_IDP_X509_CERT_PATH={path!r}: {e}. "
                "In Docker, mount the host PEM into the container (e.g. "
                "-v /etc/ssl/certs/your.pem:/run/saml/idp.pem:ro) and set "
                "SAML_IDP_X509_CERT_PATH=/run/saml/idp.pem."
            ) from e
    raw = os.getenv("SAML_IDP_X509_CERT", "").strip()
    if raw:
        return raw.replace("\\n", "\n").strip()
    return ""


def saml_is_configured() -> bool:
    return bool(os.getenv("SAML_IDP_SSO_URL", "").strip() and _load_idp_x509_cert())


def build_saml_settings() -> dict[str, Any]:
    entity_id = os.getenv(
        "SAML_SP_ENTITY_ID", "https://nano-chat.su.domains/saml/metadata"
    ).strip()
    acs_url = os.getenv(
        "SAML_SP_ACS_URL",
        "https://nano-chat.su.domains/auth/saml/callback",
    ).strip()
    idp_entity = os.getenv("SAML_IDP_ENTITY_ID", "").strip()
    idp_sso = os.getenv("SAML_IDP_SSO_URL", "").strip()
    cert = _load_idp_x509_cert()

    if not idp_sso or not cert:
        raise RuntimeError(
            "SAML is not configured: set SAML_IDP_SSO_URL and SAML_IDP_X509_CERT "
            "or SAML_IDP_X509_CERT_PATH"
        )

    strict = os.getenv("SAML_STRICT", "true").lower() in ("1", "true", "yes")
    debug = os.getenv("SAML_DEBUG", "false").lower() in ("1", "true", "yes")

    return {
        "strict": strict,
        "debug": debug,
        "sp": {
            "entityId": entity_id,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "attributeConsumingService": {
                "serviceName": "Nano Chat",
                "serviceDescription": "Nano Chat SP",
                "requestedAttributes": [
                    {"name": "urn:mace:dir:attribute-def:mail", "isRequired": False},
                    {"name": "urn:oid:0.9.2342.19200300.100.1.3", "isRequired": False},
                ],
            },
            "NameIDFormat": (
                "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
            ),
            "x509cert": "",
            "privateKey": "",
        },
        "idp": {
            "entityId": idp_entity or idp_sso,
            "singleSignOnService": {
                "url": idp_sso,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": cert,
        },
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": False,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "wantMessagesSigned": False,
            "wantAssertionsSigned": True,
            "wantAssertionsEncrypted": False,
            "wantNameIdEncrypted": False,
        },
    }


def request_data_from_parsed_acs(
    *,
    https_on: bool,
    http_host: str,
    path: str,
    get_data: dict[str, str],
    post_data: dict[str, str],
) -> dict[str, Any]:
    return {
        "https": "on" if https_on else "off",
        "http_host": http_host,
        "script_name": path,
        "get_data": get_data,
        "post_data": post_data,
    }


def build_request_data_for_url(
    *,
    public_url: str,
    get_data: dict[str, str],
    post_data: dict[str, str],
) -> dict[str, Any]:
    """Build SAML request_data so get_self_url_no_query matches `public_url` (ACS or login path)."""
    parsed = urlparse(public_url)
    https_on = parsed.scheme == "https"
    host = parsed.netloc
    path = parsed.path or "/"
    return request_data_from_parsed_acs(
        https_on=https_on,
        http_host=host,
        path=path,
        get_data=get_data,
        post_data=post_data,
    )


def saml_auth_for_request(request_data: dict[str, Any]) -> OneLogin_Saml2_Auth:
    return OneLogin_Saml2_Auth(request_data, old_settings=build_saml_settings())


def acs_public_url() -> str:
    return os.getenv(
        "SAML_SP_ACS_URL",
        "https://nano-chat.su.domains/auth/saml/callback",
    ).strip()


def saml_login_public_url() -> str:
    p = urlparse(acs_public_url())
    if not p.scheme or not p.netloc:
        raise RuntimeError("SAML_SP_ACS_URL must include scheme and host")
    return f"{p.scheme}://{p.netloc}/auth/saml/login"


def primary_email_from_saml(
    attributes: dict[str, list[str]], nameid: str | None
) -> str | None:
    candidate_keys = (
        "mail",
        "email",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "urn:mace:dir:attribute-def:mail",
        "urn:oid:0.9.2342.19200300.100.1.3",
    )
    for key in candidate_keys:
        vals = attributes.get(key)
        if vals:
            v = vals[0] if isinstance(vals, list) else vals
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
    if nameid and "@" in nameid:
        return nameid.strip().lower()
    return None


def sunet_from_saml(
    attributes: dict[str, list[str]], nameid: str | None, email: str | None
) -> str | None:
    for key in (
        "uid",
        "sAMAccountName",
        "urn:mace:dir:attribute-def:uid",
        "urn:oid:0.9.2342.19200300.100.1.1",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    ):
        vals = attributes.get(key)
        if vals:
            v = vals[0] if isinstance(vals, list) else vals
            if isinstance(v, str) and v.strip():
                return v.strip().split("@", 1)[0]
    if nameid and "@" in nameid:
        return nameid.strip().split("@", 1)[0]
    if email and "@" in email:
        return email.split("@", 1)[0]
    return None
