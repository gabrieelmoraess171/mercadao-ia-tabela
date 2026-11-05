import base64
import hashlib
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from services.mercadolivre_auth import (
    AUTH_ENDPOINT, TOKEN_ENDPOINT, AuthorizationError, MercadoLivreOAuth, Tokens, validate_redirect_uri,
)

REDIRECT = "https://retorno.example.test/mercadolivre"


def service(handler, *, pkce=True, clock=lambda: 1000):
    return MercadoLivreOAuth("123456", "test-secret", REDIRECT, pkce=pkce,
        client=httpx.Client(transport=httpx.MockTransport(handler)), clock=clock)


def returned(attempt, **overrides):
    params = {"code": "test-code", "state": attempt.state}
    params.update(overrides)
    return REDIRECT + "?" + urlencode(params)


def success(request):
    return httpx.Response(200, json={"access_token": "test-access", "refresh_token": "test-refresh",
                                    "token_type": "bearer", "expires_in": 21600})


def test_authorization_url_state_pkce_and_single_use_exchange():
    seen = []
    def handle(request):
        seen.append(request)
        assert str(request.url) == TOKEN_ENDPOINT
        assert request.method == "POST"
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["authorization_code"]
        assert form["client_secret"] == ["test-secret"]
        assert form["redirect_uri"] == [REDIRECT]
        assert form["code_verifier"] == [attempt.verifier]
        return success(request)
    oauth = service(handle)
    attempt, link = oauth.begin()
    parsed = urlsplit(link)
    assert parsed.scheme + "://" + parsed.netloc + parsed.path == AUTH_ENDPOINT
    params = parse_qs(parsed.query)
    assert params["state"] == [attempt.state]
    assert params["redirect_uri"] == [REDIRECT]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).rstrip(b"=").decode()
    assert params["code_challenge"] == [challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert attempt.verifier not in link and "test-secret" not in link
    tokens = oauth.finish(attempt, returned(attempt))
    assert tokens.access_token == "test-access" and tokens.expires_at == 22600
    assert "test-access" not in repr(tokens) and "test-refresh" not in repr(tokens)
    assert attempt.state not in repr(attempt) and attempt.verifier not in repr(attempt)
    with pytest.raises(AuthorizationError, match="já foi utilizada"):
        oauth.finish(attempt, returned(attempt))
    assert len(seen) == 1


@pytest.mark.parametrize("url", ["http://192.168.1.10:8765", "http://site.test/retorno", "https://user:secret@site.test/retorno",
    "https://site.test/?code=x", "https://site.test/#code=x", "https://site.test:bad/", "https://", "https://site. test/"])
def test_invalid_registered_redirect_rejected(url):
    with pytest.raises(AuthorizationError):
        validate_redirect_uri(url)


@pytest.mark.parametrize("mutation", ["state", "missing-state", "duplicate-state", "other-domain", "other-path", "fragment", "missing-code", "duplicate-code"])
def test_bad_callback_never_contacts_token_endpoint(mutation):
    oauth = service(lambda r: pytest.fail("Não trocar um código de retorno inválido"))
    attempt, _ = oauth.begin()
    callback = returned(attempt)
    if mutation == "state": callback = returned(attempt, state="other")
    if mutation == "missing-state": callback = REDIRECT + "?code=x"
    if mutation == "duplicate-state": callback += "&state=" + attempt.state
    if mutation == "other-domain": callback = callback.replace("retorno.example.test", "other.test")
    if mutation == "other-path": callback = callback.replace("/mercadolivre", "/other")
    if mutation == "fragment": callback += "#code=other"
    if mutation == "missing-code": callback = REDIRECT + "?state=" + attempt.state
    if mutation == "duplicate-code": callback += "&code=other"
    with pytest.raises(AuthorizationError):
        oauth.finish(attempt, callback)
    assert not attempt.used


def test_expiry_and_configuration_change_require_new_attempt():
    now = [1000]
    oauth = service(lambda r: pytest.fail("Não usar tentativa expirada"), clock=lambda: now[0])
    attempt, _ = oauth.begin()
    now[0] = 1601
    with pytest.raises(AuthorizationError, match="expirou"):
        oauth.finish(attempt, returned(attempt))
    now[0] = 1000
    oauth.client_id = "987654"
    with pytest.raises(AuthorizationError, match="configurações mudaram"):
        oauth.finish(attempt, returned(attempt))


def test_denied_authorization_does_not_exchange_code():
    oauth = service(lambda r: pytest.fail("Não trocar autorização recusada"))
    attempt, _ = oauth.begin()
    with pytest.raises(AuthorizationError, match="cancelada ou recusada"):
        oauth.finish(attempt, REDIRECT + "?" + urlencode({"error": "access_denied", "state": attempt.state}))
    assert attempt.used


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 302])
def test_remote_failure_redacted_and_code_not_reused(status):
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(status, text="test-secret private-response test-code")
    oauth = service(handle)
    attempt, _ = oauth.begin()
    with pytest.raises(AuthorizationError) as error:
        oauth.finish(attempt, returned(attempt))
    assert all(secret not in str(error.value) for secret in ("test-secret", "private-response", "test-code"))
    assert attempt.used and len(seen) == 1


