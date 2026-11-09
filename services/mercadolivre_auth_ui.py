"""Conexão opcional ao Mercado Livre, sem login próprio ou armazenamento de tokens."""
import os
import time

import streamlit as st

from .mercadolivre_auth import AuthorizationError, MercadoLivreOAuth


def _oauth():
    return MercadoLivreOAuth(st.session_state.get("meli_client_id", ""),
        st.session_state.get("meli_client_secret", ""), st.session_state.get("meli_redirect_uri", ""),
        pkce=st.session_state.get("meli_pkce", True))


def _clear_connection():
    for key in ("meli_tokens", "meli_attempt", "meli_authorization_url", "meli_returned_url"):
        st.session_state.pop(key, None)


def _begin():
    oauth = None
    try:
        oauth = _oauth()
        attempt, url = oauth.begin()
        # Uma nova autorização pode ser para outra conta. Não continuar usando
        # a conexão anterior se esta tentativa for cancelada ou recusada.
        st.session_state.pop("meli_tokens", None)
        st.session_state.pop("meli_attempt", None)
        st.session_state.pop("meli_authorization_url", None)
        st.session_state["meli_attempt"] = attempt
        st.session_state["meli_authorization_url"] = url
        st.session_state.pop("meli_returned_url", None)
        st.session_state["meli_auth_notice"] = ("info", "Abra o link, autorize e conclua o retorno nesta mesma aba do programa. A tentativa vale por 10 minutos. Não gere outro link durante essa tentativa.")
    except AuthorizationError as exc:
        st.session_state["meli_auth_notice"] = ("error", str(exc))
    finally:
        if oauth:
            oauth.close()


def _finish():
    oauth = None
    try:
        attempt = st.session_state.get("meli_attempt")
        if attempt is None:
            raise AuthorizationError("Gere uma autorização nesta sessão antes de colar o retorno.")
        oauth = _oauth()
        received = st.session_state.get("meli_returned_url", "")
        tokens = oauth.finish(attempt, received)
        st.session_state["meli_tokens"] = tokens
        st.session_state.pop("meli_attempt", None)
        st.session_state.pop("meli_authorization_url", None)
        st.session_state["meli_auth_notice"] = ("success", "Conta conectada nesta sessão. A consulta de anúncios ainda depende das permissões do Mercado Livre.")
    except AuthorizationError as exc:
        st.session_state["meli_auth_notice"] = ("error", str(exc))
    finally:
        attempt = st.session_state.get("meli_attempt")
        if attempt is not None and attempt.used:
            st.session_state.pop("meli_attempt", None)
            st.session_state.pop("meli_authorization_url", None)
        st.session_state.pop("meli_returned_url", None)
        if oauth:
            oauth.close()


def connection_ui():
    with st.expander("Conectar conta do Mercado Livre"):
        st.caption("Conexão opcional para obter e renovar o token. Use uma aplicação cadastrada no portal de desenvolvedores; não envie o Client Secret no chat.")
        st.text_input("App ID do Mercado Livre", value=os.getenv("MELI_CLIENT_ID", ""), key="meli_client_id", on_change=_clear_connection)
        st.text_input("Client Secret do Mercado Livre", value=os.getenv("MELI_CLIENT_SECRET", ""), type="password", key="meli_client_secret", on_change=_clear_connection)
        st.text_input("URL de retorno cadastrada no Mercado Livre", value=os.getenv("MELI_REDIRECT_URI", ""), key="meli_redirect_uri", on_change=_clear_connection,
            help="Informe a URL HTTPS real da sua página de retorno, depois de publicada e aceita no cadastro. Não use um endereço inventado ou um site de terceiros.")
        st.caption("O retorno HTTP local foi recusado pelo portal. A conexão precisa de uma página HTTPS de retorno; programa e fotos continuam no computador.")
        st.caption("No portal, clique em Adicionar URI de redirect e salve a aplicação. O endereço deve ficar na lista cadastrada, exatamente igual ao campo acima.")
        st.checkbox("Usar PKCE (ative também no cadastro da aplicação)", value=True, key="meli_pkce", on_change=_clear_connection)
        st.button("Gerar autorização do Mercado Livre", on_click=_begin)
        url = st.session_state.get("meli_authorization_url")
        if url:
            st.link_button("Autorizar no site do Mercado Livre", url)
            st.caption("Depois de autorizar, use o botão Copiar retorno na página de retorno e cole abaixo. "
                "Se a página não oferecer o botão, copie o endereço completo recebido. A conexão será concluída no programa.")
            st.text_input("Endereço completo recebido após autorizar", type="password", key="meli_returned_url")
            st.button("Concluir conexão do Mercado Livre", on_click=_finish)
        notice = st.session_state.pop("meli_auth_notice", None)
        if notice:
            getattr(st, notice[0])(notice[1])
        tokens = st.session_state.get("meli_tokens")
        if tokens:
            remaining = max(0, int((tokens.expires_at - time.time()) / 60))
            st.success(f"Conexão disponível nesta sessão · validade aproximada: {remaining} minutos.")
            st.caption("A renovação é automática ao pesquisar, quando houver permissão. Tokens ficam apenas na memória e são perdidos ao encerrar a sessão.")
            st.button("Desconectar Mercado Livre deste programa", on_click=_clear_connection)


def access_token(fallback: str = "") -> str:
    tokens = st.session_state.get("meli_tokens")
    if not tokens:
        return fallback
    if tokens.expires_at > time.time() + 60:
        return tokens.access_token
    oauth = None
    try:
        oauth = _oauth()
        renewed = oauth.refresh(tokens)
        st.session_state["meli_tokens"] = renewed
        return renewed.access_token
    except AuthorizationError as exc:
        st.session_state.pop("meli_tokens", None)
        raise AuthorizationError("A conexão expirou e não pôde ser renovada. " + str(exc)) from None
    finally:
        if oauth:
            oauth.close()
