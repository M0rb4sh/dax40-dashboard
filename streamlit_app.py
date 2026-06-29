from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf


APP_DIR = Path(__file__).resolve().parent
WEIGHTS_FILE = APP_DIR / "dax_weights.csv"
DAX_TICKER = "^GDAXI"


st.set_page_config(
    page_title="DAX 40 – Tagesbeiträge",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.15rem; padding-bottom: 2rem; max-width: 1500px;}
        h1 {font-size: 2rem !important; letter-spacing: -0.03em; margin-bottom: 0.1rem !important;}
        h2 {font-size: 1.25rem !important; margin-top: 1.2rem !important;}
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 0.75rem 0.85rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        [data-testid="stMetricLabel"] {font-size: 0.82rem;}
        [data-testid="stMetricValue"] {font-size: 1.45rem;}
        .status-line {
            display: inline-block;
            color: #475569;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 999px;
            padding: 0.25rem 0.65rem;
            font-size: 0.78rem;
        }
        div[data-testid="stDataFrame"] {border: 1px solid #e5e7eb; border-radius: 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)


class DashboardDataError(Exception):
    """Verständliche Fehlermeldung für fehlerhafte lokale Eingabedaten."""


def format_de(value: float, decimals: int = 2, show_plus: bool = False) -> str:
    """Formatiert eine Zahl mit deutschen Tausender- und Dezimalzeichen."""
    if pd.isna(value):
        return "–"
    prefix = "+" if show_plus and value > 0 else ""
    text = f"{value:,.{decimals}f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefix}{text}"


def load_weights(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise DashboardDataError(f"Die Datei {path.name} wurde nicht gefunden.")

    try:
        # Erkennt sowohl Komma- als auch Semikolon-getrennte CSV-Dateien.
        frame = pd.read_csv(path, sep=None, engine="python", dtype=str)
    except Exception as exc:
        raise DashboardDataError(f"Die Gewichtungsdatei konnte nicht gelesen werden: {exc}") from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"Unternehmen", "Ticker", "Gewichtung_pct"}
    missing = required.difference(frame.columns)
    if missing:
        raise DashboardDataError(
            "In dax_weights.csv fehlen Spalten: " + ", ".join(sorted(missing))
        )

    frame = frame[["Unternehmen", "Ticker", "Gewichtung_pct"]].copy()
    frame["Unternehmen"] = frame["Unternehmen"].astype(str).str.strip()
    frame["Ticker"] = frame["Ticker"].astype(str).str.strip().str.upper()
    weight_text = (
        frame["Gewichtung_pct"]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.strip()
        .str.replace(",", ".", regex=False)
    )
    frame["Gewichtung_pct"] = pd.to_numeric(weight_text, errors="coerce")

    invalid = frame[
        frame["Unternehmen"].eq("")
        | frame["Ticker"].eq("")
        | frame["Gewichtung_pct"].isna()
        | frame["Gewichtung_pct"].le(0)
    ]
    if not invalid.empty:
        rows = ", ".join(str(number + 2) for number in invalid.index.tolist())
        raise DashboardDataError(f"Ungültige Werte in dax_weights.csv, Zeile(n): {rows}")
    if frame["Ticker"].duplicated().any():
        duplicates = ", ".join(frame.loc[frame["Ticker"].duplicated(), "Ticker"])
        raise DashboardDataError(f"Ticker doppelt vorhanden: {duplicates}")

    return frame.reset_index(drop=True)


def extract_close(data: pd.DataFrame, symbol: str) -> pd.Series:
    """Liest die Schlusskurs-Spalte unabhängig von yfinance-Spaltenreihenfolge."""
    if data is None or data.empty:
        return pd.Series(dtype="float64")

    try:
        if isinstance(data.columns, pd.MultiIndex):
            level_0 = data.columns.get_level_values(0)
            level_1 = data.columns.get_level_values(1)
            if symbol in level_0:
                result = data[symbol]["Close"]
            elif symbol in level_1:
                result = data["Close"][symbol]
            else:
                return pd.Series(dtype="float64")
        else:
            if "Close" not in data.columns:
                return pd.Series(dtype="float64")
            result = data["Close"]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")

    if isinstance(result, pd.DataFrame):
        result = result.iloc[:, 0]
    return pd.to_numeric(result, errors="coerce").dropna()


def date_in_berlin(index_value: object):
    timestamp = pd.Timestamp(index_value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("Europe/Berlin")
    return timestamp.date()


def quote_from_series(intraday: pd.Series, daily: pd.Series) -> dict[str, float]:
    intraday = intraday.dropna()
    daily = daily.dropna()

    if not intraday.empty:
        current = float(intraday.iloc[-1])
        trade_date = date_in_berlin(intraday.index[-1])
    elif not daily.empty:
        current = float(daily.iloc[-1])
        trade_date = date_in_berlin(daily.index[-1])
    else:
        return {"current": float("nan"), "previous": float("nan"), "performance": float("nan")}

    previous_candidates = daily[
        [date_in_berlin(index_value) < trade_date for index_value in daily.index]
    ]
    if not previous_candidates.empty:
        previous = float(previous_candidates.iloc[-1])
    elif len(daily) >= 2:
        previous = float(daily.iloc[-2])
    else:
        previous = float("nan")

    performance = (
        (current / previous - 1.0) * 100.0
        if pd.notna(previous) and previous != 0
        else float("nan")
    )
    return {"current": current, "previous": previous, "performance": performance}


def fetch_one_symbol(symbol: str) -> dict[str, float]:
    """Schonender Einzelabruf als Ersatz, falls der schnelle Sammelabruf scheitert."""
    try:
        ticker = yf.Ticker(symbol)
        intraday = ticker.history(period="1d", interval="5m", auto_adjust=False)
        daily = ticker.history(period="1mo", interval="1d", auto_adjust=False)
        return quote_from_series(
            pd.to_numeric(intraday.get("Close", pd.Series(dtype="float64")), errors="coerce"),
            pd.to_numeric(daily.get("Close", pd.Series(dtype="float64")), errors="coerce"),
        )
    except Exception:
        return {"current": float("nan"), "previous": float("nan"), "performance": float("nan")}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_market_data(tickers: tuple[str, ...]) -> tuple[pd.DataFrame, float, str, list[str]]:
    symbols = list(dict.fromkeys([*tickers, DAX_TICKER]))
    batch_errors: list[str] = []

    try:
        daily_data = yf.download(
            symbols,
            period="1mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as exc:
        daily_data = pd.DataFrame()
        batch_errors.append(f"Tagesdaten: {exc}")

    try:
        intraday_data = yf.download(
            symbols,
            period="1d",
            interval="5m",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
            prepost=False,
        )
    except Exception as exc:
        intraday_data = pd.DataFrame()
        batch_errors.append(f"Intraday-Daten: {exc}")

    quotes: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        quotes[symbol] = quote_from_series(
            extract_close(intraday_data, symbol),
            extract_close(daily_data, symbol),
        )

    missing_symbols = [
        symbol
        for symbol, quote in quotes.items()
        if pd.isna(quote["current"]) or pd.isna(quote["performance"])
    ]
    if missing_symbols:
        # Nur fehlende Werte werden parallel einzeln erneut versucht.
        with ThreadPoolExecutor(max_workers=min(8, len(missing_symbols))) as executor:
            futures = {executor.submit(fetch_one_symbol, symbol): symbol for symbol in missing_symbols}
            for future in as_completed(futures):
                quotes[futures[future]] = future.result()

    unavailable = [
        symbol
        for symbol, quote in quotes.items()
        if pd.isna(quote["current"]) or pd.isna(quote["performance"])
    ]

    rows = [
        {
            "Ticker": symbol,
            "Aktueller_Kurs": quotes[symbol]["current"],
            "Tagesperformance_pct": quotes[symbol]["performance"],
        }
        for symbol in tickers
    ]
    dax_level = quotes[DAX_TICKER]["current"]
    timestamp = datetime.now().astimezone().strftime("%d.%m.%Y, %H:%M:%S %Z")

    messages = []
    if unavailable:
        messages.append("Keine vollständigen Kursdaten für: " + ", ".join(unavailable))
    if batch_errors and unavailable:
        messages.extend(batch_errors)
    return pd.DataFrame(rows), dax_level, timestamp, messages


def points_text(value: float) -> str:
    return "–" if pd.isna(value) else f"{format_de(value, 2, True)} Pkt."


def make_bar_chart(valid: pd.DataFrame):
    chart_data = valid.sort_values("DAX_Punkte", ascending=True).copy()
    chart_data["Richtung"] = chart_data["DAX_Punkte"].apply(
        lambda value: "Stütze" if value >= 0 else "Belastung"
    )
    chart_data["Punkte_Label"] = chart_data["DAX_Punkte"].apply(
        lambda value: format_de(value, 2, True)
    )
    order = chart_data["Unternehmen"].tolist()

    figure = px.bar(
        chart_data,
        x="DAX_Punkte",
        y="Unternehmen",
        orientation="h",
        color="Richtung",
        color_discrete_map={"Belastung": "#dc2626", "Stütze": "#16a34a"},
        text="Punkte_Label",
        custom_data=["Ticker", "Gewichtung_pct", "Tagesperformance_pct"],
        labels={"DAX_Punkte": "Geschätzter DAX-Punktebeitrag", "Unternehmen": ""},
    )
    figure.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>Ticker: %{customdata[0]}"
            "<br>Gewichtung: %{customdata[1]:.2f} %"
            "<br>Tagesperformance: %{customdata[2]:+.2f} %"
            "<br>DAX-Beitrag: %{x:+.2f} Punkte<extra></extra>"
        ),
    )
    figure.update_layout(
        height=max(720, 23 * len(chart_data)),
        margin=dict(l=10, r=50, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        bargap=0.24,
        font=dict(size=12),
    )
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=order,
        autorange="reversed",
        tickfont=dict(size=11),
    )
    figure.update_xaxes(zeroline=True, zerolinecolor="#64748b", gridcolor="#e5e7eb")
    return figure


def make_treemap(valid: pd.DataFrame):
    chart_data = valid.copy()
    chart_data["Punkte_Label"] = chart_data["DAX_Punkte"].apply(points_text)
    color_limit = max(float(chart_data["DAX_Punkte"].abs().max()), 0.01)
    figure = px.treemap(
        chart_data,
        path=["Unternehmen"],
        values="Gewichtung_pct",
        color="DAX_Punkte",
        color_continuous_scale=[(0.0, "#b91c1c"), (0.5, "#f8fafc"), (1.0, "#15803d")],
        color_continuous_midpoint=0,
        range_color=[-color_limit, color_limit],
        custom_data=["Punkte_Label", "Ticker", "Gewichtung_pct", "Tagesperformance_pct"],
    )
    figure.update_traces(
        texttemplate="<b>%{label}</b><br>%{customdata[0]}",
        hovertemplate=(
            "<b>%{label}</b><br>Ticker: %{customdata[1]}"
            "<br>Gewichtung: %{customdata[2]:.2f} %"
            "<br>Tagesperformance: %{customdata[3]:+.2f} %"
            "<br>DAX-Beitrag: %{customdata[0]}<extra></extra>"
        ),
        marker=dict(line=dict(color="white", width=1.5)),
    )
    figure.update_layout(
        height=690,
        margin=dict(l=5, r=5, t=30, b=5),
        paper_bgcolor="white",
        coloraxis_colorbar=dict(title="DAX-Punkte", thickness=12),
    )
    return figure


def top_list(frame: pd.DataFrame, direction: str) -> pd.DataFrame:
    if direction == "negative":
        result = frame[frame["DAX_Punkte"] < 0].nsmallest(5, "DAX_Punkte")
    else:
        result = frame[frame["DAX_Punkte"] > 0].nlargest(5, "DAX_Punkte")
    result = result[["Unternehmen", "Tagesperformance_pct", "DAX_Punkte"]].copy()
    result.columns = ["Unternehmen", "Heute", "DAX-Punkte"]
    return result


def style_top_list(frame: pd.DataFrame):
    return frame.style.format(
        {
            "Heute": lambda value: "–" if pd.isna(value) else f"{format_de(value, 2, True)} %",
            "DAX-Punkte": points_text,
        },
        na_rep="–",
    ).map(
        lambda value: "color: #15803d; font-weight: 600"
        if pd.notna(value) and value > 0
        else "color: #b91c1c; font-weight: 600",
        subset=["DAX-Punkte"],
    )


# Kopfzeile und Aktualisierung
title_column, action_column = st.columns([5, 1])
with title_column:
    st.title("DAX 40 – Wer bewegt den Index heute?")
    st.caption("Geschätzte gewichtete Tagesbeiträge aller 40 DAX-Unternehmen")
with action_column:
    if st.button("↻ Jetzt aktualisieren", type="primary", use_container_width=True):
        fetch_market_data.clear()
        st.rerun()

try:
    weights = load_weights(WEIGHTS_FILE)
except DashboardDataError as exc:
    st.error(str(exc))
    st.info(
        "Die Datei dax_weights.csv muss die Spalten Unternehmen, Ticker und Gewichtung_pct enthalten."
    )
    st.stop()

with st.spinner("Kurse und DAX-Stand werden geladen …"):
    market_prices, dax_level, updated_at, fetch_messages = fetch_market_data(
        tuple(weights["Ticker"].tolist())
    )

data = weights.merge(market_prices, on="Ticker", how="left")
data["DAX_Punkte"] = (
    dax_level
    * data["Gewichtung_pct"]
    * data["Tagesperformance_pct"]
    / 10000.0
)
data = data.sort_values("DAX_Punkte", ascending=True, na_position="last").reset_index(drop=True)
data.insert(0, "Rang", range(1, len(data) + 1))

valid = data.dropna(subset=["Aktueller_Kurs", "Tagesperformance_pct", "DAX_Punkte"]).copy()
negative_points = float(valid.loc[valid["DAX_Punkte"] < 0, "DAX_Punkte"].sum())
positive_points = float(valid.loc[valid["DAX_Punkte"] > 0, "DAX_Punkte"].sum())
net_points = negative_points + positive_points
rising = int((valid["Tagesperformance_pct"] > 0).sum())
falling = int((valid["Tagesperformance_pct"] < 0).sum())

st.markdown(
    f'<span class="status-line">Letzte Aktualisierung: {escape(updated_at)} · '
    f'{len(valid)}/{len(data)} Aktien vollständig</span>',
    unsafe_allow_html=True,
)

if fetch_messages:
    st.warning(" | ".join(fetch_messages))
if pd.isna(dax_level):
    st.error(
        "Der aktuelle DAX-Stand konnte nicht geladen werden. Kurse werden soweit möglich angezeigt; "
        "Punktebeiträge stehen erst nach einem erfolgreichen Abruf zur Verfügung."
    )

kpi_columns = st.columns(6)
kpis = [
    ("DAX-Stand", "–" if pd.isna(dax_level) else f"{format_de(dax_level, 2)} Pkt."),
    ("Belastungen", points_text(negative_points) if not valid.empty else "–"),
    ("Stützen", points_text(positive_points) if not valid.empty else "–"),
    ("Nettoeffekt", points_text(net_points) if not valid.empty else "–"),
    ("Steigende Aktien", str(rising)),
    ("Fallende Aktien", str(falling)),
]
for column, (label, value) in zip(kpi_columns, kpis):
    column.metric(label, value)

if not valid.empty:
    st.subheader("Die stärksten Treiber")
    negative_column, positive_column = st.columns(2)
    with negative_column:
        st.markdown("**Top 5 Belastungen**")
        negative_top = top_list(valid, "negative")
        if negative_top.empty:
            st.info("Heute gibt es aktuell keine negativen Beiträge.")
        else:
            st.dataframe(
                style_top_list(negative_top),
                hide_index=True,
                use_container_width=True,
                height=210,
            )
    with positive_column:
        st.markdown("**Top 5 Stützen**")
        positive_top = top_list(valid, "positive")
        if positive_top.empty:
            st.info("Heute gibt es aktuell keine positiven Beiträge.")
        else:
            st.dataframe(
                style_top_list(positive_top),
                hide_index=True,
                use_container_width=True,
                height=210,
            )

    st.subheader("Beitrag je Unternehmen")
    st.plotly_chart(make_bar_chart(valid), use_container_width=True, config={"displaylogo": False})

    st.subheader("Marktübersicht nach Gewichtung")
    st.caption(
        "Je größer die Kachel, desto höher das DAX-Gewicht. Rot belastet den Index, Grün stützt ihn."
    )
    st.plotly_chart(make_treemap(valid), use_container_width=True, config={"displaylogo": False})
else:
    st.info("Sobald Kursdaten verfügbar sind, erscheinen hier Balkendiagramm und Treemap.")

st.subheader("Kompakte Gesamttabelle")
table = data[
    [
        "Rang",
        "Unternehmen",
        "Aktueller_Kurs",
        "Gewichtung_pct",
        "Tagesperformance_pct",
        "DAX_Punkte",
    ]
].copy()
table.columns = [
    "Rang",
    "Unternehmen",
    "Aktueller Kurs",
    "Gewichtung %",
    "Tagesperformance %",
    "Geschätzte DAX-Punkte",
]

table_style = table.style.format(
    {
        "Aktueller Kurs": lambda value: "–" if pd.isna(value) else f"{format_de(value, 2)} €",
        "Gewichtung %": lambda value: "–" if pd.isna(value) else f"{format_de(value, 2)} %",
        "Tagesperformance %": lambda value: (
            "–" if pd.isna(value) else f"{format_de(value, 2, True)} %"
        ),
        "Geschätzte DAX-Punkte": points_text,
    },
    na_rep="–",
).map(
    lambda value: "color: #15803d; font-weight: 650"
    if pd.notna(value) and value > 0
    else ("color: #b91c1c; font-weight: 650" if pd.notna(value) and value < 0 else ""),
    subset=["Tagesperformance %", "Geschätzte DAX-Punkte"],
)
st.dataframe(table_style, hide_index=True, use_container_width=True, height=720)

weight_sum = float(weights["Gewichtung_pct"].sum())
st.caption(
    f"Gewichtungssumme der lokalen CSV: {format_de(weight_sum, 2)} %. "
    "Die Punktebeiträge sind Näherungswerte, keine offizielle Indexberechnung. "
    "Yahoo-Finance-Kurse können verzögert sein. Keine Anlageberatung."
)
