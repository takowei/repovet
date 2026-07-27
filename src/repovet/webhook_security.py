"""Verify a GitHub webhook's `X-Hub-Signature-256` header.

GitHub signs every webhook delivery with the app's webhook secret (HMAC
SHA-256 over the raw request body). This is the one gate between "runs
arbitrary code because someone POSTed to our endpoint" and "only ever acts on
deliveries GitHub actually sent" -- every caller of `app_webhook.handle_event`
must go through `verify_signature` first.
"""

import hmac


def verify_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    """Return True iff `signature_header` (the raw `X-Hub-Signature-256`
    value, e.g. 'sha256=abcd...') matches HMAC-SHA256(secret, payload).

    Missing header, malformed header, or empty secret all fail closed
    (return False) rather than raising -- callers should treat any False as
    "reject the request", not "not applicable".
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, "sha256").hexdigest()
    provided = signature_header[len("sha256=") :]
    return hmac.compare_digest(expected, provided)
