import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from repovet.app_auth import create_app_jwt, get_installation_token
from repovet.errors import NetworkError
from tests.conftest import FakeResponse, FakeSession, make_client


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def test_create_app_jwt_is_verifiable_and_has_expected_claims(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = create_app_jwt("app-123", private_pem, now=1_000_000)

    decoded = jwt.decode(
        token, public_pem, algorithms=["RS256"], options={"verify_exp": False, "verify_iat": False}
    )
    assert decoded["iss"] == "app-123"
    assert decoded["iat"] == 1_000_000 - 60
    assert decoded["exp"] == 1_000_000 + 540


def test_get_installation_token_returns_token(tmp_cache):
    session = FakeSession(
        [FakeResponse(201, {"token": "ghs_installation_token", "expires_at": "..."}, {})]
    )
    client = make_client(tmp_cache, [], token="app-jwt")
    client.session = session

    token = get_installation_token(client, installation_id=42)

    assert token == "ghs_installation_token"
    url, _ = session.calls[0]
    assert url == "https://api.github.com/app/installations/42/access_tokens"


def test_get_installation_token_raises_when_token_missing(tmp_cache):
    session = FakeSession([FakeResponse(201, {"unexpected": "shape"}, {})])
    client = make_client(tmp_cache, [], token="app-jwt")
    client.session = session

    with pytest.raises(NetworkError):
        get_installation_token(client, installation_id=42)
