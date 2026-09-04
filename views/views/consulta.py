"""
Conteúdo da página "Consulta de Inadimplência". A senha e o page_config
ficam em app.py (o roteador da navegação); este arquivo assume que quem
chegou até aqui já passou pela tela de senha.
"""

import pandas as pd
import streamlit as st

from busca import MSG_SEM_ATRASO, buscar_cliente, montar_email_map
from data_loader import carregar_dados
from ui_common import botao_recarregar_dados
from utils import fmt_moeda, parse_date, rotulo_documento, safe_col

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
email_df = dados["email"]

if base_completa.empty:
    st.warning("A aba Base_cobrança está vazia ou não foi encontrada.")
    st.stop()

st.title("🔎 Consulta de Inadimplência")
st.caption(
    f"Acessórias · dados lidos da Base_cobrança · última leitura da planilha: "
    f"{dados['carregado_em'].strftime('%d/%m/%Y %H:%M:%S')}"
)

query = st.text_input(
    "Buscar cliente",
    placeholder="Digite telefone, e-mail, razão social, CNPJ ou CPF e pressione Enter",
)

if not query:
    st.info("Digite um dado do cliente acima para consultar a situação de inadimplência.")
    st.stop()

matched_keys = buscar_cliente(query, base_completa, email_df)

if not matched_keys:
    st.warning(MSG_SEM_ATRASO)
    st.stop()

email_map = montar_email_map(email_df)

if len(matched_keys) > 1:
    st.info(
        f"Encontramos **{len(matched_keys)} clientes diferentes** com esse dado. "
        "Selecione abaixo qual você quer consultar:"
    )
    opcoes = {}
    for k in matched_keys:
        linha = base_completa[base_completa["_cliente_key"] == k].iloc[0]
        nome = linha.get("Empresa", "")
        documento = linha.get("CNPJ", "") or linha.get("CNPJ_edit", "")
        rotulo = rotulo_documento(documento)
        opcoes[f"{nome} — {rotulo} {documento}"] = k
    escolha = st.selectbox("Cliente:", list(opcoes.keys()))
    cliente_key = opcoes[escolha]
else:
    cliente_key = matched_keys[0]

linhas_cliente = base_completa[base_completa["_cliente_key"] == cliente_key].copy()

if linhas_cliente.empty:
    st.warning(MSG_SEM_ATRASO)
    st.stop()

primeira = linhas_cliente.iloc[0]
documento_cliente = primeira.get("CNPJ", "") or primeira.get("CNPJ_edit", "")
rotulo_doc = rotulo_documento(documento_cliente)

st.subheader(primeira.get("Empresa", "Cliente"))

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
dcol1.write(f"**{rotulo_doc}:** {primeira.get('CNPJ', '-') or '-'}")
dcol1.write(f"**{rotulo_doc} editado:** {primeira.get('CNPJ_edit', '-') or '-'}")
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
