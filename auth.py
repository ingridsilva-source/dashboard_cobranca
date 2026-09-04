"""
Proteção simples por senha.

Serve pra publicar o app como "público" no Streamlit Community Cloud
(sem gastar a única vaga de app privado da conta) mantendo os dados
protegidos: ninguém vê nada do dashboard sem digitar a senha certa,
configurada em st.secrets["APP_PASSWORD"].
"""

import hmac
import os

import streamlit as st


def _senha_configurada():
    """Lê APP_PASSWORD dos Secrets do Streamlit (nuvem) ou de uma
    variável de ambiente (uso local, sem precisar de secrets.toml)."""
    try:
        if "APP_PASSWORD" in st.secrets:
            return str(st.secrets["APP_PASSWORD"])
    except Exception:
        pass
    return os.getenv("APP_PASSWORD")


def check_password() -> bool:
    """Mostra uma tela de login simples. Devolve True só depois que a
    senha certa for digitada (fica lembrada pelo resto da sessão do
    navegador)."""

    if st.session_state.get("password_correct", False):
        return True

    senha_configurada = _senha_configurada()
    if not senha_configurada:
        st.error(
            "Este app ainda não tem uma senha de acesso configurada. "
            "Defina o segredo APP_PASSWORD nas configurações do app "
            "(Settings → Secrets) antes de compartilhar o link. Veja o README."
        )
        st.stop()
        return False

    def _senha_digitada():
        digitada = st.session_state.get("password", "")
        if hmac.compare_digest(digitada, senha_configurada):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    st.title("🔒 Dashboard — Carteira de Cobrança")
    st.text_input(
        "Senha de acesso",
        type="password",
        on_change=_senha_digitada,
        key="password",
    )
    if st.session_state.get("password_correct") is False:
        st.error("Senha incorreta.")
    return False
