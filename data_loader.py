"""
Camada de acesso aos dados: lê as abas da planilha do Google Sheets
(Base_cobrança, Base_email, Indicadores, Historico_valores,
Relação_de_clientes) via API, autenticando com uma conta de serviço, e
devolve DataFrames já tratados e prontos para uso no dashboard e na
consulta de inadimplência.
"""

import re
import unicodedata
from pathlib import Path

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

import config
from utils import only_digits, parse_money, parse_date, safe_col

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Palavras de conexão que não mudam o sentido do status de contato — remover
# elas permite agrupar "acionado no blip" com "acionado via blip", por exemplo.
_STOPWORDS_CONTATO = {
    "no", "na", "nos", "nas", "via", "por", "pelo", "pela", "de", "do", "da",
    "dos", "das", "com", "o", "a", "os", "as", "e", "em", "ao", "aos", "um",
    "uma", "uns", "umas",
}


def _normalizar_simples(texto) -> str:
    """Normaliza texto pra comparação tolerante: sem acento (inclusive
    diferenças de codificação Unicode do mesmo acento), maiúsculas/
    minúsculas e espaços extras não importam."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


# Nomes "canônicos" de coluna que o resto do código espera, por aba. Ao
# carregar os dados, qualquer coluna da planilha cujo nome bata com um
# destes (ignorando acento/maiúscula/espaços) é renomeada pro nome
# canônico — assim uma pequena diferença de digitação na planilha (ex.:
# "mês" em vez de "Mês", ou um espaço a mais) não quebra o dashboard.
COLUNAS_CANONICAS_BASE = [
    "Carteira", "Empresa", "CNPJ", "CNPJ_edit", "Telefone", "Vencimento",
    "Atraso (dias)", "Valor fatura", "Valor atualizado",
    "Situação do contrato", "Senha boleto", "Contato", "Dia",
]
COLUNAS_CANONICAS_INDICADORES = ["Mês", "Receita", "Inadimplência", "A realizar", "Percentual"]
COLUNAS_CANONICAS_CLIENTES = ["cnpj_cpf", "uf"]
COLUNAS_CANONICAS_EMAIL = ["email", "cnpj_cpf"]


def _colunas_canonicas_historico():
    return ["Data", "Geral (Base_cobrança)"] + list(config.COLUNAS_ANALISTAS_HISTORICO)


def _renomear_para_canonico(df: pd.DataFrame, colunas_esperadas) -> pd.DataFrame:
    """Encontra colunas do DataFrame cujo nome bate (de forma tolerante)
    com um dos nomes esperados e as renomeia pro nome canônico. Não
    falha se alguma coluna esperada não existir — isso é tratado depois,
    onde cada coluna é usada."""
    if df.empty:
        return df
    normalizados = {_normalizar_simples(c): c for c in df.columns}
    renomear = {}
    for alvo in colunas_esperadas:
        atual = normalizados.get(_normalizar_simples(alvo))
        if atual and atual != alvo:
            renomear[atual] = alvo
    return df.rename(columns=renomear) if renomear else df


def _normalizar_contato(texto: str) -> str:
    """Gera uma 'chave' normalizada do texto de contato: minúsculo, sem
    acento, sem pontuação, sem palavras de conexão, e com as palavras em
    ordem alfabética (pra não importar a ordem). Textos que geram a mesma
    chave são tratados como a mesma categoria de contato."""
    if not texto:
        return ""
    t = texto.lower().strip()
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    palavras = [p for p in t.split() if p not in _STOPWORDS_CONTATO]
    palavras.sort()
    return " ".join(palavras)


# --------------------------------------------------------------------------
# ACESSO AO GOOGLE SHEETS
# --------------------------------------------------------------------------
def _get_credentials():
    """Monta as credenciais da conta de serviço a partir dos Secrets do
    Streamlit (uso no Streamlit Community Cloud) ou de um arquivo local
    service_account.json na raiz do projeto (uso na sua máquina)."""
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            return Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception:
        pass

    caminho = Path(__file__).parent / "service_account.json"
    if caminho.exists():
        return Credentials.from_service_account_file(str(caminho), scopes=SCOPES)

    raise RuntimeError(
        "Credenciais do Google não encontradas. Configure o segredo "
        "'gcp_service_account' (Streamlit Cloud) ou coloque um arquivo "
        "service_account.json na raiz do projeto (uso local). Veja o README."
    )


def _abrir_planilha():
    creds = _get_credentials()
    cliente = gspread.authorize(creds)
    try:
        return cliente.open_by_key(config.GOOGLE_SHEETS_ID)
    except gspread.exceptions.APIError as e:
        raise RuntimeError(
            "Não foi possível abrir a planilha do Google Sheets. Confira se "
            "GOOGLE_SHEETS_ID está correto e se a planilha foi compartilhada "
            "com o e-mail da conta de serviço (acesso de Leitor).\n\n"
            f"Erro técnico: {e}"
        ) from e


def _encontrar_aba(planilha, nome_desejado):
    """Procura a aba tolerando pequenas diferenças de acentuação/maiúsculas
    (ex.: 'Base_cobranca' vs 'Base_cobrança')."""
    alvo = _normalizar_simples(nome_desejado)
    for ws in planilha.worksheets():
        if _normalizar_simples(ws.title) == alvo:
            return ws
    return None


def _deduplicar_colunas(nomes):
    """Garante nomes de coluna únicos, mesmo que a planilha tenha
    cabeçalhos repetidos (ex.: duas colunas 'Multa') ou em branco. A
    primeira ocorrência mantém o nome original; as repetições ganham um
    sufixo (_2, _3, ...). Sem isso, gspread recusa a leitura da aba."""
    contagem = {}
    resultado = []
    for nome in nomes:
        nome = str(nome).strip() if str(nome).strip() else "Coluna_sem_nome"
        contagem[nome] = contagem.get(nome, 0) + 1
        if contagem[nome] == 1:
            resultado.append(nome)
        else:
            resultado.append(f"{nome}_{contagem[nome]}")
    return resultado


def _ler_aba(planilha, nome_desejado, intervalo: str = None) -> pd.DataFrame:
    """Lê uma aba pegando os valores brutos, em vez de get_all_records:
    este último quebra quando a planilha tem cabeçalhos duplicados ou em
    branco, o que é comum em planilhas mantidas por várias pessoas ao
    longo do tempo.

    Se `intervalo` for passado (ex.: "J10:N22"), lê só aquele intervalo
    da aba — usado pra tabelas dinâmicas que não começam em A1. Sem
    `intervalo`, lê a aba inteira (get_all_values)."""
    ws = _encontrar_aba(planilha, nome_desejado)
    if ws is None:
        return pd.DataFrame()

    valores = ws.get(intervalo) if intervalo else ws.get_all_values()
    if not valores:
        return pd.DataFrame()

    cabecalho = _deduplicar_colunas(valores[0])
    n_colunas = len(cabecalho)

    linhas = []
    for linha in valores[1:]:
        if len(linha) < n_colunas:
            linha = linha + [""] * (n_colunas - len(linha))
        elif len(linha) > n_colunas:
            linha = linha[:n_colunas]
        linhas.append(linha)

    return pd.DataFrame(linhas, columns=cabecalho)


# --------------------------------------------------------------------------
# TRATAMENTO DOS DADOS (função pura — sem chamada de rede — pra testar fácil)
# --------------------------------------------------------------------------
def _processar(base, email, indicadores, clientes, historico):
    base = base.copy()
    email = email.copy()
    indicadores = indicadores.copy()
    clientes = clientes.copy()
    historico = historico.copy()

    # Tolera pequenas diferenças de acento/maiúsculas/espaços nos
    # cabeçalhos reais da planilha em relação ao nome que o código espera.
    base = _renomear_para_canonico(base, COLUNAS_CANONICAS_BASE)
    email = _renomear_para_canonico(email, COLUNAS_CANONICAS_EMAIL)
    indicadores = _renomear_para_canonico(indicadores, COLUNAS_CANONICAS_INDICADORES)
    clientes = _renomear_para_canonico(clientes, COLUNAS_CANONICAS_CLIENTES)
    historico = _renomear_para_canonico(historico, _colunas_canonicas_historico())

    # ---------- Base_cobrança ----------
    if not base.empty:
        base["Valor fatura"] = base.get("Valor fatura", pd.Series(dtype=object)).apply(parse_money)
        base["Valor atualizado"] = base.get("Valor atualizado", pd.Series(dtype=object)).apply(parse_money)
        # Série (não escalar) como padrão: um valor solto não tem .fillna()
        # e, se a coluna não existir, o default precisa ter o mesmo índice
        # da base pra virar 0 em toda linha, e não NaN por desalinhamento.
        _atraso_default = pd.Series([0] * len(base), index=base.index)
        base["Atraso (dias)"] = pd.to_numeric(
            base.get("Atraso (dias)", _atraso_default), errors="coerce"
        ).fillna(0)

        base["Vencimento_dt"] = pd.to_datetime(
            base.get("Vencimento", pd.Series(dtype=object)).apply(parse_date), errors="coerce"
        )
        base["Mes_Vencimento"] = base["Vencimento_dt"].dt.to_period("M").astype(str)
        base.loc[base["Vencimento_dt"].isna(), "Mes_Vencimento"] = ""

        base["CNPJ_limpo"] = base.get("CNPJ", pd.Series(dtype=object)).apply(only_digits)
        base["CNPJ_edit_limpo"] = base.get("CNPJ_edit", pd.Series(dtype=object)).apply(only_digits)
        # chave do cliente: prioriza CNPJ_edit (usado no sistema para agrupar
        # o mesmo CNPJ em várias filiais/registros); cai para o CNPJ normal
        base["_cliente_key"] = base["CNPJ_edit_limpo"].where(
            base["CNPJ_edit_limpo"] != "", base["CNPJ_limpo"]
        )
        base["Telefone_limpo"] = base.get("Telefone", pd.Series(dtype=object)).apply(only_digits)
        base["Empresa_norm"] = base.get("Empresa", pd.Series(dtype=object)).fillna("").apply(_normalizar_simples)

        # safe_col nunca quebra mesmo se a coluna não existir na planilha
        # (diferente de base.get(col, "").fillna(...), que falha nesse caso
        # porque o valor padrão "" é uma string comum, sem método .fillna).
        base["Contato"] = safe_col(base, "Contato").astype(str).str.strip()
        base["Contato"] = base["Contato"].replace("", "Não informado")
        base["Carteira"] = safe_col(base, "Carteira").replace("", "Não informado")
        base["Situação do contrato"] = safe_col(base, "Situação do contrato").replace("", "Não informado")

        termos = [t.lower() for t in config.TERMOS_CONTATO_SEM_SUCESSO]
        base["Sem_sucesso"] = base["Contato"].str.lower().apply(
            lambda c: any(t in c for t in termos)
        )

        # Agrupa variações de texto parecidas (ex: "acionado no blip" e
        # "acionado via blip" viram uma única categoria). O rótulo exibido é
        # a variação mais frequente dentro do grupo.
        base["_chave_contato"] = base["Contato"].apply(_normalizar_contato)
        mapa_rotulo = (
            base.groupby("_chave_contato")["Contato"]
            .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0])
        )
        base["Contato_agrupado"] = base["_chave_contato"].map(mapa_rotulo)
        base.drop(columns=["_chave_contato"], inplace=True)

        # "Sem sucesso" continua sendo uma categoria única e explícita,
        # independente de qual variação de texto deu origem a ela.
        base["Contato_agrupado"] = base["Contato_agrupado"].where(
            ~base["Sem_sucesso"], "Sem sucesso"
        )

        # Remove linhas em branco que vêm do intervalo lido na planilha.
        # Importante: usa "_cliente_key" (CNPJ_edit OU CNPJ), não só
        # "CNPJ_limpo" — senão um cliente cujo documento só está
        # preenchido em CNPJ_edit (comum quando a mesma razão social tem
        # um registro de CNPJ e outro de CPF) era descartado aqui antes
        # mesmo de chegar na busca.
        base = base[base["_cliente_key"] != ""].reset_index(drop=True)

    # ---------- Base_email ----------
    if not email.empty:
        email["_email_norm"] = email.get("email", pd.Series(dtype=object)).fillna("").apply(_normalizar_simples)
        email["_cnpj_digits"] = email.get("cnpj_cpf", pd.Series(dtype=object)).apply(only_digits)

    # ---------- Relação_de_clientes ----------
    if not clientes.empty:
        clientes["CNPJ_limpo"] = clientes.get("cnpj_cpf", pd.Series(dtype=object)).apply(only_digits)
        clientes["uf"] = safe_col(clientes, "uf").replace("", "Não informado")

    # ---------- Cruzamento com UF ----------
    if not base.empty and not clientes.empty:
        base = base.merge(
            clientes[["CNPJ_limpo", "uf"]].drop_duplicates(subset="CNPJ_limpo"),
            on="CNPJ_limpo",
            how="left",
        )
        base["uf"] = base["uf"].fillna("Não identificado")
    elif not base.empty:
        base["uf"] = "Não identificado"

    # ---------- Indicadores ----------
    if not indicadores.empty:
        if "Mês" in indicadores.columns:
            indicadores = indicadores[
                (indicadores["Mês"].astype(str).str.strip() != "")
                & (~indicadores["Mês"].astype(str).str.strip().str.lower().eq("total geral"))
            ].reset_index(drop=True)

        for col in ["Inadimplência", "Receita", "A realizar"]:
            if col in indicadores.columns:
                indicadores[col] = indicadores[col].apply(parse_money)

        if "Percentual" in indicadores.columns:
            def _parse_pct(v):
                if pd.isna(v) or v == "":
                    return 0.0
                texto = str(v).strip()
                tem_percentual = "%" in texto
                s = texto.replace("%", "").replace(",", ".").strip()
                try:
                    val = float(s)
                except ValueError:
                    return 0.0
                # Se o texto já tinha o símbolo "%", o número sempre
                # precisa ser dividido por 100 — mesmo quando é menor que
                # 1 (ex.: "0,97%" é 0,97 vencido em 100, não 97%). Sem o
                # símbolo, mantém a regra antiga (número > 1 = já veio
                # como percentual "cheio", ex. 60 em vez de 0,60).
                if tem_percentual:
                    return val / 100
                return val / 100 if val > 1 else val
            indicadores["Percentual"] = indicadores["Percentual"].apply(_parse_pct)

        indicadores["Meta (R$)"] = indicadores.get("Receita", 0) * config.META_PERCENTUAL_INADIMPLENCIA
        indicadores["Falta p/ meta (R$)"] = indicadores.get("Inadimplência", 0) - indicadores["Meta (R$)"]

        if "Mês" in indicadores.columns:
            indicadores["Mês"] = indicadores["Mês"].astype(str).str.strip().str.capitalize()

    # ---------- Historico_valores ----------
    if not historico.empty:
        historico["Data_dt"] = pd.to_datetime(
            historico.get("Data", pd.Series(dtype=object)).apply(parse_date), errors="coerce"
        )
        historico["Geral (Base_cobrança)"] = historico.get(
            "Geral (Base_cobrança)", pd.Series(dtype=object)
        ).apply(parse_money)
        for col in config.COLUNAS_ANALISTAS_HISTORICO:
            if col in historico.columns:
                historico[col] = historico[col].apply(parse_money)
        historico = historico[historico["Data_dt"].notna()].reset_index(drop=True)
        historico["Dia"] = historico["Data_dt"].dt.day
        historico["Mes"] = historico["Data_dt"].dt.month
        historico["Ano"] = historico["Data_dt"].dt.year

    return {
        "base": base,
        "indicadores": indicadores,
        "clientes": clientes,
        "historico": historico,
        "email": email,
    }


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner="Atualizando dados da planilha...")
def carregar_dados():
    """Busca as abas da planilha no Google Sheets e devolve os DataFrames
    já tratados. Fica com cache (st.cache_data) pra não bater na API do
    Google a cada rerun — e como é a mesma função importada por todas as
    páginas do app (Dashboard e Consulta de Inadimplência), o cache é
    compartilhado entre elas."""
    planilha = _abrir_planilha()

    base = _ler_aba(planilha, config.ABA_BASE_COBRANCA)
    email = _ler_aba(planilha, config.ABA_BASE_EMAIL)
    indicadores = _ler_aba(planilha, config.ABA_INDICADORES, intervalo=config.RANGE_INDICADORES)
    clientes = _ler_aba(planilha, config.ABA_RELACAO_CLIENTES)
    historico = _ler_aba(planilha, config.ABA_HISTORICO_VALORES)

    dados = _processar(base, email, indicadores, clientes, historico)
    dados["carregado_em"] = pd.Timestamp.now()
    return dados
