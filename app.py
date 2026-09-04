"""
Dashboard interativo da carteira de cobrança — com filtros globais por
mês e por carteira. A Consulta de Inadimplência fica numa página
separada (veja pages/1_🔎_Consulta_de_Inadimplencia.py).

Rodar com:
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

import config
from auth import check_password
from data_loader import carregar_dados
from ui_common import botao_recarregar_dados
from utils import fmt_moeda, mes_vencimento_label, nome_mes_de_referencia

st.set_page_config(
    page_title="Dashboard de Cobrança",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tela de senha — bloqueia todo o resto do app (dados, gráficos) até a
# senha certa ser digitada. Veja auth.py.
if not check_password():
    st.stop()

if HAS_AUTOREFRESH:
    st_autorefresh(interval=config.REFRESH_INTERVAL_MS, key="auto_refresh")


def bar_com_rotulo_moeda(df, x, y, **kwargs):
    """Cria um gráfico de barras com rótulo em R$ por extenso (sem abreviar em k/M)."""
    df = df.copy()
    df["_label"] = df[y].apply(fmt_moeda)
    fig = px.bar(df, x=x, y=y, text="_label", **kwargs)
    fig.update_traces(textposition="outside")
    return fig


# --------------------------------------------------------------------------
# CARGA DE DADOS
# --------------------------------------------------------------------------
botao_recarregar_dados()

try:
    dados = carregar_dados()
except Exception as e:
    st.error(
        "Não foi possível carregar os dados do Google Sheets. Confira se "
        "GOOGLE_SHEETS_ID está correto, se a planilha foi compartilhada com "
        "o e-mail da conta de serviço (acesso de Leitor), e se as "
        "credenciais estão configuradas corretamente. Veja o README.\n\n"
        f"Erro técnico: {e}"
    )
    st.stop()

base_completa = dados["base"]
indicadores = dados["indicadores"]
historico = dados["historico"]

if base_completa.empty:
    st.warning("A aba Base_cobrança está vazia ou não foi encontrada.")
    st.stop()

st.title("📊 Dashboard — Carteira de Cobrança")
st.caption(
    f"Atualiza automaticamente a cada {config.REFRESH_INTERVAL_MS // 60000} min "
    f"· Última leitura da planilha: {dados['carregado_em'].strftime('%d/%m/%Y %H:%M:%S')} "
    "· Precisa consultar um cliente específico? Veja a página "
    "\"Consulta de Inadimplência\" na barra lateral."
)

# --------------------------------------------------------------------------
# FILTROS GLOBAIS (mês e carteira) — afetam tudo abaixo, exceto Indicadores
# --------------------------------------------------------------------------
st.subheader("Filtros")

meses_disponiveis = sorted(m for m in base_completa["Mes_Vencimento"].unique() if m)
carteiras_disponiveis = sorted(v for v in base_completa["Carteira"].dropna().unique() if v)

fcol1, fcol2 = st.columns(2)
with fcol1:
    meses_sel = st.multiselect(
        "Mês de vencimento",
        options=meses_disponiveis,
        format_func=mes_vencimento_label,
        placeholder="Todos os meses",
    )
with fcol2:
    carteiras_sel = st.multiselect(
        "Carteira",
        options=carteiras_disponiveis,
        placeholder="Todas as carteiras",
    )

base = base_completa.copy()
if meses_sel:
    base = base[base["Mes_Vencimento"].isin(meses_sel)]
if carteiras_sel:
    base = base[base["Carteira"].isin(carteiras_sel)]

if base.empty:
    st.warning("Nenhum registro encontrado para os filtros selecionados.")
    st.stop()

st.divider()

# --------------------------------------------------------------------------
# KPIs GERAIS
# --------------------------------------------------------------------------
total_vencido = base["Valor fatura"].sum()
qtd_boletos = len(base)
qtd_clientes = base["CNPJ_limpo"].nunique()

k1, k2, k3 = st.columns(3)
k1.metric("Valor total vencido", fmt_moeda(total_vencido))
k2.metric("Boletos vencidos (Quantidade)", f"{qtd_boletos:,}".replace(",", "."))
k3.metric("Clientes com boletos vencidos (Qtd)", f"{qtd_clientes:,}".replace(",", "."))

st.divider()

# --------------------------------------------------------------------------
# 1. Vencidos por carteira | 2. Vencidos por situação do contrato
# --------------------------------------------------------------------------
c1, c2 = st.columns(2)

with c1:
    st.subheader("Vencidos por carteira")
    g = base.groupby("Carteira", as_index=False)["Valor fatura"].sum().sort_values(
        "Valor fatura", ascending=False
    )
    fig = bar_com_rotulo_moeda(g, x="Carteira", y="Valor fatura")
    fig.update_layout(yaxis_title="Valor vencido (R$)")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Vencidos por situação do contrato")
    g = base.groupby("Situação do contrato", as_index=False)["Valor fatura"].sum().sort_values(
        "Valor fatura", ascending=False
    )
    fig = bar_com_rotulo_moeda(g, x="Situação do contrato", y="Valor fatura")
    fig.update_layout(yaxis_title="Valor vencido (R$)")
    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------------------
# 3. Vencidos por estado
# --------------------------------------------------------------------------
st.subheader("Vencidos por estado (UF)")
g_uf = base.groupby("uf", as_index=False)["Valor fatura"].sum().sort_values(
    "Valor fatura", ascending=False
)
top10 = g_uf.head(10)
resto = g_uf.iloc[10:]

col_graf, col_tab = st.columns([2, 1])
with col_graf:
    st.caption("Top 10 estados com mais valor vencido")
    fig = bar_com_rotulo_moeda(top10, x="uf", y="Valor fatura")
    fig.update_layout(yaxis_title="Valor vencido (R$)", xaxis_title="UF")
    st.plotly_chart(fig, use_container_width=True)

with col_tab:
    st.caption("Demais estados")
    if not resto.empty:
        st.dataframe(
            resto.rename(columns={"uf": "UF", "Valor fatura": "Valor vencido"})
            .style.format({"Valor vencido": fmt_moeda}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Todos os estados já aparecem no gráfico.")

if (base["uf"] == "Não identificado").any():
    n_sem_uf = base.loc[base["uf"] == "Não identificado", "CNPJ_limpo"].nunique()
    st.caption(
        f"⚠️ {n_sem_uf} cliente(s) não foram encontrados na Relação_de_clientes "
        "(CNPJ sem correspondência) e estão em 'Não identificado'."
    )

st.divider()

# --------------------------------------------------------------------------
# 4. Principais contatos e valores vencidos
# --------------------------------------------------------------------------
st.subheader("Contatos x valores vencidos")

g = (
    base.groupby("Contato_agrupado")
    .agg(
        Qtd_clientes=("CNPJ_limpo", "nunique"),
        Qtd_boletos=("CNPJ_limpo", "size"),
        Valor_vencido=("Valor fatura", "sum"),
    )
    .reset_index()
    .rename(columns={"Contato_agrupado": "Contato"})
    .sort_values("Valor_vencido", ascending=False)
)


def destaca_sem_sucesso(row):
    is_sem_sucesso = row["Contato"] == "Sem sucesso"
    return ["background-color: #ffe5e5"] * len(row) if is_sem_sucesso else [""] * len(row)


st.dataframe(
    g.style.apply(destaca_sem_sucesso, axis=1).format({"Valor_vencido": fmt_moeda}),
    use_container_width=True,
    hide_index=True,
)

resumo_sem_sucesso = base[base["Sem_sucesso"]]
if not resumo_sem_sucesso.empty:
    st.info(
        f"🔴 Contato sem sucesso: **{resumo_sem_sucesso['CNPJ_limpo'].nunique()} clientes** "
        f"somando **{fmt_moeda(resumo_sem_sucesso['Valor fatura'].sum())}** vencidos."
    )

st.divider()

# --------------------------------------------------------------------------
# 5. Valor vencido por mês (+ % de inadimplência do mês) | 6. Mês x Carteira
# --------------------------------------------------------------------------
st.subheader("Valor vencido por mês")

g = (
    base[base["Mes_Vencimento"] != ""]
    .groupby("Mes_Vencimento", as_index=False)["Valor fatura"]
    .sum()
    .sort_values("Mes_Vencimento")
)
g["_rotulo_mes"] = g["Mes_Vencimento"].apply(mes_vencimento_label)
g["_label_valor"] = g["Valor fatura"].apply(fmt_moeda)

# Percentual de inadimplência de cada mês, vindo da aba Indicadores (que só
# guarda o nome do mês, sem ano — por isso o cruzamento é só pelo nome).
mapa_percentual = {}
if indicadores is not None and not indicadores.empty and {"Mês", "Percentual"} <= set(indicadores.columns):
    mapa_percentual = {
        str(m).strip().lower(): p
        for m, p in zip(indicadores["Mês"], indicadores["Percentual"])
    }
g["_nome_mes"] = g["Mes_Vencimento"].apply(nome_mes_de_referencia)
g["_percentual"] = g["_nome_mes"].str.lower().map(mapa_percentual)

fig = go.Figure()
fig.add_bar(
    x=g["_rotulo_mes"], y=g["Valor fatura"], name="Valor vencido",
    text=g["_label_valor"], textposition="outside", marker_color="#4C78A8",
)
fig.add_scatter(
    x=g["_rotulo_mes"], y=g["_percentual"], name="% Inadimplência do mês",
    mode="lines+markers", yaxis="y2", marker_color="#E45756",
    text=g["_percentual"].apply(lambda p: f"{p:.2%}" if pd.notna(p) else "sem dado"),
    hovertemplate="%{x}: %{text}<extra></extra>",
)
fig.update_layout(
    xaxis_title="Mês de vencimento",
    yaxis=dict(title="Valor vencido (R$)"),
    yaxis2=dict(title="% Inadimplência", overlaying="y", side="right", tickformat=".2%"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)
if g["_percentual"].isna().all():
    st.caption(
        "⚠️ Não encontrei o percentual de inadimplência de nenhum desses meses "
        "na aba Indicadores — a linha de % fica sem dado."
    )
st.plotly_chart(fig, use_container_width=True)

st.subheader("Vencidos Mês x Carteira")
st.caption(
    "Clique numa carteira na legenda pra ver só ela; clique de novo pra voltar a ver todas."
)
g = (
    base[base["Mes_Vencimento"] != ""]
    .groupby(["Mes_Vencimento", "Carteira"], as_index=False)["Valor fatura"]
    .sum()
    .sort_values("Mes_Vencimento")
)
g["_rotulo_mes"] = g["Mes_Vencimento"].apply(mes_vencimento_label)
fig = px.bar(g, x="_rotulo_mes", y="Valor fatura", color="Carteira", barmode="group")
fig.update_layout(
    xaxis_title="Mês de vencimento",
    yaxis_title="Valor vencido (R$)",
    legend=dict(itemclick="toggleothers", itemdoubleclick="toggle"),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# Evolução diária: mês vigente x mês anterior (aba Historico_valores)
# --------------------------------------------------------------------------
st.subheader("Evolução diária do valor vencido — mês vigente x mês anterior")

colunas_pessoas_selecionadas = [c for c in carteiras_sel if c in config.COLUNAS_ANALISTAS_HISTORICO]

if historico is not None and not historico.empty and colunas_pessoas_selecionadas:
    historico = historico.copy()
    coluna_valor = "_valor_serie_selecionada"
    historico[coluna_valor] = historico[colunas_pessoas_selecionadas].sum(axis=1)
    st.caption("Mostrando a evolução de: " + ", ".join(colunas_pessoas_selecionadas))
else:
    coluna_valor = "Geral (Base_cobrança)"

if historico is not None and not historico.empty:
    hoje = pd.Timestamp.now()
    mes_anterior_ref = hoje - pd.DateOffset(months=1)

    atual = historico[
        (historico["Ano"] == hoje.year) & (historico["Mes"] == hoje.month)
    ][["Dia", coluna_valor]].copy()
    atual = atual.rename(columns={coluna_valor: "Valor"})
    atual["Série"] = "Mês vigente"

    anterior = historico[
        (historico["Ano"] == mes_anterior_ref.year)
        & (historico["Mes"] == mes_anterior_ref.month)
    ][["Dia", coluna_valor]].copy()
    anterior = anterior.rename(columns={coluna_valor: "Valor"})
    anterior["Série"] = "Mês anterior"

    combinado = pd.concat([atual, anterior], ignore_index=True).sort_values("Dia")

    if combinado.empty:
        st.caption(
            "⚠️ Não encontrei registros no Historico_valores para o mês "
            "vigente nem para o mês anterior."
        )
    else:
        combinado["Valor_fmt"] = combinado["Valor"].apply(fmt_moeda)
        fig = px.line(
            combinado,
            x="Dia",
            y="Valor",
            color="Série",
            markers=True,
            category_orders={"Série": ["Mês vigente", "Mês anterior"]},
            custom_data=["Valor_fmt"],
        )
        fig.update_traces(hovertemplate="Dia %{x}<br>%{customdata[0]}<extra></extra>")
        fig.update_layout(
            xaxis_title="Dia do mês",
            yaxis_title="Valor vencido (R$)",
            xaxis=dict(dtick=1),
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("A aba Historico_valores está vazia ou não foi encontrada.")

st.divider()

# --------------------------------------------------------------------------
# 7. Espelho da tabela dinâmica (Indicadores)
# --------------------------------------------------------------------------
st.subheader("Indicadores — Receita, inadimplência e meta")
st.caption(
    "Esta seção mostra os indicadores gerais da empresa e não é afetada "
    "pelos filtros de mês/carteira acima."
)

if indicadores is not None and not indicadores.empty:
    cols_mostrar = [c for c in [
        "Mês", "Receita", "Inadimplência", "Percentual", "Meta (R$)",
        "Falta p/ meta (R$)"
    ] if c in indicadores.columns]

    tabela = indicadores[cols_mostrar].copy()
    fmt_dict = {}
    for c in ["Receita", "Inadimplência", "Meta (R$)", "Falta p/ meta (R$)"]:
        if c in tabela.columns:
            fmt_dict[c] = fmt_moeda
    if "Percentual" in tabela.columns:
        fmt_dict["Percentual"] = lambda v: f"{v:.2%}"

    def cor_falta_meta(row):
        estilos = [""] * len(row)
        if "Falta p/ meta (R$)" in row.index and "Percentual" in row.index:
            idx = list(row.index).index("Falta p/ meta (R$)")
            if row["Percentual"] > config.META_PERCENTUAL_INADIMPLENCIA:
                estilos[idx] = "background-color: #ffd6d6"  # vermelho claro
            else:
                estilos[idx] = "background-color: #d6f5d6"  # verde claro
        return estilos

    st.dataframe(
        tabela.style.format(fmt_dict).apply(cor_falta_meta, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # Identifica o mês ANTERIOR comparando pelo nome do mês em português
    # (a coluna "Mês" na planilha é só o nome, sem ano)
    from utils import MESES_PT
    mes_anterior_num = (pd.Timestamp.now() - pd.DateOffset(months=1)).month
    mes_atual_nome = MESES_PT[mes_anterior_num]

    if "Mês" not in indicadores.columns:
        st.caption(
            "⚠️ Não encontrei uma coluna 'Mês' na aba Indicadores — não dá "
            "pra identificar automaticamente a linha do mês anterior."
        )
    else:
        linha_atual = indicadores[
            indicadores["Mês"].str.lower() == mes_atual_nome.lower()
        ]

        if not linha_atual.empty:
            atual_row = linha_atual.iloc[0]
            falta = atual_row.get("Falta p/ meta (R$)", None)
            mes_label = atual_row.get("Mês", mes_atual_nome)
            if falta is not None:
                if falta > 0:
                    st.warning(
                        f"Faltam **{fmt_moeda(falta)}** para atingir a meta de 0,60% "
                        f"de inadimplência em **{mes_label}** (mês anterior)."
                    )
                else:
                    st.success(
                        f"Meta batida em **{mes_label}** (mês anterior)! Inadimplência "
                        f"**{fmt_moeda(-falta)}** abaixo da meta."
                    )
        else:
            st.caption(
                f"⚠️ Não encontrei uma linha na tabela de Indicadores para o mês "
                f"anterior ({mes_atual_nome})."
            )
else:
    st.warning("A aba Indicadores está vazia ou não foi encontrada.")

st.caption(
    "Meta calculada como 0,60% da Receita do mês (config.META_PERCENTUAL_INADIMPLENCIA). "
    "'Falta p/ meta' = Inadimplência atual − Meta."
)
