"""
Cliente HTTP pra API do Mindsight -- mesma logica de autenticacao usada na
Automacao de envio de e-mail de AVE (outro repositorio): login via
username/senha no endpoint /api/token/, aplicado tanto como header
Authorization quanto como cookie (a API valida os dois).

Credenciais vem de st.secrets quando rodando dentro do Streamlit; cai pra
variavel de ambiente se streamlit nao estiver disponivel (ex: script solto
de debug), pra este modulo nao depender de Streamlit pra ser testado.
"""

from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_USER_AGENT = "Mozilla/5.0"


def _get_credentials() -> tuple[str, str]:
    try:
        import streamlit as st
        return st.secrets["mindsight"]["username"], st.secrets["mindsight"]["password"]
    except Exception:
        import os
        return os.environ["MINDSIGHT_USERNAME"], os.environ["MINDSIGHT_PASSWORD"]


def authenticate(auth_url: str, tenant: str) -> dict:
    """Login na API interna -- devolve {'access':..., 'refresh':...}."""
    username, password = _get_credentials()
    resp = requests.post(
        auth_url,
        data={"username": username, "password": password, "tenant": tenant},
        headers={"User-Agent": DEFAULT_USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def apply_auth(session: requests.Session, tokens: dict) -> None:
    session.headers.update({
        "Authorization": f"Token {tokens['access']}",
        "User-Agent": DEFAULT_USER_AGENT,
    })
    session.cookies.set("access_token", tokens["access"])
    if tokens.get("refresh"):
        session.cookies.set("refresh_token", tokens["refresh"])


@dataclass
class ApiSession:
    session: requests.Session
    auth_url: str
    tenant: str


def make_session(auth_url: str, tenant: str) -> ApiSession:
    session = requests.Session()
    apply_auth(session, authenticate(auth_url, tenant))
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return ApiSession(session=session, auth_url=auth_url, tenant=tenant)


def get_with_reauth(api_session: ApiSession, url: str) -> requests.Response:
    """GET que refaz o login 1x se a sessao tiver expirado.

    Trata dois sintomas de sessao expirada: status 401 (comum), e loop de
    redirecionamento (TooManyRedirects) -- alguns endpoints redirecionam pra
    uma tela de login em vez de responder 401 quando o token nao e mais
    valido, o que o requests enxerga como "redirecionado demais" em vez de
    um status de erro claro."""
    try:
        resp = api_session.session.get(url, timeout=30)
    except requests.exceptions.TooManyRedirects:
        apply_auth(api_session.session, authenticate(api_session.auth_url, api_session.tenant))
        resp = api_session.session.get(url, timeout=30)
    else:
        if resp.status_code == 401:
            apply_auth(api_session.session, authenticate(api_session.auth_url, api_session.tenant))
            resp = api_session.session.get(url, timeout=30)
    resp.raise_for_status()
    return resp


def fetch_all_pages(api_session: ApiSession, url: str) -> list[dict]:
    """Pagina um endpoint DRF padrao (count/next/previous/results) e devolve
    todos os 'results' concatenados."""
    rows: list[dict] = []
    while url:
        data = get_with_reauth(api_session, url).json()
        rows.extend(data["results"])
        url = data.get("next")
    return rows