"""Optional "Prepared by" details on client reports, read from environment variables (.env).

They live in your own .env, not in this public repo, so each user's reports show their own details.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Branding:
    name: str
    title: str = ""
    email: str = ""
    linkedin_url: str = ""


def load_branding(env: Mapping[str, str] = os.environ) -> Branding | None:
    """None unless CWF_PREPARED_BY is set. Only https:// LinkedIn links are used."""
    name = _value(env, "CWF_PREPARED_BY")
    if not name:
        return None
    linkedin = _value(env, "CWF_LINKEDIN_URL")
    return Branding(
        name=name,
        title=_value(env, "CWF_PREPARED_BY_TITLE"),
        email=_value(env, "CWF_CONTACT_EMAIL"),
        linkedin_url=linkedin if linkedin.startswith("https://") else "",
    )


def _value(env: Mapping[str, str], key: str) -> str:
    """Trimmed value without surrounding quotes (docker --env-file keeps quotes from .env)."""
    value = env.get(key, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value
