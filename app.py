"""
Dashboard interativo da carteira de cobrança — com consulta de
inadimplência e filtros globais por mês e por carteira.

Rodar com:
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

import config
from auth import check_password
from busca import MSG_SEM_ATRASO, buscar_cliente, montar_email_map
from data_loader import carregar_dados
from utils import fmt_moeda, mes_vencimento_label, parse_date, safe_col

st.set_page_config(
    page_title="Dashboard de Cobrança",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Tela de senha — bloqueia todo o resto do app (dados, gráficos, consulta)
# até a senha certa ser digitada. Veja auth.py.
if not check_password():
    st.stop()

if HAS_AUTOREFRESH:
    st_autorefresh(interval=config.REFRESH_INTERVAL_MS, key="auto_refresh")


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner="Atualizando dados da planilha...")
def get_data():
    return carregar_dados()


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
with st.sidebar:
    st.subheader("Dados")
    if st.button("🔄 Recarregar dados agora"):
        st.cache_data.clear()
        st.rerun()

try:
    dados = get_data()
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
email_df = dados["email"]
indicadores = dados["indicadores"]
historico = dados["historico"]

if base_completa.empty:
    st.warning("A aba Base_cobrança está vazia ou não foi encontrada.")
    st.stop()

st.title("📊 Dashboard — Carteira de Cobrança")
st.caption(
    f"Atualiza automaticamente a cada {config.REFRESH_INTERVAL_MS // 60000} min "
    f"· Última leitura da planilha: {dados['carregado_em'].strftime('%d/%m/%Y %H:%M:%S')}"
)

# --------------------------------------------------------------------------
# CONSULTA DE INADIMPLÊNCIA (busca livre, sempre na base completa)
# --------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("🔎 Consulta de Inadimplência")
    st.caption(
        "Busque por telefone, e-mail, razão social, CNPJ ou CNPJ editado. "
        "Essa busca não é afetada pelos filtros de mês/carteira abaixo."
    )
    query = st.text_input(
        "Buscar cliente",
        placeholder="Digite qualquer um desses dados e pressione Enter",
        label_visibility="collapsed",
    )

    if query:
        matched_keys = buscar_cliente(query, base_completa, email_df)

        if not matched_keys:
            st.warning(MSG_SEM_ATRASO)
        else:
            email_map = montar_email_map(email_df)

            if len(matched_keys) > 1:
                opcoes = {}
                for k in matched_keys:
                    linha = base_completa[base_completa["_cliente_key"] == k].iloc[0]
                    nome = linha.get("Empresa", "")
                    cnpj = linha.get("CNPJ", "")
                    opcoes[f"{nome} — CNPJ {cnpj}"] = k
                escolha = st.selectbox("Mais de um cliente encontrado, selecione:", list(opcoes.keys()))
                cliente_key = opcoes[escolha]
            else:
                cliente_key = matched_keys[0]

            linhas_cliente = base_completa[base_completa["_cliente_key"] == cliente_key].copy()

            if linhas_cliente.empty:
                st.warning(MSG_SEM_ATRASO)
            else:
                primeira = linhas_cliente.iloc[0]
                st.markdown(f"### {primeira.get('Empresa', 'Cliente')}")

                total_fatura = linhas_cliente["Valor fatura"].sum()
                total_atualizado = linhas_cliente["Valor atualizado"].sum()
                qtd_boletos = len(linhas_cliente)
                maior_atraso = pd.to_numeric(linhas_cliente["Atraso (dias)"], errors="coerce").max()

                cc1, cc2, cc3, cc4 = st.columns(4)
                cc1.metric("Boletos em atraso", qtd_boletos)
                cc2.metric("Total vencido (valor da fatura)", fmt_moeda(total_fatura))
                cc3.metric("Total atualizado (com encargos)", fmt_moeda(total_atualizado))
                cc4.metric("Maior atraso (dias)", int(maior_atraso) if pd.notna(maior_atraso) else "-")

                emails_cliente = email_map.get(cliente_key, [])

                st.markdown("**Dados cadastrais**")
                dcol1, dcol2, dcol3 = st.columns(3)
                dcol1.write(f"**CNPJ:** {primeira.get('CNPJ', '-') or '-'}")
                dcol1.write(f"**CNPJ editado:** {primeira.get('CNPJ_edit', '-') or '-'}")
                dcol2.write(f"**Telefone:** {primeira.get('Telefone', '-') or '-'}")
                dcol2.write(f"**E-mail:** {', '.join(emails_cliente) if emails_cliente else '-'}")
                dcol3.write(f"**Situação do contrato:** {primeira.get('Situação do contrato', '-') or '-'}")
                dcol3.write(f"**Carteira:** {primeira.get('Carteira', '-') or '-'}")

                # último contato = linha com a data (coluna "Dia") mais recente
                if "Dia" in linhas_cliente.columns:
                    datas = linhas_cliente["Dia"].apply(parse_date)
                    if datas.notna().any():
                        idx_ultimo = datas.idxmax()
                        ultimo = linhas_cliente.loc[idx_ultimo]
                        st.markdown("**Último contato**")
                        st.write(f"{ultimo.get('Contato', '-') or '-'} em {datas.loc[idx_ultimo].strftime('%d/%m/%Y')}")

                st.markdown("**Boletos vencidos**")
                tabela = pd.DataFrame({
                    "Vencimento": linhas_cliente["Vencimento_dt"].dt.strftime("%d/%m/%Y").fillna("-"),
                    "Atraso (dias)": linhas_cliente["Atraso (dias)"],
                    "Valor fatura": linhas_cliente["Valor fatura"].apply(fmt_moeda),
                    "Valor atualizado": linhas_cliente["Valor atualizado"].apply(fmt_moeda),
                    "Senha do boleto": safe_col(linhas_cliente, "Senha boleto"),
                    "Contato": safe_col(linhas_cliente, "Contato"),
                })
                st.dataframe(tabela, use_container_width=True, hide_index=True)
    else:
        st.caption("Digite um dado do cliente acima para consultar a situação de inadimplência.")

st.divider()

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
k2.metric("Boletos vencidos (linhas)", f"{qtd_boletos:,}".replace(",", "."))
k3.metric("Clientes com boletos vencidos", f"{qtd_clientes:,}".replace(",", "."))

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
# 5. Valor vencido por mês | 6. Vencido por mês por carteira
# --------------------------------------------------------------------------
st.subheader("Valor vencido por mês (de vencimento)")
g = (
    base[base["Mes_Vencimento"] != ""]
    .groupby("Mes_Vencimento", as_index=False)["Valor fatura"]
    .sum()
    .sort_values("Mes_Vencimento")
)
g["_rotulo_mes"] = g["Mes_Vencimento"].apply(mes_vencimento_label)
fig = bar_com_rotulo_moeda(g, x="_rotulo_mes", y="Valor fatura")
fig.update_layout(xaxis_title="Mês de vencimento", yaxis_title="Valor vencido (R$)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Vencido por mês, por carteira")
g = (
    base[base["Mes_Vencimento"] != ""]
    .groupby(["Mes_Vencimento", "Carteira"], as_index=False)["Valor fatura"]
    .sum()
    .sort_values("Mes_Vencimento")
)
g["_rotulo_mes"] = g["Mes_Vencimento"].apply(mes_vencimento_label)
fig = px.bar(g, x="_rotulo_mes", y="Valor fatura", color="Carteira", barmode="group")
fig.update_layout(xaxis_title="Mês de vencimento", yaxis_title="Valor vencido (R$)")
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
