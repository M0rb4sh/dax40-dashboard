from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf


APP_DIR = Path(__file__).resolve().parent
INDEX_CONFIGS = {
    "dax": {
        "nav_label": "Der DAX", "short_label": "DAX", "market_label": "DAX 40",
        "ticker": "^GDAXI", "weights_file": "dax_weights.csv",
        "timezone": "Europe/Berlin", "source": "Yahoo Finance/Xetra",
        "delay": "ca. 15 Min. verzögert", "constituents": "40 DAX-Unternehmen",
        "chart_limit": 40, "weight_mode": "fixed",
    },
    "sp500": {
        "nav_label": "Der S&P 500", "short_label": "S&P 500", "market_label": "S&P 500",
        "ticker": "^GSPC", "weights_file": "sp500_weights.csv",
        "timezone": "America/New_York", "source": "Yahoo Finance/USA",
        "delay": "ggf. börsenverzögert", "constituents": "503 S&P-500-Aktien",
        "chart_limit": 40, "weight_mode": "fixed",
    },
    "dow": {
        "nav_label": "Der Dow Jones", "short_label": "Dow Jones", "market_label": "Dow Jones",
        "ticker": "^DJI", "weights_file": "dow_weights.csv",
        "timezone": "America/New_York", "source": "Yahoo Finance/USA",
        "delay": "ggf. börsenverzögert", "constituents": "30 Dow-Jones-Aktien",
        "chart_limit": 30, "weight_mode": "price",
    },
}

requested_index = str(st.query_params.get("index", "dax")).lower()
INDEX_KEY = requested_index if requested_index in INDEX_CONFIGS else "dax"
INDEX = INDEX_CONFIGS[INDEX_KEY]
WEIGHTS_FILE = APP_DIR / INDEX["weights_file"]
DAX_TICKER = INDEX["ticker"]


