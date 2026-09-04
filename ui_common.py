"""
Pedaços de interface compartilhados entre as páginas do app (Dashboard e
Consulta de Inadimplência) — hoje só o botão de recarregar dados na
barra lateral.
"""

import streamlit as st


def botao_recarregar_dados():
    with st.sidebar:
        st.subheader("Dados")
        if st.button("🔄 Recarregar dados agora", key="recarregar_dados"):
            st.cache_data.clear()
            st.rerun()
