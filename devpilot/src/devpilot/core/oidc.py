"""OIDC discovery, Authorization Code + PKCE exchange and ID-token validation."""
import base64
import hashlib
import secrets
from functools import lru_cache
from urllib.parse import urlencode
import httpx
import jwt
from devpilot.config import AppSettings


@lru_cache(maxsize=8)
def discovery(issuer: str) -> dict:
    response = httpx.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=10)
    response.raise_for_status()
    return response.json()


def authorization_request(settings: AppSettings) -> tuple[str, str, str, str]:
    metadata = discovery(settings.oidc_issuer)
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urlencode({"response_type": "code", "client_id": settings.oidc_client_id, "redirect_uri": settings.oidc_redirect_uri, "scope": "openid profile email groups", "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"})
    return f"{metadata['authorization_endpoint']}?{query}", state, nonce, verifier


def exchange_and_validate(settings: AppSettings, code: str, verifier: str, nonce: str) -> dict:
    metadata = discovery(settings.oidc_issuer)
    response = httpx.post(metadata["token_endpoint"], data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.oidc_redirect_uri, "client_id": settings.oidc_client_id, "client_secret": settings.oidc_client_secret.get_secret_value(), "code_verifier": verifier}, timeout=15)
    response.raise_for_status()
    id_token = response.json().get("id_token")
    if not id_token: raise ValueError("OIDC token response did not include id_token")
    signing_key = jwt.PyJWKClient(metadata["jwks_uri"]).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(id_token, signing_key.key, algorithms=["RS256", "ES256"], audience=settings.oidc_client_id, issuer=settings.oidc_issuer, options={"require": ["exp", "iat", "sub"]})
    if claims.get("nonce") != nonce: raise ValueError("OIDC nonce mismatch")
    return claims
