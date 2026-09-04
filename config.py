"""
Configurações centrais do dashboard.
"""

import os

import streamlit as st


def _get_secret(key: str, default=None):
    """Lê uma configuração dos Secrets do Streamlit (usado no Streamlit
    Community Cloud) e, se não encontrar, cai para uma variável de
    ambiente (útil rodando localmente)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


# --------------------------------------------------------------------------
# ACESSO AOS DADOS (Google Sheets via conta de serviço)
# --------------------------------------------------------------------------
# ID da planilha do Google Sheets — fica na URL, entre "/d/" e "/edit":
#   https://docs.google.com/spreadsheets/d/ESTE_TRECHO_AQUI/edit
# Configure em .streamlit/secrets.toml (nuvem) ou na variável de ambiente
# GOOGLE_SHEETS_ID (local). Veja o README para o passo a passo completo.
GOOGLE_SHEETS_ID = _get_secret("GOOGLE_SHEETS_ID", "COLOQUE_AQUI_O_ID_DA_PLANILHA")

# Nomes exatos das abas na planilha
ABA_BASE_COBRANCA = "Base_cobrança"
ABA_BASE_EMAIL = "Base_email"
ABA_INDICADORES = "Indicadores"
ABA_HISTORICO_VALORES = "Historico_valores"
ABA_RELACAO_CLIENTES = "Relação_de_clientes"

# --------------------------------------------------------------------------
# REGRAS DE NEGÓCIO
# --------------------------------------------------------------------------
# Meta de inadimplência: 0,60% da receita do mês
META_PERCENTUAL_INADIMPLENCIA = 0.006

# Intervalo de atualização automática do dashboard (em milissegundos).
# Cuidado ao diminuir muito: cada refresh de cada pessoa com o app aberto
# gasta cota da API do Google Sheets (o cache abaixo já reduz bastante isso).
REFRESH_INTERVAL_MS = 2 * 60 * 1000  # 2 minutos

# Tempo de cache dos dados (em segundos) — deve ser um pouco menor que o
# intervalo de refresh para garantir dado fresco a cada rerun, mas alto o
# bastante pra não estourar a cota de leitura da API do Google Sheets.
CACHE_TTL_SECONDS = 110

# Valor considerado "contato sem sucesso" (ajuste conforme o texto real
# usado na coluna "Contato" da Base_cobrança). A checagem é case-insensitive
# e por "contém", então "Sem sucesso", "sem sucesso - não atendeu" etc. batem.
TERMOS_CONTATO_SEM_SUCESSO = ["sem sucesso", "não atendeu", "nao atendeu"]

# Nomes das colunas de analistas na aba Historico_valores. Usados para
# detalhar a evolução diária "por pessoa" quando o filtro de Carteira, no
# topo do dashboard, seleciona uma ou mais dessas pessoas.
COLUNAS_ANALISTAS_HISTORICO = ["Adriana", "Didiane", "Rafaela", "Vitória"]
