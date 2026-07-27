import hmac

from repovet.webhook_security import verify_signature


def sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, "sha256").hexdigest()


def test_verify_signature_accepts_correct_signature():
    payload = b'{"hello": "world"}'
    header = sign("my-secret", payload)
    assert verify_signature("my-secret", payload, header) is True


def test_verify_signature_rejects_wrong_secret():
    payload = b'{"hello": "world"}'
    header = sign("wrong-secret", payload)
    assert verify_signature("my-secret", payload, header) is False


def test_verify_signature_rejects_tampered_payload():
    payload = b'{"hello": "world"}'
    header = sign("my-secret", payload)
    assert verify_signature("my-secret", b'{"hello": "mallory"}', header) is False


def test_verify_signature_fails_closed_on_missing_header():
    assert verify_signature("my-secret", b"payload", None) is False
    assert verify_signature("my-secret", b"payload", "") is False


def test_verify_signature_fails_closed_on_missing_secret():
    payload = b"payload"
    header = sign("some-secret", payload)
    assert verify_signature("", payload, header) is False


def test_verify_signature_rejects_wrong_prefix():
    payload = b"payload"
    digest = hmac.new(b"my-secret", payload, "sha256").hexdigest()
    assert verify_signature("my-secret", payload, f"sha1={digest}") is False
