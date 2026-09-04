"""
Lógica de busca de cliente para a Consulta de Inadimplência, embutida no
topo do dashboard. Cruza CNPJ, CNPJ editado, telefone, razão social e
e-mail contra a Base_cobrança já tratada pelo data_loader.
"""

import re

import pandas as pd

from utils import normalize_text, only_digits

MSG_SEM_ATRASO = (
    "Este cliente não possui boletos ATRASADOS. Qualquer dúvida, "
    "gentileza fazer contato com o financeiro."
)


def buscar_cliente(query: str, base: pd.DataFrame, email: pd.DataFrame):
    """Retorna a lista de client_keys (CNPJ ou CNPJ_edit normalizado) que
    batem com a busca por telefone, e-mail, razão social, CNPJ ou CNPJ
    editado."""
    if base is None or base.empty or not query.strip():
        return []

    digits_query = only_digits(query)
    text_query = normalize_text(query)
    keys = set()

    # 1) CNPJ / CNPJ editado (dígitos, comparação exata) + telefone
    if len(digits_query) >= 6:
        mask_cnpj = (base["CNPJ_limpo"] == digits_query) | (base["CNPJ_edit_limpo"] == digits_query)
        keys.update(base.loc[mask_cnpj, "_cliente_key"])

        # telefone: compara pelos últimos 8 dígitos, pra tolerar DDI/DDD
        # digitados de forma diferente na busca
        tail = digits_query[-8:]
        mask_tel = (base["Telefone_limpo"] != "") & base["Telefone_limpo"].str.endswith(tail)
        keys.update(base.loc[mask_tel, "_cliente_key"])

    # 2) Razão social (Empresa) — busca por trecho do nome
    if text_query:
        mask_empresa = base["Empresa_norm"].str.contains(re.escape(text_query), na=False)
        keys.update(base.loc[mask_empresa, "_cliente_key"])

    # 3) E-mail — procura na Base_email e cruza pelo CNPJ/CPF
    if email is not None and not email.empty and text_query and "_email_norm" in email.columns:
        mask_email = email["_email_norm"].str.contains(re.escape(text_query), na=False)
        for c in email.loc[mask_email, "_cnpj_digits"]:
            if not c:
                continue
            match = base[(base["CNPJ_limpo"] == c) | (base["CNPJ_edit_limpo"] == c)]
            keys.update(match["_cliente_key"])

    keys.discard("")
    return sorted(k for k in keys if k)


def montar_email_map(email: pd.DataFrame):
    """CNPJ (dígitos) -> lista de e-mails, pra exibir na ficha do cliente."""
    resultado = {}
    if email is None or email.empty or "_cnpj_digits" not in email.columns:
        return resultado
    col_email = "email" if "email" in email.columns else None
    if col_email is None:
        return resultado
    for _, row in email.iterrows():
        c = row.get("_cnpj_digits", "")
        if not c:
            continue
        valor = row.get(col_email, "")
        if valor:
            resultado.setdefault(c, [])
            if valor not in resultado[c]:
                resultado[c].append(valor)
    return resultado
