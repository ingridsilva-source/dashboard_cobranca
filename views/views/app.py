"""
Ponto de entrada do app — o nome deste arquivo (app.py) tem que
continuar exatamente assim, porque é o que está configurado em
"Main file path" nas configurações do app no Streamlit Cloud (esse
campo não pode ser mudado depois que o app já foi publicado, então o
nome do arquivo principal fica travado nesse valor para sempre).

Este arquivo só cuida da senha e monta a navegação da barra lateral,
definindo o título de cada página diretamente (por isso os títulos na
barra lateral não dependem mais do nome dos arquivos). O conteúdo de
cada página está em:
    views/dashboard.py  → "Dashboard - Carteira de Cobrança"
    views/consulta.py   → "Consulta de Inadimplência"

Rodar com:
    streamlit run app.py
"""

import streamlit as st

from auth import check_password

st.set_page_config(
    page_title="Dashboard de Cobrança",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tela de senha — bloqueia as duas páginas (Dashboard e Consulta) até a
# senha certa ser digitada. Veja auth.py.
if not check_password():
    st.stop()

dashboard_page = st.Page(
    "views/dashboard.py",
    title="Dashboard - Carteira de Cobrança",
    icon="📊",
    default=True,
)
consulta_page = st.Page(
    "views/consulta.py",
    title="Consulta de Inadimplência",
    icon="🔎",
)

pg = st.navigation([dashboard_page, consulta_page])
pg.run()