def test_no_pkce_when_disabled_in_application_registration():
    forms = []
    def handle(request):
        forms.append(parse_qs(request.content.decode()))
        return success(request)
    oauth = service(handle, pkce=False)
    attempt, link = oauth.begin()
    assert "code_challenge" not in parse_qs(urlsplit(link).query)
    oauth.finish(attempt, returned(attempt))
    assert "code_verifier" not in forms[0]


def test_refresh_rotates_token_and_uses_official_endpoint():
    def handle(request):
        assert str(request.url) == TOKEN_ENDPOINT
        assert parse_qs(request.content.decode())["grant_type"] == ["refresh_token"]
        return httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh",
                                        "expires_in": 21600, "token_type": "Bearer"})
    tokens = service(handle).refresh(Tokens("old-access", "old-refresh", 900))
    assert tokens.access_token == "new-access" and tokens.refresh_token == "new-refresh"


@pytest.mark.parametrize("payload", [[], {}, {"access_token": "x", "token_type": "bearer", "expires_in": -1},
    {"access_token": "x", "token_type": "bearer", "expires_in": True},
    {"access_token": "x", "token_type": "invalid", "expires_in": 21600}])
def test_malformed_tokens_are_not_accepted(payload):
    oauth = service(lambda r: httpx.Response(200, json=payload))
    attempt, _ = oauth.begin()
    with pytest.raises(AuthorizationError):
        oauth.finish(attempt, returned(attempt))


def test_root_callback_handles_browser_trailing_slash_and_default_port():
    oauth = MercadoLivreOAuth("123456", "test-secret", "https://retorno.example.test",
        client=httpx.Client(transport=httpx.MockTransport(success)))
    attempt, _ = oauth.begin()
    callback = "https://retorno.example.test:443/?" + urlencode({"code": "test-code", "state": attempt.state})
    assert oauth.finish(attempt, callback).access_token == "test-access"


def test_local_http_redirect_is_rejected_after_portal_refusal():
    for invalid in ("http://127.0.0.1:8765/mercadolivre/callback", "http://localhost:8765/mercadolivre/callback", "http://0.0.0.0:8765/callback"):
        with pytest.raises(AuthorizationError):
            validate_redirect_uri(invalid)


@pytest.mark.parametrize("status,code,expected", [
    (401, "invalid_client", "MESMO cadastro"),
    (400, "invalid_grant", "não corresponder ao retorno/PKCE"),
    (400, "invalid_request", "dados da solicitação"),
    (403, "unauthorized_client", "Authorization Code"),
    (403, "forbidden", "bloqueou o acesso"),
    (403, "PA_UNAUTHORIZED_RESULT_FROM_POLICIES", "políticas"),
    (400, "invalid_scope", "permissões"),
])
def test_oauth_reason_is_specific_without_exposing_remote_details(status, code, expected):
    oauth = service(lambda r: httpx.Response(status, json={"error": code,
        "message": "test-secret test-code PRIVATE", "error_description": "test-access test-refresh"}))
    attempt, _ = oauth.begin()
    with pytest.raises(AuthorizationError) as error:
        oauth.finish(attempt, returned(attempt))
    text = str(error.value)
    assert f"HTTP {status}" in text and code in text and expected in text
    assert all(value not in text for value in ("test-secret", "test-code", "PRIVATE", "test-access", "test-refresh"))
    assert attempt.used


@pytest.mark.parametrize("body", [[], {"error": ["invalid_client"]}, {"error": {"private": "test-secret"}},
    {"error": "test-secret"}, {"error": "invalid_client test-secret"}])
def test_unknown_or_malformed_error_never_leaks_content(body):
    oauth = service(lambda r: httpx.Response(400, json=body))
    attempt, _ = oauth.begin()
    with pytest.raises(AuthorizationError) as error:
        oauth.finish(attempt, returned(attempt))
    assert "HTTP 400" in str(error.value) and "test-secret" not in str(error.value)


def test_refresh_error_is_not_reported_as_an_authorization_code_error():
    oauth = service(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(AuthorizationError) as error:
        oauth.refresh(Tokens("test-access", "test-refresh", 900))
    assert "renovação" in str(error.value) and "invalid_grant" in str(error.value)
