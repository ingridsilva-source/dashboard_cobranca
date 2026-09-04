"""
Funções utilitárias de formatação e normalização de texto/números,
compartilhadas entre data_loader.py, busca.py e app.py.
"""

import re
import unicodedata
from datetime import datetime

import pandas as pd


def strip_accents(text) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text) -> str:
    return strip_accents(str(text or "")).lower().strip()


def only_digits(text) -> str:
    return re.sub(r"\D", "", str(text or ""))


def safe_col(df: pd.DataFrame, name: str) -> pd.Series:
    """Retorna a coluna como Series de texto, mesmo que ela não exista no
    DataFrame (evita o app quebrar se um nome de coluna mudar um dia)."""
    if name in df.columns:
        return df[name].fillna("")
    return pd.Series([""] * len(df), index=df.index)


def parse_money(value) -> float:
    """Converte valores vindos do Google Sheets (numérico ou texto tipo
    'R$ 1.234,56') para float."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = re.sub(r"[^\d,.\-]", "", str(value).strip())
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fmt_moeda(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = 0.0
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def parse_date(value):
    """Interpreta datas vindas do Google Sheets em vários formatos possíveis
    (serial do Sheets, ISO, dd/mm/aaaa etc.)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            base = datetime(1899, 12, 30)
            return (base + pd.Timedelta(days=float(value))).date()
        except Exception:
            return None
    s = str(value).strip()
    if not s:
        return None
    s_sem_z = s.replace("Z", "")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(s_sem_z, fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return parsed.date() if pd.notna(parsed) else None
    except Exception:
        return None


def format_date(d) -> str:
    if not d:
        return "-"
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def mes_vencimento_label(valor: str) -> str:
    """Converte 'AAAA-MM' (formato de Mes_Vencimento) em 'Mês/AAAA' pra
    exibir nos filtros e eixos dos gráficos."""
    if not valor or "-" not in str(valor):
        return str(valor)
    try:
        ano, mes = str(valor).split("-")
        return f"{MESES_PT[int(mes)]}/{ano}"
    except (ValueError, KeyError):
        return str(valor)