st.set_page_config(
    page_title=f'{INDEX["short_label"]} – Tagesbeiträge',
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

def make_design(app_bg: str, button_bg: str, accent: str, grid: str = "rgba(15, 23, 42, 0.09)"):
    return {
        "app_bg": app_bg,
        "card_bg": "rgba(255, 255, 255, 0.88)",
        "text": "#000000",
        "muted": "#465569",
        "border": f"color-mix(in srgb, {accent} 27%, transparent)",
        "shadow": "0 14px 36px rgba(15, 23, 42, 0.12)",
        "status_bg": "rgba(255, 255, 255, 0.82)",
        "button_bg": button_bg,
        "chart_bg": "rgba(255, 255, 255, 0.96)",
        "grid": grid,
        "accent": accent,
    }


DESIGNS = {
    "Aurora": make_design(
        "radial-gradient(circle at 8% 0%, #dbeafe 0, transparent 30%), radial-gradient(circle at 92% 8%, #ccfbf1 0, transparent 26%), #f8fafc",
        "linear-gradient(135deg, #5eead4, #67e8f9)", "#0891b2", "#e2e8f0",
    ),
    "Electric Waves": make_design(
        "radial-gradient(ellipse at 0% 50%, rgba(34,211,238,.55) 0 18%, transparent 19% 100%) 0 0/180px 92px, radial-gradient(ellipse at 100% 50%, rgba(59,130,246,.42) 0 18%, transparent 19% 100%) 0 46px/180px 92px, linear-gradient(135deg,#93c5fd,#67e8f9)",
        "linear-gradient(135deg,#22d3ee,#3b82f6)", "#0284c7", "#bfdbfe",
    ),
    "Cobalt Grid": make_design(
        "linear-gradient(rgba(255,255,255,.28) 2px,transparent 2px) 0 0/36px 36px, linear-gradient(90deg,rgba(255,255,255,.28) 2px,transparent 2px) 0 0/36px 36px, linear-gradient(145deg,#60a5fa,#818cf8)",
        "linear-gradient(135deg,#60a5fa,#818cf8)", "#2563eb", "#dbeafe",
    ),
    "Coral Arches": make_design(
        "radial-gradient(circle at 0 50%,transparent 28px,rgba(255,255,255,.34) 29px 36px,transparent 37px) 0 0/84px 84px, radial-gradient(circle at 100% 50%,transparent 28px,rgba(251,113,133,.32) 29px 36px,transparent 37px) 42px 42px/84px 84px, linear-gradient(135deg,#fdba74,#fb7185)",
        "linear-gradient(135deg,#fb923c,#fb7185)", "#e11d48", "#ffe4e6",
    ),
    "Emerald Tiles": make_design(
        "conic-gradient(from 45deg,rgba(255,255,255,.34) 0 25%,transparent 0 50%,rgba(16,185,129,.32) 0 75%,transparent 0) 0 0/54px 54px, linear-gradient(140deg,#6ee7b7,#2dd4bf)",
        "linear-gradient(135deg,#34d399,#14b8a6)", "#059669", "#d1fae5",
    ),
    "Violet Circuit": make_design(
        "linear-gradient(90deg,rgba(255,255,255,.3) 2px,transparent 2px) 0 0/48px 48px, linear-gradient(rgba(255,255,255,.3) 2px,transparent 2px) 0 0/48px 48px, radial-gradient(circle,rgba(124,58,237,.5) 0 5px,transparent 6px) 0 0/48px 48px, linear-gradient(135deg,#c084fc,#818cf8)",
        "linear-gradient(135deg,#a855f7,#6366f1)", "#7c3aed", "#ede9fe",
    ),
    "Sunset Ripple": make_design(
        "repeating-radial-gradient(circle at 15% 10%,rgba(255,255,255,.34) 0 3px,transparent 4px 34px), linear-gradient(145deg,#fbbf24,#fb7185 58%,#c084fc)",
        "linear-gradient(135deg,#f59e0b,#f43f5e)", "#e11d48", "#ffedd5",
    ),
    "Ocean Scales": make_design(
        "radial-gradient(circle at 50% 100%,transparent 28px,rgba(255,255,255,.38) 29px 36px,transparent 37px) 0 0/72px 44px, linear-gradient(145deg,#38bdf8,#2dd4bf)",
        "linear-gradient(135deg,#0ea5e9,#14b8a6)", "#0891b2", "#cffafe",
    ),
    "Lemon Pop": make_design(
        "radial-gradient(circle,rgba(17,24,39,.18) 0 3px,transparent 4px) 0 0/28px 28px, linear-gradient(135deg,#fde047,#a3e635)",
        "linear-gradient(135deg,#facc15,#84cc16)", "#4d7c0f", "#ecfccb",
    ),
    "Ruby Weave": make_design(
        "repeating-linear-gradient(45deg,rgba(255,255,255,.24) 0 6px,transparent 6px 28px), repeating-linear-gradient(-45deg,rgba(136,19,55,.18) 0 6px,transparent 6px 28px), linear-gradient(145deg,#fb7185,#f472b6)",
        "linear-gradient(135deg,#f43f5e,#ec4899)", "#be123c", "#ffe4e6",
    ),
    "Indigo Rings": make_design(
        "repeating-radial-gradient(circle at 75% 20%,transparent 0 22px,rgba(255,255,255,.34) 23px 28px,transparent 29px 54px), linear-gradient(135deg,#818cf8,#a78bfa)",
        "linear-gradient(135deg,#6366f1,#8b5cf6)", "#4f46e5", "#e0e7ff",
    ),
}

DESIGN_NAMES = list(DESIGNS)
selected_design = st.session_state.get("design_choice", DESIGN_NAMES[0])
DESIGN = DESIGNS.get(selected_design, DESIGNS[DESIGN_NAMES[0]])

st.markdown(
    f"""
    <style>
        .stApp, [data-testid="stAppViewContainer"] {{
            background: {DESIGN["app_bg"]};
            color: {DESIGN["text"]};
        }}
        [data-testid="stHeader"] {{background: transparent;}}
        .block-container {{padding-top: 1.35rem; padding-bottom: 2.5rem; max-width: 1480px;}}
        h1 {{
            color: {DESIGN["text"]} !important;
            font-size: clamp(2rem, 4vw, 3.15rem) !important;
            letter-spacing: -0.055em;
            line-height: 1.02 !important;
            margin: 0.2rem 0 0.35rem !important;
        }}
        h2 {{
            color: {DESIGN["text"]} !important;
            font-size: 1.32rem !important;
            letter-spacing: -0.02em;
            margin-top: 1.45rem !important;
        }}
        p, label {{color: {DESIGN["muted"]};}}
        .hero-kicker {{
            color: #0f766e;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }}
        [data-testid="stMetric"] {{
            background: {DESIGN["card_bg"]};
            border: 1px solid {DESIGN["border"]};
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: {DESIGN["shadow"]};
            backdrop-filter: blur(16px);
            transition: transform 160ms ease, box-shadow 160ms ease;
        }}
        [data-testid="stMetric"]:hover {{transform: translateY(-3px);}}
        [data-testid="stMetricLabel"] {{font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em;}}
        [data-testid="stMetricLabel"] *,
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {{color: #000000 !important;}}
        [data-testid="stMetricValue"] {{font-size: 1.65rem; font-weight: 760;}}
        .status-line {{
            display: inline-flex;
            align-items: center;
            color: {DESIGN["muted"]};
            background: {DESIGN["status_bg"]};
            border: 1px solid {DESIGN["border"]};
            border-radius: 999px;
            padding: 0.42rem 0.78rem;
            font-size: 0.78rem;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
            backdrop-filter: blur(12px);
        }}
        .status-dot {{
            width: 7px;
            height: 7px;
            margin-right: 0.5rem;
            border-radius: 50%;
            background: #16a34a;
            box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.12);
        }}
        div[data-testid="stDataFrame"],
        [data-testid="stPlotlyChart"] {{
            background: {DESIGN["card_bg"]};
            border: 1px solid {DESIGN["border"]};
            border-radius: 16px;
            box-shadow: {DESIGN["shadow"]};
            overflow: hidden;
        }}
        .stButton button[kind="primary"] {{
            color: #000000 !important;
            background: {DESIGN["button_bg"]};
            border: 0;
            border-radius: 12px;
            min-height: 2.65rem;
            font-weight: 750;
            box-shadow: 0 8px 20px rgba(15, 118, 110, 0.18);
        }}
        .stButton button[kind="primary"] p,
        .stButton button[kind="primary"] span {{color: #000000 !important;}}
        .actor-title {{
            color: #000000 !important;
            font-size: 1rem;
            font-weight: 800;
            margin: 0.2rem 0 0.65rem;
        }}
        [data-testid="stTable"] {{
            background: {DESIGN["card_bg"]};
            border: 1px solid {DESIGN["border"]};
            border-radius: 14px;
            box-shadow: {DESIGN["shadow"]};
            overflow: hidden;
        }}
        [data-testid="stTable"] th {{color: #000000 !important;}}
        div[data-baseweb="select"] > div {{
            border-radius: 12px;
            border-color: {DESIGN["border"]};
        }}

        section[data-testid="stSidebar"] {{
            background: rgba(255, 255, 255, 0.74);
            border-right: 1px solid {DESIGN["border"]};
            backdrop-filter: blur(20px);
        }}
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{color: #000000 !important;}}
        .nav-eyebrow {{font-size: .7rem; font-weight: 850; letter-spacing: .16em; text-transform: uppercase; color: #475569; margin: .3rem 0 .8rem;}}
        .index-nav {{display: grid; gap: .72rem; margin: .2rem 0 1.2rem;}}
        .index-nav-link {{
            display: block; padding: .95rem 1rem; border-radius: 16px; text-decoration: none !important;
            color: #000000 !important; font-weight: 800; border: 1px solid {DESIGN["border"]};
            background: rgba(255,255,255,.76); box-shadow: 0 8px 22px rgba(15,23,42,.08);
            transition: transform 150ms ease, box-shadow 150ms ease, background 150ms ease;
        }}
        .index-nav-link:hover {{transform: translateY(-2px); box-shadow: 0 12px 28px rgba(15,23,42,.13);}}
        .index-nav-link.active {{background: {DESIGN["button_bg"]}; border-color: transparent;}}
        .index-nav-small {{display:block; margin-top:.18rem; color:#334155; font-size:.72rem; font-weight:650;}}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown('<div class="nav-eyebrow">Index-Auswahl</div>', unsafe_allow_html=True)
    nav_links = []
    for key, config in INDEX_CONFIGS.items():
        active = " active" if key == INDEX_KEY else ""
        nav_links.append(
            f'<a class="index-nav-link{active}" href="?index={key}" target="_self">'
            f'{escape(config["nav_label"])}'
            f'<span class="index-nav-small">Tagesbeiträge öffnen →</span></a>'
        )
    st.markdown('<div class="index-nav">' + "".join(nav_links) + '</div>', unsafe_allow_html=True)
    st.caption("Wähle links deinen Markt. Alle drei Seiten nutzen denselben Aufbau und dieselbe Design-Auswahl.")


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
            f"In {path.name} fehlen Spalten: " + ", ".join(sorted(missing))
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
        raise DashboardDataError(f"Ungültige Werte in {path.name}, Zeile(n): {rows}")
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


def timestamp_in_market(index_value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(index_value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(INDEX["timezone"])
    else:
        timestamp = timestamp.tz_convert(INDEX["timezone"])
    return timestamp


def date_in_market(index_value: object):
    return timestamp_in_market(index_value).date()


def quote_from_series(intraday: pd.Series, daily: pd.Series) -> dict[str, object]:
    intraday = intraday.dropna()
    daily = daily.dropna()

    if not intraday.empty:
        current = float(intraday.iloc[-1])
        quote_timestamp = timestamp_in_market(intraday.index[-1])
        trade_date = quote_timestamp.date()
    elif not daily.empty:
        current = float(daily.iloc[-1])
        quote_timestamp = timestamp_in_market(daily.index[-1])
        trade_date = quote_timestamp.date()
    else:
        return {
            "current": float("nan"),
            "previous": float("nan"),
            "performance": float("nan"),
            "timestamp": "",
        }

    previous_candidates = daily[
        [date_in_market(index_value) < trade_date for index_value in daily.index]
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
    return {
        "current": current,
        "previous": previous,
        "performance": performance,
        "timestamp": quote_timestamp.isoformat(),
    }


def fetch_one_symbol(symbol: str) -> dict[str, object]:
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
        return {
            "current": float("nan"),
            "previous": float("nan"),
            "performance": float("nan"),
            "timestamp": "",
        }


def download_symbol_chunks(symbols: list[str], period: str, interval: str) -> pd.DataFrame:
    """Lädt große Indexlisten in handlichen Paketen, um URL- und Anbieterlimits zu vermeiden."""
    chunks: list[pd.DataFrame] = []
    for start in range(0, len(symbols), 75):
        try:
            part = yf.download(
                symbols[start : start + 75],
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
                prepost=False,
            )
        except Exception:
            continue
        if part is not None and not part.empty:
            chunks.append(part)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, axis=1) if len(chunks) > 1 else chunks[0]


@st.cache_data(ttl=60, show_spinner=False)
def fetch_market_data(
    tickers: tuple[str, ...], index_ticker: str
) -> tuple[pd.DataFrame, float, str, list[str], pd.DataFrame]:
    symbols = list(dict.fromkeys([*tickers, index_ticker]))
    batch_errors: list[str] = []

    try:
        daily_data = download_symbol_chunks(symbols, period="1mo", interval="1d")
    except Exception as exc:
        daily_data = pd.DataFrame()
        batch_errors.append(f"Tagesdaten: {exc}")

    try:
        intraday_data = download_symbol_chunks(symbols, period="1d", interval="5m")
    except Exception as exc:
        intraday_data = pd.DataFrame()
        batch_errors.append(f"Intraday-Daten: {exc}")

    quotes: dict[str, dict[str, object]] = {}
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
    retry_symbols = missing_symbols if len(missing_symbols) <= 60 else missing_symbols[:24]
    if retry_symbols:
        # Bei sehr großen Indizes werden nur einige Lücken einzeln nachgeladen, um Yahoo nicht zu überlasten.
        with ThreadPoolExecutor(max_workers=min(8, len(retry_symbols))) as executor:
            futures = {executor.submit(fetch_one_symbol, symbol): symbol for symbol in retry_symbols}
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
    dax_level = quotes[index_ticker]["current"]
    quote_times = [
        pd.Timestamp(quotes[symbol]["timestamp"])
        for symbol in tickers
        if quotes[symbol].get("timestamp")
    ]
    market_timestamp = min(quote_times) if quote_times else None
    timestamp = (
        market_timestamp.strftime("%d.%m.%Y, %H:%M Uhr")
        if market_timestamp is not None
        else "nicht verfügbar"
    )

    dax_intraday = extract_close(intraday_data, index_ticker)
    dax_chart = pd.DataFrame(
        {
            "Zeit": [timestamp_in_market(index_value) for index_value in dax_intraday.index],
            "DAX": dax_intraday.astype(float).tolist(),
        }
    )

    messages = []
    if unavailable:
        preview = ", ".join(unavailable[:18])
        more = f" … und {len(unavailable) - 18} weitere" if len(unavailable) > 18 else ""
        messages.append("Keine vollständigen Kursdaten für: " + preview + more)
    if batch_errors and unavailable:
        messages.extend(batch_errors)
    return pd.DataFrame(rows), dax_level, timestamp, messages, dax_chart


def points_text(value: float) -> str:
    return "–" if pd.isna(value) else f"{format_de(value, 2, True)} Pkt."


def make_dax_chart(dax_chart: pd.DataFrame):
    chart_data = dax_chart.dropna(subset=["Zeit", "DAX"]).sort_values("Zeit").copy()
    first_value = float(chart_data["DAX"].iloc[0])
    last_value = float(chart_data["DAX"].iloc[-1])
    change_pct = (last_value / first_value - 1.0) * 100.0 if first_value else 0.0
    positive = last_value >= first_value
    line_color = "#16a34a" if positive else "#dc2626"
    fill_color = "rgba(22, 163, 74, 0.11)" if positive else "rgba(220, 38, 38, 0.10)"

    lower = float(chart_data["DAX"].min())
    upper = float(chart_data["DAX"].max())
    span = max(upper - lower, max(abs(last_value), 1.0) * 0.001)
    y_range = [lower - span * 0.30, upper + span * 0.35]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=chart_data["Zeit"],
            y=chart_data["DAX"],
            mode="lines",
            line=dict(color=line_color, width=2.5, shape="spline"),
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate="<b>%{y:,.2f} Punkte</b><br>%{x|%H:%M} Uhr<extra></extra>",
        )
    )
    figure.add_hline(
        y=first_value,
        line_width=1,
        line_dash="dot",
        line_color=DESIGN["muted"],
        opacity=0.55,
    )
    figure.update_layout(
        height=250,
        margin=dict(l=18, r=18, t=58, b=18),
        title=dict(
            text=f"<b>{INDEX['short_label']} Intraday</b> · {format_de(change_pct, 2, True)} % heute",
            x=0.02,
            xanchor="left",
            font=dict(size=16, color=DESIGN["text"]),
        ),
        plot_bgcolor=DESIGN["chart_bg"],
        paper_bgcolor=DESIGN["chart_bg"],
        font=dict(color=DESIGN["text"]),
        hovermode="x unified",
        showlegend=False,
        yaxis=dict(
            range=y_range,
            side="right",
            gridcolor=DESIGN["grid"],
            zeroline=False,
            tickformat=",.0f",
            title="",
        ),
        xaxis=dict(
            tickformat="%H:%M",
            showgrid=False,
            zeroline=False,
            title="",
        ),
    )
    return figure


def make_bar_chart(valid: pd.DataFrame):
    if len(valid) > INDEX["chart_limit"]:
        half = INDEX["chart_limit"] // 2
        chart_data = pd.concat(
            [valid.nsmallest(half, "DAX_Punkte"), valid.nlargest(half, "DAX_Punkte")],
            ignore_index=True,
        ).drop_duplicates(subset="Ticker")
    else:
        chart_data = valid.copy()
    chart_data = chart_data.sort_values("DAX_Punkte", ascending=True).copy()
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
        labels={"DAX_Punkte": f"Geschätzter {INDEX['short_label']}-Punktebeitrag", "Unternehmen": ""},
    )
    figure.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>Ticker: %{customdata[0]}"
            "<br>Gewichtung: %{customdata[1]:.2f} %"
            "<br>Tagesperformance: %{customdata[2]:+.2f} %"
            f"<br>{INDEX['short_label']}-Beitrag: %{{x:+.2f}} Punkte<extra></extra>"
        ),
    )
    figure.update_layout(
        height=max(720, 23 * len(chart_data)),
        margin=dict(l=10, r=50, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        plot_bgcolor=DESIGN["chart_bg"],
        paper_bgcolor=DESIGN["chart_bg"],
        bargap=0.24,
        font=dict(size=12, color=DESIGN["text"]),
    )
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=order,
        autorange="reversed",
        tickfont=dict(size=11),
    )
    figure.update_xaxes(zeroline=True, zerolinecolor="#64748b", gridcolor=DESIGN["grid"])
    return figure


def top_list(frame: pd.DataFrame, direction: str) -> pd.DataFrame:
    if direction == "negative":
        result = frame[frame["DAX_Punkte"] < 0].nsmallest(5, "DAX_Punkte")
    else:
        result = frame[frame["DAX_Punkte"] > 0].nlargest(5, "DAX_Punkte")
    result = result[["Unternehmen", "Tagesperformance_pct", "DAX_Punkte"]].copy()
    result.columns = ["Unternehmen", "Heute", f"{INDEX['short_label']}-Punkte"]
    return result


def style_top_list(frame: pd.DataFrame):
    points_column = f"{INDEX['short_label']}-Punkte"
    return frame.style.format(
        {
            "Heute": lambda value: "–" if pd.isna(value) else f"{format_de(value, 2, True)} %",
            points_column: points_text,
        },
        na_rep="–",
    ).map(
        lambda value: "color: #15803d; font-weight: 600"
        if pd.notna(value) and value > 0
        else "color: #b91c1c; font-weight: 600",
        subset=[points_column],
    ).hide(axis="index")

# Kopfzeile, Design-Proben und Aktualisierung
title_column, design_column, action_column = st.columns([4.2, 1.15, 1.35])
with title_column:
    st.markdown(
        f'<div class="hero-kicker">Market Pulse · {escape(INDEX["market_label"])}</div>',
        unsafe_allow_html=True,
    )
    st.title(f'Wie bewegt sich der {INDEX["short_label"]}?')
    st.caption(f'Geschätzte gewichtete Tagesbeiträge aller {INDEX["constituents"]}')
with design_column:
    st.selectbox(
        "Design-Probe",
        DESIGN_NAMES,
        key="design_choice",
        help="Aurora plus zehn kräftige Farb- und Musterdesigns zum direkten Ausprobieren.",
    )
with action_column:
    st.caption("Kursdaten")
    if st.button(
        "↻ Kurse neu laden",
        type="primary",
        use_container_width=True,
        help="Verwirft den 60-Sekunden-Zwischenspeicher und fragt Yahoo Finance sofort erneut ab.",
    ):
        fetch_market_data.clear()
        st.rerun()

try:
    weights = load_weights(WEIGHTS_FILE)
except DashboardDataError as exc:
    st.error(str(exc))
    st.info(
        f'Die Datei {WEIGHTS_FILE.name} muss die Spalten Unternehmen, Ticker und Gewichtung_pct enthalten.'
    )
    st.stop()

with st.spinner(f'Kurse und {INDEX["short_label"]}-Stand werden geladen …'):
    market_prices, dax_level, quote_time, fetch_messages, dax_chart = fetch_market_data(
        tuple(weights["Ticker"].tolist()), DAX_TICKER
    )

data = weights.merge(market_prices, on="Ticker", how="left")
if INDEX["weight_mode"] == "price":
    # Der Dow ist preisgewichtet: die Gewichte werden aus den geladenen Kursen frisch berechnet.
    price_sum = float(data["Aktueller_Kurs"].dropna().sum())
    if price_sum > 0 and data["Aktueller_Kurs"].notna().all():
        data["Gewichtung_pct"] = data["Aktueller_Kurs"] / price_sum * 100.0
    else:
        stored_sum = float(data["Gewichtung_pct"].sum())
        if stored_sum > 0:
            data["Gewichtung_pct"] = data["Gewichtung_pct"] / stored_sum * 100.0

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
st.markdown(
    f'<span class="status-line" title="Zeitpunkt des ältesten zuletzt verwendeten Aktienkurses">'
    f'<span class="status-dot"></span>Kursstand: {escape(quote_time)} · '
    f'{escape(INDEX["source"])} · {escape(INDEX["delay"])} · {len(valid)}/{len(data)} Aktien</span>',
    unsafe_allow_html=True,
)

if fetch_messages:
    st.warning(" | ".join(fetch_messages))
if pd.isna(dax_level):
    st.error(
        f'Der aktuelle {INDEX["short_label"]}-Stand konnte nicht geladen werden. Kurse werden soweit möglich angezeigt; '
        "Punktebeiträge stehen erst nach einem erfolgreichen Abruf zur Verfügung."
    )

kpi_columns = st.columns(4)
kpis = [
    (f'{INDEX["short_label"]}-Stand', "–" if pd.isna(dax_level) else f"{format_de(dax_level, 2)} Pkt."),
    ("Negative", points_text(negative_points) if not valid.empty else "–"),
    ("Positive", points_text(positive_points) if not valid.empty else "–"),
    ("Nettoeffekt", points_text(net_points) if not valid.empty else "–"),
]
for column, (label, value) in zip(kpi_columns, kpis):
    column.metric(label, value)

if dax_chart.empty:
    st.info(f'Für den kompakten {INDEX["short_label"]}-Intraday-Chart sind aktuell keine Kursdaten verfügbar.')
else:
    st.plotly_chart(
        make_dax_chart(dax_chart),
        use_container_width=True,
        config={"displayModeBar": False, "displaylogo": False},
    )

if not valid.empty:
    st.subheader("Die stärksten Akteure")
    negative_column, positive_column = st.columns(2)
    with negative_column:
        st.markdown('<div class="actor-title">Top 5</div>', unsafe_allow_html=True)
        negative_top = top_list(valid, "negative")
        if negative_top.empty:
            st.info("Heute gibt es aktuell keine negativen Beiträge.")
        else:
            st.table(style_top_list(negative_top))
    with positive_column:
        st.markdown('<div class="actor-title">Flop 5</div>', unsafe_allow_html=True)
        positive_top = top_list(valid, "positive")
        if positive_top.empty:
            st.info("Heute gibt es aktuell keine positiven Beiträge.")
        else:
            st.table(style_top_list(positive_top))

    st.subheader(f'{INDEX["short_label"]} Werte')
    if len(valid) > INDEX["chart_limit"]:
        half = INDEX["chart_limit"] // 2
        st.caption(
            f"Für eine lesbare Grafik werden die {half} stärksten negativen und "
            f"{half} stärksten positiven Beiträge gezeigt."
        )
    st.plotly_chart(make_bar_chart(valid), use_container_width=True, config={"displaylogo": False})
else:
    st.info(f'Sobald Kursdaten verfügbar sind, erscheint hier die {INDEX["short_label"]}-Werte-Grafik.')

weight_sum = float(data["Gewichtung_pct"].sum())
if INDEX_KEY == "sp500":
    weight_source_note = "Gewichte aus den SPY-Holdings von State Street, Stand 26.06.2026."
elif INDEX_KEY == "dow":
    weight_source_note = "Der preisgewichtete Dow wird aus den aktuell geladenen Aktienkursen gewichtet."
else:
    weight_source_note = f"Gewichte aus der lokalen Datei {INDEX['weights_file']}."

st.caption(
    f"Gewichtungssumme: {format_de(weight_sum, 2)} %. "
    + weight_source_note
    + " Die Punktebeiträge sind Näherungswerte, keine offizielle Indexberechnung. "
    + "Yahoo-Finance-Kurse können verzögert sein. Keine Anlageberatung."
)
