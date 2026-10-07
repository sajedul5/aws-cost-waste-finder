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

    @property
    def linkedin_label(self) -> str:
        """ "linkedin.com/in/name" for display."""
        return self.linkedin_url.removeprefix("https://").removeprefix("www.").rstrip("/")


def load_branding(env: Mapping[str, str] = os.environ) -> Branding | None:
    """None unless CWF_PREPARED_BY is set. Only https:// LinkedIn links are used."""
    name = env.get("CWF_PREPARED_BY", "").strip()
    if not name:
        return None
    linkedin = env.get("CWF_LINKEDIN_URL", "").strip()
    return Branding(
        name=name,
        title=env.get("CWF_PREPARED_BY_TITLE", "").strip(),
        email=env.get("CWF_CONTACT_EMAIL", "").strip(),
        linkedin_url=linkedin if linkedin.startswith("https://") else "",
    )
