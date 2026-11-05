"""OAuth oficial; códigos e tokens permanecem apenas na memória da sessão."""
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

AUTH_ENDPOINT = "https://auth.mercadolivre.com.br/authorization"
TOKEN_ENDPOINT = "https://api.mercadolibre.com/oauth/token"


class AuthorizationError(RuntimeError):
    """Mensagem controlada, sem respostas remotas ou credenciais."""


def token_rejection(response: httpx.Response, grant_type: str) -> AuthorizationError:
    # Somente códigos conhecidos e textos locais chegam à interface. Nunca exibir
    # message/error_description remotos: podem conter códigos, tokens ou segredo.
    descriptions = {
        "invalid_client": "A aplicação não foi autenticada. Copie novamente o App ID e o Client Secret do MESMO cadastro no portal; depois gere uma nova autorização.",
        "unauthorized_client": "A aplicação não tem autorização para esse fluxo. Confira Authorization Code e a situação da aplicação no portal.",
        "invalid_grant": "O código de autorização foi recusado. Ele pode estar vencido, já utilizado ou não corresponder ao retorno/PKCE desta tentativa. Gere uma nova autorização, copie o retorno e conclua uma única vez, sem gerar outro link no meio.",
        "invalid_request": "A API recusou os dados da solicitação. Confira o retorno cadastrado e o PKCE da aplicação; gere uma nova autorização.",
        "invalid_scope": "A API recusou as permissões solicitadas. Confira as permissões da aplicação no portal.",
        "unsupported_grant_type": "A API recusou o fluxo de autenticação. Confira Authorization Code no cadastro da aplicação.",
        "access_denied": "O Mercado Livre negou o acesso. Confira a conta usada e as permissões/situação da aplicação no portal.",
        "forbidden": "O Mercado Livre bloqueou o acesso à troca de token. Confira a conta e as permissões/situação da aplicação no portal.",
        "PA_UNAUTHORIZED_RESULT_FROM_POLICIES": "A troca de token foi bloqueada pelas políticas do Mercado Livre. Confira a situação da aplicação e as permissões da conta no portal.",
    }
    data = {}
    try:
        if len(response.content) <= 65536:
            body = response.json()
            if isinstance(body, dict):
                data = body
    except ValueError:
        pass
    error = next((value for key in ("error", "code")
                  if isinstance(value := data.get(key), str) and value in descriptions), None)
    operation = "renovação do token" if grant_type == "refresh_token" else "troca do código por token"
    prefix = f"Mercado Livre recusou a {operation} (HTTP {response.status_code}"
    prefix += f"; {error}). " if error else "). "
    if error == "invalid_grant" and grant_type == "refresh_token":
        return AuthorizationError(prefix + "A renovação foi recusada. Conecte a conta novamente para obter uma nova autorização.")
    if error:
        return AuthorizationError(prefix + descriptions[error])
    if response.status_code == 429:
        return AuthorizationError(prefix + "Limite de autorizações atingido. Aguarde antes de gerar outra autorização.")
    if response.status_code >= 500:
        return AuthorizationError(prefix + "O serviço está indisponível. Aguarde e gere uma nova autorização.")
    if response.status_code == 401:
        return AuthorizationError(prefix + "A API não autenticou a solicitação. Confira App ID e Client Secret da mesma aplicação.")
    if response.status_code == 403:
        return AuthorizationError(prefix + "Acesso negado. Confira as permissões e a situação da aplicação/conta no portal.")
    return AuthorizationError(prefix + "A API não informou um motivo reconhecido. Confira o cadastro da aplicação e gere uma nova autorização.")


def validate_redirect_uri(uri: str) -> str:
    uri = uri.strip()
    try:
        parsed = urlsplit(uri)
        _ = parsed.port  # Valida portas malformadas; não consulta o endereço.
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment
                or any(char.isspace() for char in uri)):
            raise ValueError
    except ValueError:
        raise AuthorizationError("Informe um retorno HTTPS aceito pelo Mercado Livre, sem usuário, senha, parâmetros ou fragmento. O retorno HTTP local foi recusado pelo portal.") from None
    return uri


@dataclass
class AuthorizationAttempt:
    client_id: str
    redirect_uri: str
    state: str = field(repr=False)
    verifier: str = field(repr=False)
    created_at: float
    pkce: bool = True
    used: bool = False


@dataclass
class Tokens:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_at: float


class MercadoLivreOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, *,
                 pkce: bool = True, client=None, clock=time.time):
        if not client_id.strip() or not client_id.strip().isascii() or not client_id.strip().isdigit():
            raise AuthorizationError("Informe o App ID numérico da sua aplicação do Mercado Livre.")
        if not client_secret.strip():
            raise AuthorizationError("Informe o Client Secret no campo protegido do programa.")
        self.client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self.redirect_uri = validate_redirect_uri(redirect_uri)
        self.pkce = pkce
        self.clock = clock
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def begin(self) -> tuple[AuthorizationAttempt, str]:
        attempt = AuthorizationAttempt(self.client_id, self.redirect_uri,
            secrets.token_urlsafe(32), secrets.token_urlsafe(64), self.clock(), pkce=self.pkce)
        params = {"response_type": "code", "client_id": self.client_id,
                  "redirect_uri": self.redirect_uri, "state": attempt.state}
        if self.pkce:
            challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
            params.update(code_challenge=challenge, code_challenge_method="S256")
        return attempt, AUTH_ENDPOINT + "?" + urlencode(params)

    def finish(self, attempt: AuthorizationAttempt, returned_url: str) -> Tokens:
        if attempt.used:
            raise AuthorizationError("Essa tentativa já foi utilizada. Clique em gerar nova autorização.")
        if self.clock() - attempt.created_at > 600 or self.clock() < attempt.created_at:
            raise AuthorizationError("A autorização expirou. Gere uma nova autorização e tente novamente.")
        if attempt.client_id != self.client_id or attempt.redirect_uri != self.redirect_uri or attempt.pkce != self.pkce:
            raise AuthorizationError("As configurações mudaram. Gere uma nova autorização.")
        try:
            parsed = urlsplit(returned_url.strip())
            expected = urlsplit(attempt.redirect_uri)
            actual_target = (parsed.scheme, parsed.hostname, parsed.port or 443, parsed.path or "/")
            expected_target = (expected.scheme, expected.hostname, expected.port or 443, expected.path or "/")
            if actual_target != expected_target or parsed.fragment or parsed.username or parsed.password:
                raise ValueError
            params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)
            states = params.get("state", [])
            if len(states) != 1 or not secrets.compare_digest(states[0], attempt.state):
                raise ValueError
        except (ValueError, TypeError):
            raise AuthorizationError("O endereço de retorno não corresponde a esta tentativa. Volte ao link de autorização gerado nesta sessão.") from None
        if "error" in params:
            attempt.used = True
            raise AuthorizationError("A autorização foi cancelada ou recusada no Mercado Livre.")
        codes = params.get("code", [])
        if len(codes) != 1 or not codes[0] or len(codes[0]) > 4096:
            raise AuthorizationError("O endereço de retorno precisa conter o código recebido do Mercado Livre.")
        # Não repetir uma troca ambígua: códigos são de uso único.
        attempt.used = True
        payload = {"grant_type": "authorization_code", "client_id": self.client_id,
                   "client_secret": self._client_secret, "redirect_uri": self.redirect_uri, "code": codes[0]}
        if attempt.pkce:
            payload["code_verifier"] = attempt.verifier
        return self._tokens(payload)

    def refresh(self, tokens: Tokens) -> Tokens:
        if not tokens.refresh_token:
            raise AuthorizationError("Esta conexão não permite renovação. Autorize novamente no Mercado Livre.")
        result = self._tokens({"grant_type": "refresh_token", "client_id": self.client_id,
                               "client_secret": self._client_secret, "refresh_token": tokens.refresh_token})
        if not result.refresh_token:
            result.refresh_token = tokens.refresh_token
        return result

    def _tokens(self, payload: dict) -> Tokens:
        try:
            response = self.client.post(TOKEN_ENDPOINT, data=payload)
            if not response.is_success:
                raise token_rejection(response, payload["grant_type"])
            response.raise_for_status()
            data = response.json()
            access = data.get("access_token")
            refresh = data.get("refresh_token")
            duration = data.get("expires_in")
            if (not isinstance(access, str) or not access or not isinstance(duration, int)
                    or isinstance(duration, bool) or duration <= 0
                    or (refresh is not None and (not isinstance(refresh, str) or not refresh))
                    or str(data.get("token_type", "")).lower() != "bearer"):
                raise AuthorizationError("Mercado Livre retornou uma conexão incompleta. Gere uma nova autorização.")
            return Tokens(access, refresh, self.clock() + duration)
        except (httpx.HTTPError, ValueError, AttributeError):
            raise AuthorizationError("Não foi possível concluir a conexão com o Mercado Livre. Confira a rede e gere uma nova autorização.") from None

    def close(self):
        self.client.close()
