"""GitHub App authentication: sign a short-lived app JWT, then exchange it
for a per-installation access token.

Never reads the private key from a file path baked into source -- callers
must pass the PEM contents (typically sourced from an env var by the
process entry point, e.g. `REPOVET_APP_PRIVATE_KEY`). This module never
persists a key or token anywhere.
"""

import time

import jwt

from repovet.errors import NetworkError
from repovet.github_client import GitHubClient

JWT_TTL_SECONDS = 540  # GitHub allows at most 10 minutes; stay under with margin


def create_app_jwt(app_id: str, private_key_pem: str, now: int | None = None) -> str:
    """Build the RS256 JWT a GitHub App uses to authenticate as itself
    (not as an installation) -- required to mint installation tokens."""
    issued_at = now if now is not None else int(time.time())
    payload = {
        "iat": issued_at - 60,  # allow for clock drift
        "exp": issued_at + JWT_TTL_SECONDS,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def get_installation_token(rest_client: GitHubClient, installation_id: int) -> str:
    """Exchange an app-JWT-authenticated `rest_client` for a scoped
    installation access token (valid ~1 hour, used for all subsequent API
    calls made on that installation's behalf)."""
    response = rest_client.post(f"/app/installations/{installation_id}/access_tokens", {})
    token = response.get("token")
    if not token:
        raise NetworkError(f"no token in installation access_tokens response: {response}")
    return token
