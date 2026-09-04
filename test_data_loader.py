"""
Testes do tratamento de dados (data_loader._processar), usando DataFrames
sintéticos no lugar de uma chamada real à API do Google Sheets.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_loader import _deduplicar_colunas, _ler_aba, _processar  # noqa: E402
from utils import rotulo_documento  # noqa: E402


def _base_bruta():
    return pd.DataFrame([
        {
            "Carteira": "Adriana", "Empresa": "Empresa Teste LTDA",
            "CNPJ": "12.345.678/0001-99", "CNPJ_edit": "",
            "Telefone": "(11) 99999-0000", "Vencimento": "01/08/2026",
            "Atraso (dias)": "10", "Valor fatura": "R$ 1.234,56",
            "Valor atualizado": "R$ 1.300,00", "Situação do contrato": "Ativo",
            "Senha boleto": "abc123", "Contato": "Acionado no Blip",
            "Dia": "20/08/2026",
        },
        {
            "Carteira": "Didiane", "Empresa": "Outra Empresa SA",
            "CNPJ": "98.765.432/0001-11", "CNPJ_edit": "",
            "Telefone": "(11) 98888-0000", "Vencimento": "15/07/2026",
            "Atraso (dias)": "5", "Valor fatura": "R$ 500,00",
            "Valor atualizado": "R$ 520,00", "Situação do contrato": "Ativo",
            "Senha boleto": "xyz789", "Contato": "Sem sucesso - não atendeu",
            "Dia": "01/08/2026",
        },
    ])


def _clientes_bruta():
    return pd.DataFrame([
        {"cnpj_cpf": "12.345.678/0001-99", "uf": "SP"},
        {"cnpj_cpf": "98.765.432/0001-11", "uf": "RJ"},
    ])


def _historico_bruta():
    return pd.DataFrame([
        {"Data": "2026-08-01T00:00:00", "Geral (Base_cobrança)": "1000,00", "Adriana": "600,00", "Didiane": "400,00"},
        {"Data": "2026-08-02T00:00:00", "Geral (Base_cobrança)": "1100,00", "Adriana": "650,00", "Didiane": "450,00"},
    ])


def test_processar_basico():
    base = _base_bruta()
    clientes = _clientes_bruta()
    historico = _historico_bruta()
    email = pd.DataFrame(columns=["email", "cnpj_cpf"])
    indicadores = pd.DataFrame([{"Mês": "Agosto", "Receita": "100000,00", "Inadimplência": "700,00"}])

    resultado = _processar(base, email, indicadores, clientes, historico)

    b = resultado["base"]
    assert len(b) == 2
    assert set(b["Mes_Vencimento"]) == {"2026-08", "2026-07"}
    assert round(b.loc[b["Empresa"] == "Empresa Teste LTDA", "Valor fatura"].iloc[0], 2) == 1234.56
    assert set(b["uf"]) == {"SP", "RJ"}
    assert b.loc[b["Contato"].str.contains("Sem sucesso"), "Contato_agrupado"].iloc[0] == "Sem sucesso"
    # busca: CNPJ sem pontuação vira a chave do cliente
    assert "12345678000199" in set(b["_cliente_key"])

    ind = resultado["indicadores"]
    assert round(ind["Meta (R$)"].iloc[0], 2) == round(100000.00 * 0.006, 2)
    assert round(ind["Falta p/ meta (R$)"].iloc[0], 2) == round(700.00 - 100000.00 * 0.006, 2)

    hist = resultado["historico"]
    assert list(hist["Dia"]) == [1, 2]
    assert hist["Ano"].iloc[0] == 2026
    assert round(hist["Adriana"].iloc[0], 2) == 600.00


def test_processar_base_vazia_nao_quebra():
    vazio = pd.DataFrame()
    resultado = _processar(vazio, vazio, vazio, vazio, vazio)
    assert resultado["base"].empty
    assert resultado["indicadores"].empty
    assert resultado["historico"].empty


def test_processar_tolera_cabecalho_de_indicadores_diferente():
    # Reproduz o caso real: a coluna vem como "mês " (minúsculo, com
    # espaço) em vez de "Mês" — não pode quebrar com KeyError.
    base = _base_bruta()
    clientes = _clientes_bruta()
    historico = _historico_bruta()
    email = pd.DataFrame(columns=["email", "cnpj_cpf"])
    indicadores = pd.DataFrame([{"mês ": "Agosto", "receita": "100000,00", "INADIMPLÊNCIA": "700,00"}])

    resultado = _processar(base, email, indicadores, clientes, historico)

    ind = resultado["indicadores"]
    assert "Mês" in ind.columns
    assert "Receita" in ind.columns
    assert "Inadimplência" in ind.columns
    assert round(ind["Meta (R$)"].iloc[0], 2) == round(100000.00 * 0.006, 2)


def test_processar_sem_colunas_esperadas_na_base_nao_quebra():
    # Base sem "Carteira", "Situação do contrato" nem "Contato" — o
    # tratamento não pode falhar com AttributeError (base.get(x, "") sem
    # a coluna devolvia uma string comum, que não tem .fillna).
    base = pd.DataFrame([
        {"Empresa": "Empresa Teste LTDA", "CNPJ": "12.345.678/0001-99",
         "Vencimento": "01/08/2026", "Valor fatura": "R$ 100,00"},
    ])
    vazio = pd.DataFrame()

    resultado = _processar(base, vazio, vazio, vazio, vazio)

    b = resultado["base"]
    assert len(b) == 1
    assert b["Carteira"].iloc[0] == "Não informado"
    assert b["Situação do contrato"].iloc[0] == "Não informado"
    assert b["Contato"].iloc[0] == "Não informado"


def test_ler_aba_com_intervalo_le_tabela_dinamica_fora_de_a1():
    # Reproduz o caso real: a aba Indicadores é uma tabela dinâmica que
    # começa em J10, não em A1 — _ler_aba precisa ler só esse intervalo
    # quando ele é passado, e não a aba inteira.
    ws = _WorksheetFalso(
        valores=[["isso", "aqui", "e", "lixo", "antes", "da", "tabela"]],
        valores_intervalo={
            "J10:N22": [
                ["Mês", "Inadimplência", "Receita", "Percentual", "A realizar"],
                ["Agosto", "4000,00", "500000,00", "0,8%", "1000,00"],
            ]
        },
    )
    ws.title = "Indicadores"
    planilha = _PlanilhaFalsa([ws])

    df = _ler_aba(planilha, "Indicadores", intervalo="J10:N22")

    assert list(df.columns) == ["Mês", "Inadimplência", "Receita", "Percentual", "A realizar"]
    assert len(df) == 1
    assert df.loc[0, "Mês"] == "Agosto"


def test_percentual_com_simbolo_abaixo_de_1_nao_vira_100x_maior():
    # Bug relatado: "0,97%" estava virando 97% na tela, porque o parser
    # antigo só dividia por 100 quando o número (sem o "%") era > 1.
    base = _base_bruta()
    clientes = _clientes_bruta()
    historico = _historico_bruta()
    email = pd.DataFrame(columns=["email", "cnpj_cpf"])
    indicadores = pd.DataFrame([
        {"Mês": "Julho", "Receita": "100000,00", "Inadimplência": "970,00", "Percentual": "0,97%"},
        {"Mês": "Agosto", "Receita": "100000,00", "Inadimplência": "6000,00", "Percentual": "6%"},
    ])

    resultado = _processar(base, email, indicadores, clientes, historico)
    ind = resultado["indicadores"].set_index("Mês")

    assert round(ind.loc["Julho", "Percentual"], 4) == 0.0097
    assert round(ind.loc["Agosto", "Percentual"], 4) == 0.06


def test_rotulo_documento_cpf_vs_cnpj():
    assert rotulo_documento("123.456.789-01") == "CPF"  # 11 dígitos
    assert rotulo_documento("12.345.678/0001-99") == "CNPJ"  # 14 dígitos
    assert rotulo_documento("") == "CNPJ"  # vazio cai no padrão CNPJ


def test_deduplicar_colunas_com_repetidas_e_em_branco():
    # Reproduz o caso real que quebrava com get_all_records: cabeçalho
    # com "Multa" repetido duas vezes e uma coluna sem nome.
    cabecalho = ["Empresa", "Multa", "Multa", "", "Contato"]
    resultado = _deduplicar_colunas(cabecalho)
    assert resultado == ["Empresa", "Multa", "Multa_2", "Coluna_sem_nome", "Contato"]
    assert len(resultado) == len(set(resultado))  # todos únicos


class _WorksheetFalso:
    """Simula o objeto Worksheet do gspread só com o que _ler_aba usa."""

    def __init__(self, valores, valores_intervalo=None):
        self._valores = valores
        self._valores_intervalo = valores_intervalo or {}

    def get_all_values(self):
        return self._valores

    def get(self, intervalo):
        return self._valores_intervalo[intervalo]


class _PlanilhaFalsa:
    def __init__(self, worksheets):
        self._worksheets = worksheets

    def worksheets(self):
        return self._worksheets


def test_ler_aba_com_cabecalho_duplicado_nao_quebra():
    valores = [
        ["Empresa", "Multa", "Multa", "Contato"],
        ["Empresa Teste LTDA", "10,00", "5,00", "Acionado no Blip"],
        ["Outra Empresa SA", "20,00"],  # linha mais curta que o cabeçalho
    ]
    ws = _WorksheetFalso(valores)
    ws.title = "Base_cobrança"
    planilha = _PlanilhaFalsa([ws])

    df = _ler_aba(planilha, "Base_cobrança")

    assert list(df.columns) == ["Empresa", "Multa", "Multa_2", "Contato"]
    assert len(df) == 2
    assert df.loc[1, "Multa_2"] == ""  # célula ausente na linha curta vira vazio
