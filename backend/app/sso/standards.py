"""OIDC Code + PKCE and strict XML Signature SAML using vetted protocol libraries."""
import base64
import hashlib
from urllib.parse import urlsplit
import httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.oidc.core import CodeIDToken
from joserfc import jwt
from joserfc.jwk import KeySet
from app.core.config import settings
from app.security.jwt import InvalidTokenError
from app.sso.service import issue_local_token


def _metadata():
    issuer = settings.oidc_issuer.rstrip("/")
    if not issuer.startswith("https://"):
        raise InvalidTokenError("OIDC requires HTTPS")
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.get(issuer + "/.well-known/openid-configuration")
        response.raise_for_status()
        if len(response.content) > 65536:
            raise InvalidTokenError("invalid OIDC metadata")
        metadata = response.json()
    if metadata.get("issuer") != settings.oidc_issuer:
        raise InvalidTokenError("OIDC issuer mismatch")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        value = urlsplit(metadata.get(field, ""))
        if value.scheme != "https" or value.username or value.password or value.hostname != urlsplit(issuer).hostname:
            raise InvalidTokenError("untrusted OIDC endpoint")
    return metadata


def oidc_url(state, nonce, verifier):
    metadata = _metadata()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with OAuth2Client(settings.oidc_client_id, settings.oidc_client_secret,
                      scope="openid profile email", redirect_uri=settings.oidc_redirect_uri) as client:
        url, _ = client.create_authorization_url(metadata["authorization_endpoint"], state=state,
            nonce=nonce, response_type="code", code_challenge=challenge, code_challenge_method="S256")
    return url


def oidc_exchange(db, code, nonce, verifier, org_id):
    metadata = _metadata()
    with OAuth2Client(settings.oidc_client_id, settings.oidc_client_secret,
                     redirect_uri=settings.oidc_redirect_uri, timeout=10, follow_redirects=False) as client:
        token = client.fetch_token(metadata["token_endpoint"], code=code, code_verifier=verifier, grant_type="authorization_code")
    with httpx.Client(timeout=10, follow_redirects=False) as key_client:
        response = key_client.get(metadata["jwks_uri"])
        response.raise_for_status()
        if len(response.content) > 65536:
            raise InvalidTokenError("invalid OIDC keys")
        decoded = jwt.decode(token["id_token"], KeySet.import_key_set(response.json()), algorithms=["RS256", "ES256"])
    claims = CodeIDToken(decoded.claims, decoded.header, options={
        "iss": {"essential": True, "value": settings.oidc_issuer},
        "aud": {"essential": True, "value": settings.oidc_audience or settings.oidc_client_id},
    }, params={"nonce": nonce, "client_id": settings.oidc_client_id, "access_token": token.get("access_token")})
    claims.validate(leeway=30)
    if claims.get("nonce") != nonce:
        raise InvalidTokenError("OIDC nonce mismatch")
    email = claims.get("email") if claims.get("email_verified") is True else None
    return issue_local_token(db=db, org_id=org_id, subject=str(claims["sub"]), role="viewer", verified_email=email)


def saml_client(request, *, response=None):
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    if not settings.saml_idp_certificate or not settings.saml_idp_sso_url.startswith("https://"):
        raise InvalidTokenError("SAML certificate and HTTPS SSO endpoint required")
    acs = urlsplit(settings.saml_acs_url)
    data = {"https": "on" if acs.scheme == "https" else "off", "http_host": acs.netloc,
            "script_name": acs.path, "get_data": {}, "post_data": {"SAMLResponse": response} if response else {}}
    config = {"strict": True, "debug": False,
        "sp": {"entityId": settings.saml_entity_id, "assertionConsumerService": {"url": settings.saml_acs_url}},
        "idp": {"entityId": settings.saml_idp_issuer, "singleSignOnService": {"url": settings.saml_idp_sso_url}, "x509cert": settings.saml_idp_certificate},
        "security": {"wantAssertionsSigned": True, "wantMessagesSigned": True, "wantXMLValidation": True,
                     "rejectUnsolicitedResponsesWithInResponseTo": True, "rejectDeprecatedAlgorithm": True}}
    return OneLogin_Saml2_Auth(data, config)
