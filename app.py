"""
GSE Daily Analytics — single-file Streamlit app
Run with:  streamlit run gse_consolidated.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
import os
from datetime import datetime, timezone
from functools import lru_cache

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

GSE_API     = "https://dev.kwayisi.org/apis/gse"
FALLBACK_URL = "https://african-markets.com/en/stock-markets/gse/listed-companies"
HEADERS     = {"User-Agent": "Mozilla/5.0 (GSE Analytics App)"}

# SECTOR_MAP defined below after _GSE_COMPANIES

CHART_COLORS = ["#378ADD", "#1D9E75", "#EF9F27", "#E24B4A", "#7F77DD", "#D85A30"]
PERIOD_DAYS  = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "All": 99999}


# ── Market hours ──────────────────────────────────────────────────────────────

def market_is_open() -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    opens  = now.replace(hour=10, minute=0, second=0, microsecond=0)
    closes = now.replace(hour=15, minute=0, second=0, microsecond=0)
    return opens <= now <= closes


# ── Column name aliases (covers all known GSE API variants) ─────────────────

# Maps every known raw column name → our standard name
# ── Column normalisation ─────────────────────────────────────────────────────
# The GSE API /live endpoint returns:
#   "name"   = ticker symbol (e.g. "GCB", "MTNGH")  ← NOT the company name
#   "price"  = current price
#   "change" = price change % (0 for unchanged stocks)
#   "volume" = shares traded
# Company full names come from /equities/<symbol> profile endpoint.

_COL_ALIASES = {
    # ticker / symbol
    "ticker": "symbol", "code": "symbol", "equity": "symbol",
    # company full name (scraper sources)
    "company": "name", "stock": "name", "description": "name",
    # price
    "closeprice": "price", "close": "price", "last price": "price",
    "lastprice": "price", "last": "price", "currentprice": "price",
    # change %
    "pricechg": "change", "chg%": "change", "change%": "change",
    "changepct": "change", "percentchange": "change", "pct_change": "change",
    "pricechange": "change", "chgpct": "change",
    # volume
    "vol": "volume", "tradedvolume": "volume", "shares": "volume",
}

# Cache of symbol -> full company name fetched from /equities/<symbol>
_COMPANY_NAMES: dict = {}


# ── Full GSE listed company database ─────────────────────────────────────────
_GSE_COMPANIES = {
    "ACCESS": {
        "name":        "Access Bank Ghana Plc",
        "listed":      "21/12/2022",
        "capital":     "GHS 400 million",
        "issued":      "118,093,134",
        "authorised":  "173,947,596 ordinary shares",
        "sector":      "Financials",
    },
    "ADB": {
        "name":        "Agricultural Development Bank",
        "listed":      "12/12/2016",
        "capital":     "—",
        "issued":      "—",
        "authorised":  "—",
        "sector":      "Financials",
    },
    "AGA": {
        "name":        "AngloGold Ashanti Plc",
        "listed":      "27/04/2004",
        "capital":     "ZAR 4,899,021,716.98",
        "issued":      "417,339,100 ordinary shares",
        "authorised":  "600,000,000",
        "sector":      "Mining",
    },
    "ALW": {
        "name":        "Aluworks Ltd",
        "listed":      "29/11/1996",
        "capital":     "GHS —",
        "issued":      "236,685,180 ordinary shares",
        "authorised":  "1,000,000,000 ordinary shares",
        "sector":      "Manufacturing",
    },
    "ALLGH": {
        "name":        "Atlantic Lithium Limited",
        "listed":      "13/05/2024",
        "capital":     "AUD$ 129,873,021",
        "issued":      "649,669,053",
        "authorised":  "—",
        "sector":      "Mining",
    },
    "ASG": {
        "name":        "Asante Gold Corporation",
        "listed":      "29/06/2022",
        "capital":     "C$ 20,366,275",
        "issued":      "315,010,000",
        "authorised":  "—",
        "sector":      "Mining",
    },
    "BOPP": {
        "name":        "Benso Oil Palm Plantation Ltd",
        "listed":      "16/04/2004",
        "capital":     "GHS —",
        "issued":      "34,800,000",
        "authorised":  "50,000,000 shares of no par value",
        "sector":      "Agribusiness",
    },
    "CAL": {
        "name":        "CalBank PLC",
        "listed":      "05/11/2004",
        "capital":     "GHS —",
        "issued":      "548,260,000",
        "authorised":  "1,000,000,000",
        "sector":      "Financials",
    },
    "CLYD": {
        "name":        "Clydestone (Ghana) Limited",
        "listed":      "19/05/2004",
        "capital":     "GHS —",
        "issued":      "34,000,000",
        "authorised":  "100,000,000",
        "sector":      "Real Estate",
    },
    "CMLT": {
        "name":        "Camelot Ghana Ltd",
        "listed":      "17/09/1999",
        "capital":     "GHS 217,467",
        "issued":      "6,830,000",
        "authorised":  "20,000,000",
        "sector":      "Manufacturing",
    },
    "CPC": {
        "name":        "Cocoa Processing Company",
        "listed":      "14/02/2003",
        "capital":     "GHS —",
        "issued":      "2,038,070,000",
        "authorised":  "20,000,000,000",
        "sector":      "Consumer Goods",
    },
    "DASPHARMA": {
        "name":        "Dannex Ayrton Starwin Plc",
        "listed":      "—",
        "capital":     "—",
        "issued":      "—",
        "authorised":  "—",
        "sector":      "Healthcare",
    },
    "EGH": {
        "name":        "Ecobank Ghana PLC",
        "listed":      "13/07/2022",
        "capital":     "GHS 226.64 million",
        "issued":      "293,230,000",
        "authorised":  "500,000,000",
        "sector":      "Financials",
    },
    "EGL": {
        "name":        "Enterprise Group PLC",
        "listed":      "—",
        "capital":     "GHS 258,886,100",
        "issued":      "170,892,825",
        "authorised":  "200,000,000",
        "sector":      "Insurance",
    },
    "ETI": {
        "name":        "Ecobank Transnational Inc",
        "listed":      "11/09/2006",
        "capital":     "US$ 867,714,000",
        "issued":      "24,067,750,000",
        "authorised":  "800,000,000",
        "sector":      "Financials",
    },
    "FML": {
        "name":        "Fan Milk Limited",
        "listed":      "18/10/1991",
        "capital":     "GHS —",
        "issued":      "116,210,000",
        "authorised":  "200,000,000",
        "sector":      "Consumer Goods",
    },
    "GCB": {
        "name":        "Ghana Commercial Bank Limited",
        "listed":      "17/05/1996",
        "capital":     "GHC 72,000,000",
        "issued":      "265,000,000",
        "authorised":  "1,500,000,000",
        "sector":      "Financials",
    },
    "GGBL": {
        "name":        "Guinness Ghana Breweries Plc",
        "listed":      "23/08/1991",
        "capital":     "GHS 272,879,113.44",
        "issued":      "100,000,000",
        "authorised":  "—",
        "sector":      "Consumer Goods",
    },
    "GOIL": {
        "name":        "GOIL PLC",
        "listed":      "16/11/2007",
        "capital":     "GHS —",
        "issued":      "391,860,000",
        "authorised":  "1,000,000,000",
        "sector":      "Oil & Gas",
    },
    "MAC": {
        "name":        "Mega African Capital Limited",
        "listed":      "23/04/2014",
        "capital":     "GHS —",
        "issued":      "9,950,000",
        "authorised":  "—",
        "sector":      "Financials",
    },
    "MTNGH": {
        "name":        "MTN Ghana",
        "listed":      "05/09/2018",
        "capital":     "GHS 1,363,000,000",
        "issued":      "—",
        "authorised":  "100,000,000,000",
        "sector":      "Telecoms",
    },
    "PBC": {
        "name":        "Produce Buying Company Ltd",
        "listed":      "17/05/2000",
        "capital":     "GHC 4,914,377",
        "issued":      "480,000,000",
        "authorised":  "20,000,000,000",
        "sector":      "Agribusiness",
    },
    "RBGH": {
        "name":        "Republic Bank (Ghana) PLC",
        "listed":      "05/10/1994",
        "capital":     "GHC 401,190,624",
        "issued":      "851,966,373",
        "authorised":  "1,000,000,000",
        "sector":      "Financials",
    },
    "SCB": {
        "name":        "Standard Chartered Bank Ghana Ltd",
        "listed":      "—",
        "capital":     "GHS —",
        "issued":      "115,510,000 ordinary + 17,480,000 pref",
        "authorised":  "250,000,000 ordinary",
        "sector":      "Financials",
    },
    "SIC": {
        "name":        "SIC Insurance Company Limited",
        "listed":      "25/01/2008",
        "capital":     "GHC 2,500,000",
        "issued":      "195,650,000",
        "authorised":  "500,000,000",
        "sector":      "Insurance",
    },
    "SOGEGH": {
        "name":        "Societe Generale Ghana Limited",
        "listed":      "13/10/1995",
        "capital":     "GHC 62,393,557.80",
        "issued":      "429,060,000",
        "authorised":  "500,000,000",
        "sector":      "Financials",
    },
    "SWL": {
        "name":        "Sam Wood Ltd",
        "listed":      "24/04/2002",
        "capital":     "GHC 220,990",
        "issued":      "21,830,000",
        "authorised":  "100,000,000",
        "sector":      "Manufacturing",
    },
    "TBL": {
        "name":        "Trust Bank Limited (The Gambia)",
        "listed":      "15/11/2002",
        "capital":     "Dalasis 200,000,000",
        "issued":      "22,750,000",
        "authorised":  "200,000,000",
        "sector":      "Financials",
    },
    "TLW": {
        "name":        "Tullow Oil Plc",
        "listed":      "27/07/2011",
        "capital":     "GBP 144,728,808.80",
        "issued":      "906,960,000",
        "authorised":  "—",
        "sector":      "Oil & Gas",
    },
    "TOTAL": {
        "name":        "TotalEnergies Ghana PLC",
        "listed":      "—",
        "capital":     "GHS 51,222,715.01",
        "issued":      "111,874,072",
        "authorised":  "111,874,072",
        "sector":      "Oil & Gas",
    },
    "UNIL": {
        "name":        "Unilever Ghana PLC",
        "listed":      "—",
        "capital":     "GHS —",
        "issued":      "62,500,000",
        "authorised":  "100,000,000",
        "sector":      "Consumer Goods",
    },
}

# Quick name lookup (backward compat with existing code)
_GSE_NAMES = {k: v["name"] for k, v in _GSE_COMPANIES.items()}


# ── Company descriptions (for Stock Detail "About" section) ─────────────────
_GSE_ABOUT = {
    "GCB":    "GCB Bank Limited is the largest indigenous Ghanaian bank by total assets. Established in 1953, it operates a nationwide network of branches and provides retail, commercial, and corporate banking services across Ghana.",
    "MTNGH":  "MTN Ghana (Scancom PLC) is the largest telecommunications company in Ghana, providing mobile voice, data, and financial services (MoMo) to millions of subscribers. Listed on the GSE in 2018.",
    "GOIL":   "GOIL PLC (Ghana Oil Company) is Ghana's leading petroleum marketing company, operating over 200 service stations and providing bulk fuel, lubricants, and aviation fueling services nationwide.",
    "EGH":    "Ecobank Ghana PLC is part of the pan-African Ecobank Group, providing banking services across retail, corporate, and investment banking segments. One of the largest banks by branch network in Ghana.",
    "ETI":    "Ecobank Transnational Incorporated (ETI) is the parent company of the Ecobank Group, one of Africa's largest banking groups with presence in 35 African countries.",
    "GGBL":   "Guinness Ghana Breweries PLC manufactures and markets premium beers and malt beverages in Ghana. Products include Guinness, Star Beer, Orijin, and Malta Guinness.",
    "TOTAL":  "TotalEnergies Ghana PLC is the leading oil marketing company in Ghana, operating a network of service stations and providing lubricants, bitumen, and industrial fuel products.",
    "SCB":    "Standard Chartered Bank Ghana Ltd is one of the oldest and most prestigious banks in Ghana, providing a full range of financial services to individuals, SMEs, and corporate clients.",
    "CAL":    "CalBank PLC is a leading commercial bank in Ghana focused on retail, SME, and corporate banking. Known for its innovative digital banking products and growing branch network.",
    "SOGEGH": "Societe Generale Ghana Limited is part of the global Societe Generale Group, offering retail, corporate, and investment banking services to individuals and businesses in Ghana.",
    "ACCESS": "Access Bank Ghana PLC is a subsidiary of Access Bank Group, one of Africa's largest banks. Provides retail, business, and corporate banking services across Ghana.",
    "FML":    "Fan Milk Limited is a leading manufacturer and marketer of frozen dairy and juice products in Ghana under the Fan brand. A household name with products sold through over 15,000 pushcarts.",
    "ALLGH":  "Atlantic Lithium Limited is developing the Ewoyaa Lithium Project in Ghana's Central Region — set to become Ghana's first lithium mine. The company collaborates with Piedmont Lithium and benefits from strong government support.",
    "SIC":    "SIC Insurance Company Limited is one of Ghana's oldest and largest insurance companies, offering life, non-life, and reinsurance products to individuals and corporate clients.",
    "BOPP":   "Benso Oil Palm Plantation Ltd operates one of the largest oil palm plantations in Ghana. Products include crude palm oil and palm kernel oil supplied to local and international markets.",
    "AGA":    "AngloGold Ashanti Plc is one of the world's largest gold mining companies. Operations in Ghana include the Obuasi and Iduapriem mines, which are among Africa's most productive gold mines.",
    "ASG":    "Asante Gold Corporation is a gold exploration and development company focused on projects in Ghana, including the Kubi Gold Project and Fahiakoba deposit in the Ashanti Gold Belt.",
    "EGL":    "Enterprise Group PLC is one of Ghana's leading financial services holding companies, with subsidiaries spanning life insurance (Enterprise Life), general insurance, properties, and trustees.",
    "RBGH":   "Republic Bank (Ghana) PLC, formerly HFC Bank, is a full-service commercial bank providing mortgage finance, retail banking, and corporate banking services across Ghana.",
    "UNIL":   "Unilever Ghana PLC manufactures and distributes a wide range of consumer goods including personal care products (Vaseline, Lux), home care (OMO, Sunlight), and food products (Lipton, Royco).",
    "TLW":    "Tullow Oil Plc is one of Africa's leading independent oil companies, operating the Jubilee and TEN oil fields offshore Ghana, which together produce hundreds of thousands of barrels per day.",
    "ADB":    "Agricultural Development Bank (ADB) is a state-owned development financial institution supporting Ghana's agricultural sector with affordable credit, savings, and financial services.",
    "PBC":    "Produce Buying Company Ltd is a major cocoa purchasing company in Ghana, licensed by COCOBOD to purchase and export cocoa beans from farmers across the country.",
    "CPC":    "Cocoa Processing Company (CPC) processes raw cocoa beans into semi-finished products including cocoa liquor, cocoa butter, and cocoa powder for export and domestic use.",
    "CLYD":   "Clydestone (Ghana) Limited provides information technology solutions and services to businesses and institutions in Ghana, including software development, systems integration, and ICT consulting.",
    "CMLT":   "Camelot Ghana Ltd is a printing and publishing company providing commercial printing, security printing, and office supplies to businesses and government institutions in Ghana.",
}
# Auto-build sector map now that _GSE_COMPANIES is defined
SECTOR_MAP = {k: v["sector"] for k, v in _GSE_COMPANIES.items()}
SECTOR_MAP.update({
    "AIRTELGH": "Telecoms", "TOR": "Oil & Gas",
    "HFC": "Financials",    "GSR": "Mining",
    "MOGL": "Mining",       "AYRTN": "Healthcare",
})

# ── Logo & avatar helpers (module-level so all pages can use them) ──────────
import base64 as _b64_mod, pathlib as _path_mod

# Sector-based badge colours (consistent across all cards and table)
_SC_COLORS = {
    "GCB":"#0a1f3d,#60a5fa","EGH":"#0a1f3d,#60a5fa","SCB":"#0a1f3d,#60a5fa",
    "CAL":"#0a1f3d,#60a5fa","ETI":"#0a1f3d,#60a5fa","ACCESS":"#0a1f3d,#60a5fa",
    "SOGEGH":"#0a1f3d,#60a5fa","RBGH":"#0a1f3d,#60a5fa","ADB":"#0a1f3d,#60a5fa",
    "MTNGH":"#2d1d00,#fbbf24",
    "GOIL":"#001a0d,#34d399","TOR":"#001a0d,#34d399","TOTAL":"#001a0d,#34d399",
    "GGBL":"#2d0808,#f87171","FML":"#2d0808,#f87171","UNIL":"#2d0808,#f87171",
    "BOPP":"#0d1f00,#86efac","PBC":"#0d1f00,#86efac",
    "MOGL":"#1f1000,#fb923c","GSR":"#1f1000,#fb923c","AGA":"#1f1000,#fb923c",
    "ALLGH":"#130a24,#c084fc","AYRTN":"#130a24,#c084fc","CPC":"#130a24,#c084fc",
    "SIC":"#001020,#38bdf8","ENTERPRISE":"#001020,#38bdf8",
    "CLYD":"#200010,#f472b6","HFC":"#200010,#f472b6",
    "CMLT":"#1a1000,#fb923c","ASG":"#1f1000,#fbbf24","AADS":"#0d1f00,#86efac",
    "BOPP":"#0d1f00,#86efac","CLYD":"#200010,#f472b6",
}
_AV_FALLBACK = [
    ("#0c2a4a","#38bdf8"), ("#0d2b1a","#4ade80"), ("#2a1a0c","#fb923c"),
    ("#1a0c2a","#a78bfa"), ("#2a0c1a","#f472b6"), ("#0c2a22","#34d399"),
]

# ── Logo loader ──────────────────────────────────────────────────────────
# Maps GSE ticker symbols to your actual logo filenames in the logos/ folder.
# Add more entries here as you collect more logos.
import base64, pathlib

_LOGO_FILES = {
    "ACCESS":     "accessbankghana_logo",
    "ADB":        "ADB images",
    "ALLGH":      "atlantic_lithium_limited_logo",  # closest match — update if needed
    "CAL":        "CALbank",
    "CPC":        "cocoa-processing-company",
    "DNNX":       "Dannex images",
    "EGH":        "Ecobank_Logo.svg",
    "FML":        "Fan milk-logo",
    "GCB":        "GCB",
    "AGA":        "gh-aad-logo",
    "BOPP":       "gh-bopp-logo",
    "ENTERPRISE": "gh-egl-logo",
    "PBC":        "gh-pbc-logo",
    "SIC":        "gh-sic-logo",
    "SOGEGH":     "gh-sogegh-logo",
    "TLW":        "gh-tlw-logo",
    "TOTAL":      "gh-total-logo",
    "GOIL":       "GOIL",
    "MTNGH":      "MTN",
    "GGBL":       "New_Guinness_Ghana_Logo",
    "RBGH":       "RBGH images",
    "SCB":        "Standard_Chartered-Logo.wine",
    "UNIL":       "Unilever.svg",
}

def _load_logo_b64(sym: str) -> str | None:
    """
    Returns base64 data URI for logo.
    Searches in both 'logo/' and 'logos/' folders.
    Handles filenames with spaces, dashes, underscores.
    """
    # Support both folder names
    for folder_name in ["logo", "logos"]:
        logos_dir = pathlib.Path(folder_name)
        if not logos_dir.exists():
            continue

        # Strategy 1: exact filename from map
        candidates = []
        if sym in _LOGO_FILES:
            candidates.append(_LOGO_FILES[sym])
        # Strategy 2: ticker name variants
        candidates += [sym.upper(), sym.lower(), sym]

        for base_name in candidates:
            for ext in ["png", "jpg", "jpeg", "svg", "webp", "PNG", "JPG", "SVG"]:
                path = logos_dir / f"{base_name}.{ext}"
                if path.exists():
                    mime = "image/svg+xml" if ext.lower() == "svg" else f"image/{ext.lower()}"
                    data = base64.b64encode(path.read_bytes()).decode()
                    return f"data:{mime};base64,{data}"

        # Strategy 3: fuzzy scan — strip spaces/dashes/underscores and compare
        try:
            def _normalise(s):
                return s.lower().replace("-","").replace("_","").replace(" ","").replace(".","")

            ticker_norm = _normalise(sym)
            all_files   = list(logos_dir.iterdir())

            # Exact normalised match first
            for f in all_files:
                if _normalise(f.stem) == ticker_norm:
                    ext  = f.suffix[1:].lower()
                    mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
                    return f"data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"

            # Prefix match (e.g. "accessbankghana_logo" starts with "access")
            for f in all_files:
                if _normalise(f.stem).startswith(ticker_norm) and len(ticker_norm) >= 3:
                    ext  = f.suffix[1:].lower()
                    mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
                    return f"data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"

            # Contains match (e.g. "MTN" inside "MTN Ghana Logo")
            for f in all_files:
                if ticker_norm in _normalise(f.stem) and len(ticker_norm) >= 3:
                    ext  = f.suffix[1:].lower()
                    mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
                    return f"data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"
        except Exception:
            pass

    return None

def _av(sym):
    logo_uri = _load_logo_b64(sym)
    if logo_uri:
        # Real logo image found in logos/ folder
        return f'''<div class="sc-avatar" style="background:#0d1117;border:1px solid #1e2d3d;padding:4px">
          <img src="{logo_uri}" style="width:100%;height:100%;object-fit:contain;border-radius:6px" alt="{sym}"/>
        </div>'''
    # Fallback: sector-coloured wordmark badge
    if sym in _SC_COLORS:
        bg, fg = _SC_COLORS[sym].split(",")
    else:
        i = sum(ord(c) for c in sym) % len(_AV_FALLBACK)
        bg, fg = _AV_FALLBACK[i]
    wm_big  = sym[0]
    wm_rest = sym[1:3] if len(sym) > 1 else ""
    return f"""<div class="sc-avatar" style="background:{bg};border:1px solid {fg}22;flex-direction:column;line-height:1">
      <div style="font-size:14px;font-weight:900;color:{fg};letter-spacing:-1px;font-family:Arial Black,sans-serif">{wm_big}</div>
      <div style="font-size:7px;font-weight:700;color:{fg}99;letter-spacing:1px;margin-top:-2px">{wm_rest}</div>
    </div>"""

def _company(sym, name):
    return _GSE_NAMES.get(sym, name) if name == sym else name



def _fetch_all_company_names(symbols: list) -> dict:
    """Start with hardcoded map, then enrich from API /equities endpoint."""
    names = dict(_GSE_NAMES)  # start with known names
    try:
        resp = requests.get(f"{GSE_API}/equities", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        for item in resp.json():
            raw = {k.lower(): v for k, v in item.items()}
            # API returns ticker in "name" field
            sym = str(raw.get("name", raw.get("ticker", raw.get("symbol", "")))).upper().strip()
            # Try multiple possible company name fields
            company = (
                raw.get("company") or raw.get("equity") or
                raw.get("description") or raw.get("fullname") or
                raw.get("longname") or names.get(sym, sym)
            )
            if sym and company:
                names[sym] = str(company).strip()
    except Exception:
        pass
    return names


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower().strip() for c in df.columns]
    return df.rename(columns=_COL_ALIASES)


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["price", "change", "volume"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                       .str.replace("%", "", regex=False)
                       .str.replace(",", "", regex=False)
                       .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0).astype(int)
    if "change" in df.columns:
        df["change"] = df["change"].fillna(0)
    return df


def _finalise(df: pd.DataFrame, company_names: dict = None) -> pd.DataFrame:
    """Ensure all required columns exist with correct values."""
    required = ["symbol", "name", "price", "change", "volume"]

    # API sends ticker in "name" col — detect and fix:
    # If there is no "symbol" col but there IS a "name" col with short uppercase values,
    # those are tickers, not company names.
    if "symbol" not in df.columns or df["symbol"].astype(str).str.strip().eq("").all():
        if "name" in df.columns:
            df["symbol"] = df["name"]

    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()

    # Attach full company names if available
    if company_names:
        df["name"] = df["symbol"].map(company_names).fillna(df["symbol"])
    elif "name" not in df.columns or df["name"].astype(str).str.strip().eq(df["symbol"]).all():
        # No company names yet — use symbol as placeholder
        df["name"] = df["symbol"]

    for col in ["price", "change", "volume"]:
        if col not in df.columns:
            df[col] = 0

    return df[required].dropna(subset=["price"]).reset_index(drop=True)


def _build_df(raw: pd.DataFrame, company_names: dict = None) -> pd.DataFrame:
    return _finalise(_coerce_numeric(_normalise_columns(raw.copy())), company_names)


# ── Live prices ───────────────────────────────────────────────────────────────

_LAST_RAW_COLS: list  = []
_LAST_RAW_SAMPLE: list = []
_DATA_SOURCE: str     = "none"


def get_live_prices() -> pd.DataFrame:
    """
    Source priority:
      1. GSE API /live  (tickers in "name" col, company names from /equities)
      2. african-markets.com scrape
      3. gse_history.csv (most recent date)
    """
    global _LAST_RAW_COLS, _LAST_RAW_SAMPLE, _DATA_SOURCE

    # Fetch company name lookup from /equities (best-effort, silent fail)
    company_names = _fetch_all_company_names([])

    # ── 1. GSE API ────────────────────────────────────────────────────────────
    try:
        resp = requests.get(f"{GSE_API}/live", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        raw = pd.DataFrame(resp.json())
        _LAST_RAW_COLS   = raw.columns.tolist()
        _LAST_RAW_SAMPLE = raw.head(3).to_dict("records")
        _DATA_SOURCE     = "GSE API"
        result = _build_df(raw, company_names)
        if not result.empty:
            return result
    except Exception as e:
        _DATA_SOURCE = f"GSE API failed: {e}"

    # ── 2. African-markets scrape ─────────────────────────────────────────────
    try:
        tables = pd.read_html(FALLBACK_URL)
        for tbl in tables:
            _LAST_RAW_COLS   = tbl.columns.tolist()
            _LAST_RAW_SAMPLE = tbl.head(3).to_dict("records")
            result = _build_df(tbl, company_names)
            if not result.empty and "price" in result.columns:
                _DATA_SOURCE = "african-markets.com"
                return result
    except Exception as e:
        _DATA_SOURCE = f"Scrape failed: {e}"

    # ── 3. Local CSV ──────────────────────────────────────────────────────────
    try:
        df = pd.read_csv("gse_history.csv")
        _LAST_RAW_COLS   = df.columns.tolist()
        _LAST_RAW_SAMPLE = df.head(3).to_dict("records")
        df = _normalise_columns(df)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df[df["date"] == df["date"].max()]
        if "change" not in df.columns:
            df["change"] = 0.0
        result = _build_df(df, company_names)
        if not result.empty:
            _DATA_SOURCE = "gse_history.csv"
            return result
    except Exception as e:
        _DATA_SOURCE = f"CSV failed: {e}"

    return pd.DataFrame(columns=["symbol", "name", "price", "change", "volume"])


# ── Daily CSV snapshot ───────────────────────────────────────────────────────

def save_daily_snapshot(df: pd.DataFrame, filepath: str = "gse_history.csv") -> bool:
    """
    Appends today's live prices to gse_history.csv.
    Deduplicates by date+symbol so re-runs don't create duplicate rows.
    Returns True if new rows were saved.
    """
    if df.empty:
        return False
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snap  = df.copy()
        snap["date"]      = today
        snap["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if os.path.exists(filepath):
            existing = pd.read_csv(filepath)
            # Drop today's rows for this symbol set (so we overwrite with latest)
            if "date" in existing.columns and "symbol" in existing.columns:
                existing = existing[existing["date"] != today]
            combined = pd.concat([existing, snap], ignore_index=True)
        else:
            combined = snap

        combined.to_csv(filepath, index=False)
        return True
    except Exception as e:
        return False


def load_historical_comparison(symbol: str, filepath: str = "gse_history.csv") -> pd.DataFrame:
    """
    Loads all historical daily closes for a symbol from the CSV.
    Returns DataFrame with columns: date, price, change, volume
    """
    try:
        df = pd.read_csv(filepath)
        df.columns = [c.lower().strip() for c in df.columns]
        if "symbol" not in df.columns and "name" in df.columns:
            df = df.rename(columns={"name": "symbol"})
        df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        return df.dropna(subset=["date","price"]).sort_values("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date","price","change","volume"])


# ── Historical EOD ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="Loading history…")
def get_history(symbol: str) -> pd.DataFrame:
    """
    Source priority:
      1. gse_history.csv (local — built daily by save_daily_snapshot)
      2. GSE API /equities/<symbol>/eod (online fallback)
    Returns DataFrame with columns: date, price, change, volume
    """
    frames = []

    # ── 1. Local CSV (primary — always has data if app has run before) ────────
    for csv_path in ["gse_history.csv", "data/gse_history.csv"]:
        try:
            df = pd.read_csv(csv_path)
            df = _normalise_columns(df)
            # Detect symbol column
            sym_col = next((c for c in ["symbol","name"] if c in df.columns), df.columns[0])
            mask = df[sym_col].astype(str).str.upper().str.strip() == symbol.upper().strip()
            if mask.any():
                df = df[mask].copy()
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                df = _coerce_numeric(df)
                if "volume" not in df.columns:
                    df["volume"] = 0
                if "change" not in df.columns:
                    df["change"] = df["price"].pct_change() * 100
                df = df.dropna(subset=["price","date"]).sort_values("date").reset_index(drop=True)
                if not df.empty:
                    frames.append(df)
                    break
        except Exception:
            pass

    # ── 2. GSE API EOD (online supplement) ────────────────────────────────────
    try:
        resp = requests.get(
            f"{GSE_API}/equities/{symbol.lower()}/eod",
            headers=HEADERS, timeout=10,
        )
        resp.raise_for_status()
        df = _normalise_columns(pd.DataFrame(resp.json()))
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        elif "name" in df.columns:
            df = df.rename(columns={"name": "date"})
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = _coerce_numeric(df)
        if "volume" not in df.columns:
            df["volume"] = 0
        if "change" not in df.columns:
            df["change"] = df["price"].pct_change() * 100
        df = df.dropna(subset=["price","date"]).sort_values("date").reset_index(drop=True)
        if not df.empty:
            frames.append(df)
    except Exception:
        pass

    if not frames:
        return pd.DataFrame(columns=["date","price","change","volume"])

    # Merge CSV + API data, deduplicate by date, keep latest value per date
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return combined.reset_index(drop=True)


# ── Company profile ───────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_profile(symbol: str) -> dict:
    try:
        resp = requests.get(
            f"{GSE_API}/equities/{symbol.lower()}",
            headers=HEADERS, timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


# ── Technical indicators ──────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["price"]

    # RSI (14)
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df["RSI"] = (100 - 100 / (1 + gain / loss.replace(0, float("nan")))).round(2)

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"]      = (ema12 - ema26).round(4)
    df["Signal"]    = df["MACD"].ewm(span=9, adjust=False).mean().round(4)
    df["MACD_Hist"] = (df["MACD"] - df["Signal"]).round(4)

    # Bollinger Bands (20, 2σ)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["BB_Upper"] = (sma20 + 2 * std20).round(4)
    df["BB_Lower"] = (sma20 - 2 * std20).round(4)
    df["BB_Mid"]   = sma20.round(4)

    # SMA 50
    df["SMA50"] = close.rolling(50).mean().round(4)

    return df


# ── Alerts ────────────────────────────────────────────────────────────────────

def _normalise_change(df: pd.DataFrame) -> pd.DataFrame:
    """
    GSE API sometimes returns change as a decimal fraction (0.033 = 3.3%).
    Detect and convert: if all abs values < 1 and not all zero, multiply by 100.
    """
    df = df.copy()
    chg = df["change"].dropna()
    nonzero = chg[chg != 0]
    if len(nonzero) > 0 and (nonzero.abs() < 1).all():
        df["change"] = (df["change"] * 100).round(2)
    return df


def generate_alerts(df: pd.DataFrame, thresholds: dict) -> list[dict]:
    df = _normalise_change(df)
    alerts = []
    for _, row in df.iterrows():
        chg = float(row.get("change", 0) or 0)
        sym = str(row.get("symbol", "") or row.get("name", ""))
        if chg <= thresholds["drop"]:
            alerts.append({"type": "danger",  "symbol": sym,
                "msg": f"{sym} fell {chg:.2f}% — below {thresholds['drop']}% threshold",
                "change": chg})
        elif chg >= thresholds["rise"]:
            alerts.append({"type": "success", "symbol": sym,
                "msg": f"{sym} rose {chg:.2f}% — above +{thresholds['rise']}% threshold",
                "change": chg})
    return sorted(alerts, key=lambda x: abs(x["change"]), reverse=True)


# ── Market summary ────────────────────────────────────────────────────────────

def market_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    vol = int(df["volume"].sum())
    return {
        "gainers":      int((df["change"] > 0).sum()),
        "losers":       int((df["change"] < 0).sum()),
        "unchanged":    int((df["change"] == 0).sum()),
        "total_volume": vol,
        "vol_label":    f"{vol/1_000_000:.2f}M" if vol >= 1_000_000 else f"{vol:,}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# APP CONFIG & SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="GSE Analytics Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
# Inject dark background before any component renders
st.markdown("""
<style>
html, body, [data-testid="stApp"] { background-color:#080c16 !important; }
[data-testid="stHeader"]  { background:#080c16 !important; border-bottom:1px solid #141d2e !important; }
[data-testid="stToolbar"] { background:#080c16 !important; }
/* Subtle noise texture overlay for depth */
[data-testid="stApp"]::before {
    content:""; position:fixed; inset:0; pointer-events:none;
    background:radial-gradient(ellipse at 20% 0%,rgba(56,189,248,0.03) 0%,transparent 60%),
               radial-gradient(ellipse at 80% 100%,rgba(167,139,250,0.03) 0%,transparent 60%);
    z-index:0;
}

/* ── Hide "nav" / "Navigation" radio label ── */
[data-testid="stRadio"] > label { display:none !important; }
[data-testid="stRadio"] > div   { gap:2px !important; }

/* ── Radio nav pill styling ── */
[data-testid="stRadio"] label {
    background:transparent !important;
    border-radius:8px !important;
    padding:9px 14px !important;
    margin:1px 0 !important;
    display:flex !important;
    align-items:center !important;
    cursor:pointer !important;
    font-size:13px !important;
    font-weight:500 !important;
    color:#64748b !important;
    transition:all .15s !important;
    border:1px solid transparent !important;
}
[data-testid="stRadio"] label:hover {
    background:#111827 !important;
    color:#94a3b8 !important;
}
[data-testid="stRadio"] label:has(input:checked) {
    background:#0f2744 !important;
    color:#38bdf8 !important;
    border-color:#1e3a5f !important;
}
/* Hide the radio circle dot */
[data-testid="stRadio"] label > div:first-child { display:none !important; }

/* ── Dataframe dark theme ── */
[data-testid="stDataFrame"] > div { border-radius:12px !important; overflow:hidden !important; }
.stDataFrame iframe { border-radius:12px !important; }
[data-testid="stDataFrame"] { background:#0d1117 !important; }

/* ── Sidebar refinements ── */
[data-testid="stSidebar"] { background:#0b0f1a !important; }
[data-testid="stSidebarContent"] { padding:0 12px !important; }

/* ── Main content bg ── */
.main .block-container { background:#0a0e1a !important; max-width:1400px !important; }

/* ── Hide Streamlit branding ── */
#MainMenu, footer, header { visibility:hidden !important; }
[data-testid="stDecoration"] { display:none !important; }
</style>""", unsafe_allow_html=True)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["GCB", "MTNGH"]
if "alert_thresholds" not in st.session_state:
    st.session_state.alert_thresholds = {"drop": -5.0, "rise": 2.0}
if "page" not in st.session_state:
    st.session_state.page = "Overview"
if "portfolio" not in st.session_state:
    st.session_state.portfolio = []  # list of {symbol, shares, buy_price, date}
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = None



# ═══════════════════════════════════════════════════════════════════════════════
# SHARED DATA LOAD
# ═══════════════════════════════════════════════════════════════════════════════

df_live = get_live_prices()
# Normalise change column (handles decimal fraction vs % format)
if not df_live.empty:
    df_live = _normalise_change(df_live)
    # Auto-save today's snapshot to CSV for historical comparison
    save_daily_snapshot(df_live)
symbols = sorted(df_live["symbol"].dropna().tolist()) if not df_live.empty else []

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <style>
    /* ── Global dark theme ── */
    html, body, [data-testid="stApp"] {
        background-color: #0a0e1a !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] {
        background: #0d1117 !important;
        border-right: 1px solid #1e2d3d !important;
    }
    [data-testid="stSidebar"] * { color: #cbd5e1 !important; }
    .main .block-container {
        background: #0a0e1a !important;
        padding-top: 1.5rem !important;
        max-width: 1400px !important;
    }
    /* Force ALL iframes (dataframe) to dark */
    iframe { background: #0d1117 !important; }
    /* stDataFrame wrapper */
    [data-testid="stDataFrame"] > div > div { background: #0d1117 !important; border-radius:12px !important; }
    /* Inputs */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] div,
    [data-testid="stMultiSelect"] div {
        background: #161b27 !important;
        border-color: #1e2d3d !important;
        color: #e2e8f0 !important;
    }
    /* Radio nav pills */
    [data-testid="stRadio"] label {
        background: transparent !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
        margin: 2px 0 !important;
        display: block !important;
        cursor: pointer !important;
        transition: background .15s !important;
        font-size: 13px !important;
    }
    [data-testid="stRadio"] label:hover { background: #1a2332 !important; }
    [data-testid="stRadio"] [aria-checked="true"] + div label,
    [data-testid="stRadio"] label:has(input:checked) {
        background: #1a2d4a !important;
        color: #38bdf8 !important;
    }
    /* Buttons */
    [data-testid="stButton"] button {
        background: #161b27 !important;
        border: 1px solid #1e2d3d !important;
        color: #94a3b8 !important;
        border-radius: 8px !important;
        font-size: 12px !important;
    }
    [data-testid="stButton"] button:hover {
        background: #1a2332 !important;
        border-color: #38bdf8 !important;
        color: #38bdf8 !important;
    }
    /* Sliders */
    [data-testid="stSlider"] [role="slider"] { background: #38bdf8 !important; }
    /* Divider */
    hr { border-color: #1e2d3d !important; }
    /* Scrollbar */
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #0d1117; }
    ::-webkit-scrollbar-thumb { background: #1e2d3d; border-radius: 2px; }
    /* Dataframe */
    [data-testid="stDataFrame"] {
        border: 1px solid #1e2d3d !important;
        border-radius: 12px !important;
        overflow: hidden !important;
        background: #0d1117 !important;
    }
    [data-testid="stDataFrame"] iframe { background: #0d1117 !important; }
    [data-testid="stDataFrame"] > div  { background: #0d1117 !important; }
    /* Expander */
    [data-testid="stExpander"] {
        background: #0d1117 !important;
        border: 1px solid #1e2d3d !important;
        border-radius: 10px !important;
    }
    /* Metric */
    [data-testid="stMetric"] { background: #0d1117 !important; }
    /* Plotly charts transparent bg */
    .js-plotly-plot .plotly { background: transparent !important; }
    /* Hide radio wrapper label ("nav" text) */
    div[data-testid="stRadio"] > label { display:none !important; }
    div[data-testid="stRadio"] > div[role="radiogroup"] { gap:2px !important; }
    div[data-testid="stRadio"] label {
        padding: 9px 12px !important; border-radius:8px !important;
        font-size:13px !important; font-weight:500 !important;
        color:#64748b !important; border:1px solid transparent !important;
        display:flex !important; align-items:center !important;
        transition:all .15s !important; margin:1px 0 !important;
    }
    div[data-testid="stRadio"] label:hover {
        background:#111827 !important; color:#94a3b8 !important;
    }
    div[data-testid="stRadio"] label:has(input:checked) {
        background:#0f2744 !important; color:#38bdf8 !important;
        border-color:#1e3a5f !important;
    }
    /* Hide radio dot/circle */
    div[data-testid="stRadio"] label > div:first-child { display:none !important; }
    /* Hide "nav" label text specifically */
    div[data-testid="stRadio"] > label[data-testid="stWidgetLabel"] { display:none !important; }
    </style>
    """, unsafe_allow_html=True)

    # Sidebar header
    st.markdown("""
    <div style="padding:8px 4px 16px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <div style="width:32px;height:32px;background:linear-gradient(135deg,#0ea5e9,#6366f1);
             border-radius:8px;display:flex;align-items:center;justify-content:center;
             font-size:14px">📈</div>
        <div>
          <div style="font-size:15px;font-weight:700;color:#f1f5f9;letter-spacing:.3px">GSE Analytics</div>
          <div style="font-size:10px;color:#475569;letter-spacing:.5px;text-transform:uppercase">Terminal v2.0</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if market_is_open():
        st.markdown('<div style="background:#052e16;border:1px solid #166534;border-radius:8px;padding:8px 12px;font-size:12px;color:#4ade80;margin-bottom:8px">● MARKET OPEN · 10:00–15:00 GMT</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="background:#1c1917;border:1px solid #292524;border-radius:8px;padding:8px 12px;font-size:12px;color:#78716c;margin-bottom:8px">○ MARKET CLOSED</div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:10px;color:#475569;margin-bottom:12px;padding-left:2px">Last refreshed: {datetime.now(timezone.utc).strftime("%H:%M:%S GMT")}</div>', unsafe_allow_html=True)

    if st.button("↺  Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    st.markdown('<div style="font-size:10px;font-weight:600;color:#475569;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px">Navigation</div>', unsafe_allow_html=True)
    page = st.radio(
        "Navigation",
        ["Overview", "Stock Detail", "Sector Analysis", "Compare Stocks", "Portfolio", "Advanced Charts", "Market Review"],
        index=["Overview", "Stock Detail", "Sector Analysis", "Compare Stocks", "Portfolio", "Advanced Charts", "Market Review"]
              .index(st.session_state.page),
        label_visibility="hidden",
        format_func=lambda x: {
            "Overview":        "🏠  Market overview",
            "Stock Detail":    "📈  Stock detail",
            "Sector Analysis": "🏭  Sector analysis",
            "Compare Stocks":  "⚖️  Compare stocks",
            "Portfolio":       "💼  Portfolio tracker",
            "Advanced Charts": "📊  Advanced charts",
            "Market Review":   "📰  Daily market review",
        }.get(x, x),
    )
    st.session_state.page = page

    st.divider()

    st.markdown('<div style="font-size:10px;font-weight:600;color:#475569;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px">Alert thresholds</div>', unsafe_allow_html=True)
    st.session_state.alert_thresholds["drop"] = st.slider(
        "Drop alert (%)", -20.0, -1.0,
        value=st.session_state.alert_thresholds["drop"], step=0.5,
    )
    st.session_state.alert_thresholds["rise"] = st.slider(
        "Rise alert (%)", 1.0, 20.0,
        value=st.session_state.alert_thresholds["rise"], step=0.5,
    )

    st.divider()

    st.markdown('<div style="font-size:10px;font-weight:600;color:#475569;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px">Watchlist</div>', unsafe_allow_html=True)
    wl_input = st.text_input("Add symbol", placeholder="e.g. GCB").upper().strip()
    if st.button("+ Add to watchlist", use_container_width=True) and wl_input:
        if wl_input not in st.session_state.watchlist:
            st.session_state.watchlist.append(wl_input)
            st.rerun()
    for sym in list(st.session_state.watchlist):
        c1, c2 = st.columns([4, 1])
        row_live = df_live[df_live["symbol"] == sym] if not df_live.empty else pd.DataFrame()
        chg = f"{row_live['change'].values[0]:+.2f}%" if not row_live.empty else ""
        color = "#4ade80" if (not row_live.empty and row_live['change'].values[0] >= 0) else "#f87171"
        c1.markdown(f'<div style="font-size:12px;color:#e2e8f0">{sym} <span style="color:{color};font-size:11px">{chg}</span></div>', unsafe_allow_html=True)
        if c2.button("✕", key=f"rm_{sym}"):
            st.session_state.watchlist.remove(sym)
            st.rerun()
# ═══════════════════════════════════════════════════════════════════════════════
# SHARED DATA LOAD
# ═══════════════════════════════════════════════════════════════════════════════

df_live = get_live_prices()
# Normalise change column (handles decimal fraction vs % format)
if not df_live.empty:
    df_live = _normalise_change(df_live)
symbols = sorted(df_live["symbol"].dropna().tolist()) if not df_live.empty else []


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

if page == "Overview":

    st.markdown("""
    <style>
    /* ── Pro dark card system ── */
    .pro-header {
        display:flex; align-items:center; justify-content:space-between;
        margin-bottom:1.5rem; padding-bottom:1rem;
        border-bottom:1px solid #1e2d3d;
    }
    .pro-header-title { font-size:26px; font-weight:800; color:#f1f5f9; letter-spacing:-.3px; }
    .pro-header-sub   { font-size:13px; color:#475569; margin-top:2px; }
    .pro-header-time  { font-size:12px; color:#334155; font-family:monospace; }

    .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:1.5rem; }
    .kpi-card {
        background:#0d1117; border:1px solid #1e2d3d; border-radius:14px;
        padding:18px 22px; position:relative; overflow:hidden;
        transition:border-color .2s, transform .2s;
    }
    .kpi-card:hover { border-color:#334155; transform:translateY(-2px); }
    .kpi-card::before {
        content:""; position:absolute; top:0; left:0; right:0; height:2px;
    }
    .kpi-green::before  { background:linear-gradient(90deg,#22c55e,#16a34a); }
    .kpi-red::before    { background:linear-gradient(90deg,#ef4444,#dc2626); }
    .kpi-blue::before   { background:linear-gradient(90deg,#38bdf8,#0ea5e9); }
    .kpi-purple::before { background:linear-gradient(90deg,#a78bfa,#7c3aed); }
    .kpi-lbl { font-size:10px; font-weight:600; color:#475569; text-transform:uppercase;
               letter-spacing:.08em; margin-bottom:8px; }
    .kpi-val { font-size:30px; font-weight:800; color:#f1f5f9; line-height:1; }
    .kpi-sub { font-size:11px; color:#334155; margin-top:6px; }

    /* ── Invisible overlay button covers entire stock card ── */
    .stock-card + div [data-testid="stButton"] button {
        position:absolute !important;
        top:-88px !important; left:0 !important;
        width:100% !important; height:88px !important;
        background:transparent !important;
        border:none !important; opacity:0 !important;
        cursor:pointer !important; z-index:10 !important;
    }
    .stock-card + div { position:relative !important; margin-top:-4px !important; }

    /* ── Grid card buttons — styled as clean "View" link ── */
    [data-testid="stButton"] button[kind="secondary"] {
        background:#111827 !important; border:1px solid #1e2d3d !important;
        color:#334155 !important; font-size:10px !important;
        padding:3px 0 !important; border-radius:0 0 14px 14px !important;
        margin-top:-14px !important; width:100% !important;
        letter-spacing:.06em !important; text-transform:uppercase !important;
        transition:all .15s !important;
    }
    [data-testid="stButton"] button[kind="secondary"]:hover {
        background:#1a2d4a !important; color:#38bdf8 !important;
        border-color:#38bdf8 !important;
    }

    /* ── Card hover glow effect ── */
    .stock-card:hover {
        border-color:#38bdf8 !important;
        box-shadow:0 0 0 1px #38bdf822 !important;
        transform:translateY(-1px) !important;
        transition:all .18s ease !important;
    }
    .stock-card { transition:all .18s ease !important; }
    .section-label {
        font-size:10px; font-weight:800; color:#38bdf8; text-transform:uppercase;
        letter-spacing:.14em; margin:1.75rem 0 .85rem;
        display:flex; align-items:center; gap:10px;
    }
    .section-label::before {
        content:""; width:3px; height:14px; background:#38bdf8;
        border-radius:2px; display:inline-block;
    }
    .section-label::after {
        content:""; flex:1; height:1px;
        background:linear-gradient(90deg,#1e2d3d,transparent);
    }

    .stock-card {
        background:#0d1117; border:1px solid #1e2d3d; border-radius:14px;
        padding:16px 18px; margin-bottom:6px;
        display:flex; align-items:center; justify-content:space-between;
        transition:all .18s ease; cursor:pointer;
    }
    .stock-card:hover {
        border-color:#38bdf8; background:#060d18;
        box-shadow:0 4px 20px rgba(56,189,248,0.06);
        transform:translateY(-1px);
    }
    .sc-left  { display:flex; align-items:center; gap:14px; }
    .sc-avatar {
        width:42px; height:42px; border-radius:10px;
        display:flex; align-items:center; justify-content:center;
        font-size:13px; font-weight:800; flex-shrink:0; letter-spacing:.5px;
        flex-direction:column; line-height:1;
    }
    .sc-sym  { font-size:15px; font-weight:700; color:#f1f5f9; }
    .sc-name { font-size:11px; color:#475569; margin-top:2px; }
    .sc-right { text-align:right; }
    .sc-price { font-size:15px; font-weight:600; color:#cbd5e1; font-family:monospace; }
    .sc-badge {
        display:inline-block; font-size:11px; font-weight:700;
        padding:3px 10px; border-radius:20px; margin-top:4px;
        font-family: monospace; letter-spacing:.3px;
    }
    .badge-up { background:#052e16; color:#4ade80; border:1px solid #166534; }
    .badge-dn { background:#1c0a0a; color:#f87171; border:1px solid #7f1d1d; }
    .badge-nt { background:#0f172a; color:#64748b; border:1px solid #1e2d3d; }

    .alert-card {
        border-radius:14px; padding:14px 18px; margin-bottom:8px;
        display:flex; align-items:flex-start; gap:14px;
        transition:transform .15s ease;
    }
    .alert-card:hover { transform:translateX(3px); }
    .alert-danger  { background:rgba(28,10,10,0.9); border:1px solid #7f1d1d;
        box-shadow:0 0 20px rgba(239,68,68,0.04); }
    .alert-success { background:rgba(2,28,14,0.9); border:1px solid #14532d;
        box-shadow:0 0 20px rgba(34,197,94,0.04); }
    .alert-dot { width:8px; height:8px; border-radius:50%; margin-top:5px; flex-shrink:0; }
    .dot-danger  { background:#ef4444; box-shadow:0 0 8px #ef4444; animation:pulse 2s infinite; }
    .dot-success { background:#22c55e; box-shadow:0 0 8px #22c55e; animation:pulse 2s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
    .alert-sym  { font-size:13px; font-weight:700; color:#f1f5f9; }
    .alert-msg  { font-size:12px; color:#94a3b8; margin-top:2px; }
    .alert-time { font-size:10px; color:#334155; margin-top:4px; font-family:monospace; }

    .wl-card {
        background:#0d1117; border:1px solid #1e2d3d; border-radius:12px;
        padding:14px 18px; margin-bottom:8px;
        display:flex; align-items:center; justify-content:space-between;
    }
    .wl-bar-bg   { height:3px; background:#1e2d3d; border-radius:2px; width:80px; margin-top:6px; }
    .wl-bar-fill { height:3px; border-radius:2px; }

    .eq-table-wrap { background:#0d1117; border:1px solid #1e2d3d;
        border-radius:12px; overflow:hidden; margin-top:.5rem; }
    [data-testid="stDataFrame"] table { background:#0d1117 !important; }
    [data-testid="stDataFrame"] th {
        background:#111827 !important; color:#475569 !important;
        font-size:11px !important; text-transform:uppercase !important;
        letter-spacing:.06em !important; border-bottom:1px solid #1e2d3d !important;
    }
    [data-testid="stDataFrame"] td { color:#cbd5e1 !important; font-size:13px !important; }
    [data-testid="stTextInput"] input {
        background:#0d1117 !important; border:1px solid #1e2d3d !important;
        color:#e2e8f0 !important; border-radius:8px !important;
    }

    /* ── Force dataframe dark ── */
    [data-testid="stDataFrame"] iframe,
    [data-testid="stDataFrame"] > div,
    [data-testid="stDataFrame"] table,
    .stDataFrame { background:#0d1117 !important; }

    /* glowing row hover */
    [data-testid="stDataFrame"] tr:hover td {
        background:#111827 !important;
    }

    /* ── Hide label above hidden radio ── */
    [data-testid="stRadio"] > label { display:none !important; }

    /* ── Plotly chart bg ── */
    .js-plotly-plot, .plot-container, .svg-container {
        background:transparent !important;
    }

    /* ── Info / warning banners ── */
    [data-testid="stAlert"] {
        background:#0d1117 !important;
        border:1px solid #1e2d3d !important;
        border-radius:10px !important;
        color:#64748b !important;
    }
    </style>
    """, unsafe_allow_html=True)

    if df_live.empty:
        st.error("Could not load market data.")
        st.stop()

    # ── Live ticker tape ───────────────────────────────────────────────────────
    ticker_items = []
    for _, r in df_live.iterrows():
        sym = str(r["symbol"])
        chg = float(r["change"])
        prc = float(r["price"])
        clr = "#4ade80" if chg > 0 else "#f87171" if chg < 0 else "#64748b"
        arrow = "▲" if chg > 0 else "▼" if chg < 0 else "●"
        ticker_items.append(
            f'<span style="margin:0 24px;white-space:nowrap">'
            f'<span style="color:#94a3b8;font-weight:700">{sym}</span> '
            f'<span style="color:#e2e8f0;font-family:monospace">GH₵ {prc:.2f}</span> '
            f'<span style="color:{clr};font-size:11px">{arrow} {chg:+.2f}%</span></span>'
        )
    ticker_html = "".join(ticker_items * 3)  # repeat for seamless loop
    st.markdown(f"""
    <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:10px;
         padding:10px 0;margin-bottom:1.25rem;overflow:hidden;position:relative">
      <div style="display:inline-flex;animation:ticker 60s linear infinite;font-size:12px">
        {ticker_html}
      </div>
    </div>
    <style>
    @keyframes ticker {{
      0%   {{ transform: translateX(0); }}
      100% {{ transform: translateX(-33.33%); }}
    }}
    </style>
    """, unsafe_allow_html=True)

    summary         = market_summary(df_live)
    gainers_count   = summary.get("gainers",   0)
    losers_count    = summary.get("losers",    0)
    unchanged_count = summary.get("unchanged", 0)
    vol_label       = summary.get("vol_label", "—")
    now_str         = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M GMT")

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pro-header">
      <div>
        <div class="pro-header-title">GSE Daily Analytics</div>
        <div class="pro-header-sub">Ghana Stock Exchange · Real-time market data</div>
      </div>
      <div class="pro-header-time">{now_str}</div>
    </div>""", unsafe_allow_html=True)

    # ── Global search bar (ISEDAN-style) ──────────────────────────────────────
    search_query = st.text_input("",
        placeholder="🔍  Search symbol or company name…",
        label_visibility="collapsed", key="global_search")
    if search_query and len(search_query) >= 2:
        q = search_query.upper()
        results = df_live[
            df_live["symbol"].str.upper().str.contains(q, na=False) |
            df_live["name"].str.upper().str.contains(q, na=False)
        ].head(8)
        if not results.empty:
            st.markdown('<div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:12px;overflow:hidden;margin-bottom:12px">', unsafe_allow_html=True)
            for _, r in results.iterrows():
                sym   = str(r["symbol"])
                cname = _GSE_NAMES.get(sym, str(r["name"]))
                chg   = float(r["change"])
                chg_c = "#4ade80" if chg > 0 else "#f87171" if chg < 0 else "#475569"
                logo  = _load_logo_b64(sym)
                av    = f'<img src="{logo}" style="width:32px;height:32px;object-fit:contain;border-radius:8px;background:#111827;padding:2px">' if logo else f'<div style="width:32px;height:32px;border-radius:8px;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;color:#38bdf8">{sym[:2]}</div>'
                st.markdown(f'''<div style="display:flex;align-items:center;gap:12px;padding:10px 16px;
                    border-bottom:1px solid #111827;cursor:pointer">
                    {av}
                    <div style="flex:1"><div style="font-size:13px;font-weight:700;color:#f1f5f9">{sym}</div>
                    <div style="font-size:11px;color:#475569">{cname}</div></div>
                    <div style="text-align:right"><div style="font-size:13px;font-weight:600;color:#e2e8f0;font-family:monospace">GH₵ {r["price"]:.2f}</div>
                    <div style="font-size:11px;color:{chg_c}">{"+" if chg>=0 else ""}{chg:.2f}%</div></div>
                </div>''', unsafe_allow_html=True)
                if st.button(f"Open {sym}", key=f"srch_{sym}", use_container_width=True):
                    st.session_state["selected_symbol"] = sym
                    st.session_state.page = "Stock Detail"
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # ── KPI cards ──────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="kpi-grid">
      <div class="kpi-card kpi-green">
        <div class="kpi-lbl">Gainers</div>
        <div class="kpi-val" style="color:#4ade80">{gainers_count}</div>
        <div class="kpi-sub">stocks advancing</div>
      </div>
      <div class="kpi-card kpi-red">
        <div class="kpi-lbl">Losers</div>
        <div class="kpi-val" style="color:#f87171">{losers_count}</div>
        <div class="kpi-sub">stocks declining</div>
      </div>
      <div class="kpi-card kpi-blue">
        <div class="kpi-lbl">Unchanged</div>
        <div class="kpi-val" style="color:#38bdf8">{unchanged_count}</div>
        <div class="kpi-sub">no movement</div>
      </div>
      <div class="kpi-card kpi-purple">
        <div class="kpi-lbl">Total volume</div>
        <div class="kpi-val" style="color:#a78bfa">{vol_label}</div>
        <div class="kpi-sub">shares traded today</div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Avatar colour helper ───────────────────────────────────────────────────
    # (avatar/logo helpers moved to module level above)


    def _sparkline(sym: str, width=80, height=28) -> str:
        """Generate a tiny inline SVG sparkline from CSV history."""
        try:
            hist = load_historical_comparison(sym)
            if len(hist) < 2:
                return ""
            prices = hist["price"].tail(14).tolist()
            mn, mx = min(prices), max(prices)
            if mx == mn:
                return ""
            xs = [i * (width / (len(prices)-1)) for i in range(len(prices))]
            ys = [height - ((p - mn) / (mx - mn)) * height for p in prices]
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
            color = "#4ade80" if prices[-1] >= prices[0] else "#f87171"
            # Fill area under line
            fill_pts = f"0,{height} " + pts + f" {width},{height}"
            return f'''<svg width="{width}" height="{height}" style="display:block">
              <defs>
                <linearGradient id="sg_{sym}" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="{color}" stop-opacity="0.3"/>
                  <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
                </linearGradient>
              </defs>
              <polygon points="{fill_pts}" fill="url(#sg_{sym})"/>
              <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"
                stroke-linecap="round" stroke-linejoin="round"/>
            </svg>'''
        except Exception:
            return ""

    # ── Gainers & Losers ───────────────────────────────────────────────────────
    gainers_df = df_live[df_live["change"] > 0].nlargest(5, "change")
    losers_df  = df_live[df_live["change"] < 0].nsmallest(5, "change")

    # ── Watchlist horizontal scroll strip (like ISEDAN) ─────────────────────
    if st.session_state.watchlist:
        wl_chips = ""
        for wsym in st.session_state.watchlist:
            wr = df_live[df_live["symbol"]==wsym]
            wchg = float(wr["change"].values[0]) if not wr.empty else 0
            wpr  = float(wr["price"].values[0])  if not wr.empty else 0
            wlog = _load_logo_b64(wsym)
            wbg  = "rgba(34,197,94,0.1)"  if wchg>0 else "rgba(239,68,68,0.1)"  if wchg<0 else "rgba(30,45,61,0.5)"
            wbdr = "#4ade8033" if wchg>0 else "#f8717133" if wchg<0 else "#1e2d3d"
            wimghtml = f'<img src="{wlog}" style="width:32px;height:32px;object-fit:contain;border-radius:8px;background:#0d1117;padding:2px">' if wlog else f'<div style="width:32px;height:32px;border-radius:8px;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:900;color:#38bdf8">{wsym[:2]}</div>'
            wc = "#4ade80" if wchg>0 else "#f87171" if wchg<0 else "#475569"
            wl_chips += f'''<div style="flex-shrink:0;background:{wbg};border:1px solid {wbdr};
                border-radius:14px;padding:10px 16px;min-width:110px;cursor:pointer"
                onclick="">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">{wimghtml}
                  <span style="font-size:13px;font-weight:700;color:#f1f5f9">{wsym}</span></div>
                <div style="font-size:12px;font-weight:600;color:{wc}">{"+" if wchg>=0 else ""}{wchg:.2f}%</div>
            </div>'''
        st.markdown(f'''<div style="display:flex;gap:10px;overflow-x:auto;padding:4px 0 12px;
            scrollbar-width:none;-ms-overflow-style:none">{wl_chips}</div>''', unsafe_allow_html=True)

    # ── TOP GAINERS grid (3-col like ISEDAN image 5) ───────────────────────────
    st.markdown('<div class="section-label">Top gainers (1D)</div>', unsafe_allow_html=True)

    if gainers_df.empty:
        st.markdown('<div style="color:#334155;font-size:13px;padding:12px">No gainers today</div>', unsafe_allow_html=True)
    else:
        gcols = st.columns(3)
        for gi, (_, row) in enumerate(gainers_df.head(9).iterrows()):
            sym   = str(row["symbol"])
            name  = _company(sym, str(row["name"]))
            price = float(row["price"])
            chg   = float(row["change"])
            prev  = price / (1 + chg/100) if chg != -100 else price
            abs_chg = price - prev
            logo  = _load_logo_b64(sym)
            av_html = f'<img src="{logo}" style="width:44px;height:44px;object-fit:contain;border-radius:50%;background:#111827;padding:3px;border:2px solid #1e2d3d">' if logo else f'<div style="width:44px;height:44px;border-radius:50%;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:900;color:#38bdf8;border:2px solid #1e3a5f">{sym[:2]}</div>'
            with gcols[gi % 3]:
                st.markdown(f"""
                <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:16px;
                     padding:16px;margin-bottom:10px;position:relative;overflow:hidden;
                     transition:all .2s;cursor:pointer">
                  <div style="position:absolute;top:10px;right:10px">
                    <span style="background:rgba(34,197,94,0.15);color:#4ade80;font-size:11px;
                      font-weight:800;padding:4px 9px;border-radius:99px">▲ +{chg:.2f}%</span>
                  </div>
                  <div style="margin-bottom:10px">{av_html}</div>
                  <div style="font-size:15px;font-weight:800;color:#f1f5f9">{sym}</div>
                  <div style="font-size:11px;color:#475569;margin-bottom:8px;
                       white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name[:22]}</div>
                  <div style="font-size:18px;font-weight:800;color:#e2e8f0;font-family:monospace">
                    GH₵ {price:.2f}</div>
                  <div style="font-size:12px;color:#4ade80;margin-top:2px;font-family:monospace">
                    +{abs_chg:.2f}</div>
                </div>""", unsafe_allow_html=True)
                if st.button(f"View {sym} →", key=f"btn_g_{sym}",
                             use_container_width=True, help=f"Open {name}"):
                    st.session_state["selected_symbol"] = sym
                    st.session_state.page = "Stock Detail"
                    st.rerun()

    # ── TOP LOSERS grid ────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Top losers (1D)</div>', unsafe_allow_html=True)

    if losers_df.empty:
        st.markdown('<div style="color:#334155;font-size:13px;padding:12px">No losers today</div>', unsafe_allow_html=True)
    else:
        lcols = st.columns(3)
        for li, (_, row) in enumerate(losers_df.head(9).iterrows()):
            sym   = str(row["symbol"])
            name  = _company(sym, str(row["name"]))
            price = float(row["price"])
            chg   = float(row["change"])
            prev  = price / (1 + chg/100) if chg != -100 else price
            abs_chg = price - prev
            logo  = _load_logo_b64(sym)
            av_html = f'<img src="{logo}" style="width:44px;height:44px;object-fit:contain;border-radius:50%;background:#111827;padding:3px;border:2px solid #1e2d3d">' if logo else f'<div style="width:44px;height:44px;border-radius:50%;background:#1c0a0a;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:900;color:#f87171;border:2px solid #7f1d1d">{sym[:2]}</div>'
            with lcols[li % 3]:
                st.markdown(f"""
                <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:16px;
                     padding:16px;margin-bottom:10px;position:relative;overflow:hidden;cursor:pointer">
                  <div style="position:absolute;top:10px;right:10px">
                    <span style="background:rgba(239,68,68,0.15);color:#f87171;font-size:11px;
                      font-weight:800;padding:4px 9px;border-radius:99px">▼ {chg:.2f}%</span>
                  </div>
                  <div style="margin-bottom:10px">{av_html}</div>
                  <div style="font-size:15px;font-weight:800;color:#f1f5f9">{sym}</div>
                  <div style="font-size:11px;color:#475569;margin-bottom:8px;
                       white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name[:22]}</div>
                  <div style="font-size:18px;font-weight:800;color:#e2e8f0;font-family:monospace">
                    GH₵ {price:.2f}</div>
                  <div style="font-size:12px;color:#f87171;margin-top:2px;font-family:monospace">
                    {abs_chg:.2f}</div>
                </div>""", unsafe_allow_html=True)
                if st.button(f"View {sym} →", key=f"btn_l_{sym}",
                             use_container_width=True, help=f"Open {name}"):
                    st.session_state["selected_symbol"] = sym
                    st.session_state.page = "Stock Detail"
                    st.rerun()

    # ── Alerts ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Critical alerts</div>', unsafe_allow_html=True)
    alerts = generate_alerts(df_live, st.session_state.alert_thresholds)
    if alerts:
        for a in alerts:
            cls  = "alert-danger"  if a["type"] == "danger"  else "alert-success"
            dcls = "dot-danger"    if a["type"] == "danger"  else "dot-success"
            sym  = str(a["symbol"])
            name = _GSE_NAMES.get(sym, sym)
            detail = a["msg"].split("—",1)[-1].strip()
            thresh = st.session_state.alert_thresholds
            st.markdown(f"""
            <div class="alert-card {cls}">
              <div class="alert-dot {dcls}"></div>
              <div>
                <div class="alert-sym">{sym} <span style="font-weight:400;color:#64748b">· {name}</span></div>
                <div class="alert-msg">{detail}</div>
                <div class="alert-time">THRESHOLD · DROP {thresh["drop"]}% / RISE +{thresh["rise"]}%</div>
              </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#334155;font-size:13px;padding:12px 0">No alerts triggered based on current thresholds.</div>', unsafe_allow_html=True)

    # ── Watchlist ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Watchlist audit</div>', unsafe_allow_html=True)
    wl_set = set(s.upper().strip() for s in st.session_state.watchlist)
    wl_df  = df_live[
        df_live["symbol"].str.upper().str.strip().isin(wl_set) |
        df_live["name"].str.upper().str.strip().isin(wl_set)
    ]
    if not wl_df.empty:
        for _, row in wl_df.iterrows():
            sym   = str(row["symbol"])
            name  = _company(sym, str(row["name"]))
            chg   = float(row["change"])
            pct   = min(max((chg + 10) / 20, 0), 1)
            bar_c = "#22c55e" if chg >= 0 else "#ef4444"
            bcls  = "badge-up" if chg >= 0 else "badge-dn"
            sign  = "▲ +" if chg >= 0 else "▼ "
            st.markdown(f"""
            <div class="wl-card">
              <div class="sc-left">{_av(sym)}
                <div>
                  <div class="sc-sym">{sym}</div>
                  <div class="sc-name">{name}</div>
                  <div class="wl-bar-bg">
                    <div class="wl-bar-fill" style="width:{int(pct*100)}%;background:{bar_c}"></div>
                  </div>
                </div>
              </div>
              <div class="sc-right">
                <div class="sc-price">GH₵ {row['price']:.2f}</div>
                <span class="sc-badge {bcls}">{sign}{abs(chg):.2f}%</span>
              </div>
            </div>""", unsafe_allow_html=True)
            if st.button("", key=f"btn_wl_{sym}", help=f"View {name} detail"):
                st.session_state["selected_symbol"] = sym
                st.session_state.page = "Stock Detail"
                st.rerun()
    else:
        st.markdown('<div style="color:#334155;font-size:13px;padding:12px 0">No watchlist symbols in today&#39;s data. Add via the sidebar.</div>', unsafe_allow_html=True)

    # ── All equities ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">All equities</div>', unsafe_allow_html=True)
    search = st.text_input("", placeholder="🔍  Search symbol or company name…", label_visibility="collapsed")
    disp = df_live.copy()
    disp["name"] = disp.apply(
        lambda r: _GSE_NAMES.get(str(r["symbol"]), str(r["name"])) if str(r["name"]) == str(r["symbol"]) else str(r["name"]), axis=1
    )
    if search:
        q = search.upper()
        disp = disp[disp["symbol"].str.upper().str.contains(q, na=False) | disp["name"].str.upper().str.contains(q, na=False)]
    disp["Price (GH₵)"] = disp["price"].map("{:.2f}".format)
    disp["Change (%)"]  = disp["change"].map("{:+.2f}%".format)
    disp["Volume"]      = disp["volume"].map("{:,}".format)
    # Build fully custom dark HTML table with click buttons
    rows_html = ""
    eq_syms_order = []  # track order for buttons
    for _, r in disp.iterrows():
        eq_syms_order.append(str(r["symbol"]))
        chg_val = float(r["change"])
        if chg_val > 0:
            chg_color = "#4ade80"
            chg_bg    = "rgba(34,197,94,0.08)"
            chg_str   = f"+{chg_val:.2f}%"
        elif chg_val < 0:
            chg_color = "#f87171"
            chg_bg    = "rgba(239,68,68,0.08)"
            chg_str   = f"{chg_val:.2f}%"
        else:
            chg_color = "#475569"
            chg_bg    = "transparent"
            chg_str   = "+0.00%"

        sym      = str(r["symbol"])
        cname    = _GSE_NAMES.get(sym, str(r["name"])) if str(r["name"]) == sym else str(r["name"])
        price    = f"GH₵ {float(r['price']):.2f}"
        vol      = f"{int(r['volume']):,}"

        # Avatar colours
        _AV2 = [
            ("#0c2a4a","#38bdf8"), ("#0d2b1a","#4ade80"), ("#2a1a0c","#fb923c"),
            ("#1a0c2a","#a78bfa"), ("#2a0c1a","#f472b6"), ("#0c2a22","#34d399"),
        ]
        ai = sum(ord(c) for c in sym) % len(_AV2)
        av_bg, av_fg = _AV2[ai]

        # Sector-based logo colours for a richer badge feel
        _SECTOR_COLORS = {
            "GCB":"#1a3a6b,#60a5fa","EGH":"#1a3a6b,#60a5fa","SCB":"#1a3a6b,#60a5fa",
            "CAL":"#1a3a6b,#60a5fa","ETI":"#1a3a6b,#60a5fa","ACCESS":"#1a3a6b,#60a5fa",
            "SOGEGH":"#1a3a6b,#60a5fa","RBGH":"#1a3a6b,#60a5fa","ADB":"#1a3a6b,#60a5fa",
            "MTNGH":"#3d2800,#fbbf24","GOIL":"#002a14,#34d399","TOR":"#002a14,#34d399",
            "TOTAL":"#002a14,#34d399","GCB":"#1a3a6b,#60a5fa",
            "GGBL":"#3d0a0a,#f87171","FML":"#3d0a0a,#f87171","UNIL":"#3d0a0a,#f87171",
            "BOPP":"#1a2800,#86efac","PBC":"#1a2800,#86efac",
            "MOGL":"#2a1a00,#fb923c","GSR":"#2a1a00,#fb923c","AGA":"#2a1a00,#fb923c",
            "ALLGH":"#1a0d2e,#c084fc","AYRTN":"#1a0d2e,#c084fc","CPC":"#1a0d2e,#c084fc",
            "SIC":"#001a2e,#38bdf8","ENTERPRISE":"#001a2e,#38bdf8",
            "CLYD":"#2e001a,#f472b6","HFC":"#2e001a,#f472b6",
        }
        sc = _SECTOR_COLORS.get(sym, f"{av_bg},{av_fg}")
        sc_bg, sc_fg = sc.split(",")

        # Word mark: first letter big, rest small
        wm_big  = sym[0]
        wm_rest = sym[1:3] if len(sym) > 1 else ""

        logo_uri_tbl = _load_logo_b64(sym)
        if logo_uri_tbl:
            badge_html = f'''<div style="width:38px;height:38px;border-radius:9px;
                background:#0d1117;border:1px solid #1e2d3d;flex-shrink:0;
                display:flex;align-items:center;justify-content:center;padding:3px;overflow:hidden">
                <img src="{logo_uri_tbl}" style="width:100%;height:100%;object-fit:contain;border-radius:6px" alt="{sym}"/>
              </div>'''
        else:
            badge_html = f'''<div style="width:38px;height:38px;border-radius:9px;background:{sc_bg};
                border:1px solid {sc_fg}22;flex-shrink:0;display:flex;align-items:center;
                justify-content:center;flex-direction:column;line-height:1">
                <div style="font-size:15px;font-weight:900;color:{sc_fg};letter-spacing:-1px;
                     font-family:Arial Black,sans-serif">{wm_big}</div>
                <div style="font-size:8px;font-weight:700;color:{sc_fg}99;letter-spacing:1px;
                     margin-top:-1px">{wm_rest}</div>
              </div>'''

        rows_html += f"""
        <tr class="eq-row">
          <td style="width:160px">
            <div style="display:flex;align-items:center;gap:12px">
              {badge_html}
              <span style="font-weight:700;color:#f1f5f9;font-size:13px">{sym}</span>
            </div>
          </td>
          <td style="color:#94a3b8;font-size:13px">{cname}</td>
          <td style="color:#e2e8f0;font-family:'Courier New',monospace;font-size:13px;font-weight:600">GH₵ {float(r["price"]):.2f}</td>
          <td>
            <span style="background:{chg_bg};color:{chg_color};font-size:12px;font-weight:700;
                 font-family:monospace;padding:3px 12px;border-radius:20px;
                 border:1px solid {chg_color}33">{chg_str}</span>
          </td>
          <td style="color:#475569;font-size:12px;font-family:monospace">{vol}</td>
        </tr>"""

    st.markdown('<div style="font-size:11px;color:#334155;margin-bottom:6px">Click a symbol button below to open full detail</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div style="border:1px solid #1e2d3d;border-radius:14px;overflow:hidden;margin-top:8px;
                max-height:520px;overflow-y:auto">
      <table style="width:100%;border-collapse:collapse;background:#0d1117">
        <thead>
          <tr style="background:#111827;border-bottom:1px solid #1e2d3d;position:sticky;top:0">
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;
                color:#475569;text-transform:uppercase;letter-spacing:.08em;width:140px">Symbol</th>
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;
                color:#475569;text-transform:uppercase;letter-spacing:.08em">Company</th>
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;
                color:#475569;text-transform:uppercase;letter-spacing:.08em">Price</th>
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;
                color:#475569;text-transform:uppercase;letter-spacing:.08em">Change</th>
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;
                color:#475569;text-transform:uppercase;letter-spacing:.08em">Volume</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    <style>
    .eq-row {{ border-bottom:1px solid #111827; transition:background .15s; }}
    .eq-row:hover {{ background:#111827 !important; }}
    .eq-row:last-child {{ border-bottom:none; }}
    .eq-row td {{ padding:11px 16px; vertical-align:middle; }}
    </style>
    """, unsafe_allow_html=True)

    # Compact symbol chip grid — cleaner than full buttons
    st.markdown('<div class="section-label" style="margin-top:1rem">Quick navigate</div>', unsafe_allow_html=True)
    chips_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:1rem">'
    for sym in eq_syms_order[:min(len(eq_syms_order), 40)]:
        chg_row = df_live[df_live["symbol"] == sym]
        chg_val = float(chg_row["change"].values[0]) if not chg_row.empty else 0.0
        chip_c  = "#4ade80" if chg_val > 0 else "#f87171" if chg_val < 0 else "#475569"
        chip_bg = "rgba(34,197,94,0.08)" if chg_val > 0 else "rgba(239,68,68,0.08)" if chg_val < 0 else "rgba(71,85,105,0.08)"
        chips_html += f'<span style="background:{chip_bg};color:{chip_c};border:1px solid {chip_c}33;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;font-family:monospace;letter-spacing:.5px">{sym}</span>'
    chips_html += '</div>'
    st.markdown(chips_html, unsafe_allow_html=True)

    # Search and click via selectbox for navigation
    nav_sym = st.selectbox("Open stock detail for:", [""] + eq_syms_order,
        format_func=lambda s: f"{s}  —  {_GSE_NAMES.get(s, s)}" if s else "Select a symbol…",
        label_visibility="collapsed", key="eq_nav_select")
    if nav_sym:
        st.session_state["selected_symbol"] = nav_sym
        st.session_state.page = "Stock Detail"
        st.rerun()
    # ── Finance news ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Finance news</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=1800, show_spinner=False)
    def fetch_news() -> list[dict]:
        """Fetch finance news from RSS feeds — GhanaWeb, Reuters, BBC Business."""
        import xml.etree.ElementTree as ET
        feeds = [
            ("Ghana Business", "https://www.ghanaweb.com/GhanaHomePage/rss/business.xml"),
            ("Reuters Markets", "https://feeds.reuters.com/reuters/businessNews"),
            ("BBC Business",    "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ]
        articles = []
        for source, url in feeds:
            try:
                r = requests.get(url, headers=HEADERS, timeout=8)
                root = ET.fromstring(r.content)
                for item in root.iter("item"):
                    title = item.findtext("title", "").strip()
                    link  = item.findtext("link",  "").strip()
                    pub   = item.findtext("pubDate", "").strip()
                    desc  = item.findtext("description", "").strip()
                    # Strip HTML tags from description
                    import re
                    desc = re.sub(r'<[^>]+>', '', desc)[:160]
                    if title:
                        articles.append({
                            "source": source, "title": title,
                            "link": link, "date": pub[:16], "desc": desc,
                        })
                    if len([a for a in articles if a["source"] == source]) >= 4:
                        break
            except Exception:
                pass
        return articles[:12]

    news_items = fetch_news()

    if news_items:
        # Group by source
        sources = {}
        for item in news_items:
            sources.setdefault(item["source"], []).append(item)

        src_cols = st.columns(len(sources))
        src_color = {"Ghana Business": "#fbbf24", "Reuters Markets": "#f87171", "BBC Business": "#60a5fa"}

        for col, (src, items) in zip(src_cols, sources.items()):
            color = src_color.get(src, "#94a3b8")
            with col:
                st.markdown(f'''<div style="font-size:10px;font-weight:700;color:{color};
                    text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;
                    padding-bottom:6px;border-bottom:1px solid #1e2d3d">{src}</div>''',
                    unsafe_allow_html=True)
                for art in items:
                    st.markdown(f'''
                    <a href="{art["link"]}" target="_blank" style="text-decoration:none">
                      <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:10px;
                           padding:12px 14px;margin-bottom:8px;transition:border-color .2s;
                           cursor:pointer">
                        <div style="font-size:12px;font-weight:600;color:#e2e8f0;
                             line-height:1.4;margin-bottom:6px">{art["title"][:90]}{"…" if len(art["title"])>90 else ""}</div>
                        <div style="font-size:11px;color:#475569;line-height:1.3">{art["desc"][:100]}{"…" if len(art["desc"])>100 else ""}</div>
                        <div style="font-size:10px;color:#334155;margin-top:6px;font-family:monospace">{art["date"]}</div>
                      </div>
                    </a>''', unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#334155;font-size:13px;padding:8px 0">News unavailable — check your connection.</div>', unsafe_allow_html=True)

    # ── Developer footer ─────────────────────────────────────────────────────
    st.markdown("""
    <div style="margin-top:3rem;padding:20px 0;border-top:1px solid #1e2d3d;
         display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
          <div style="width:36px;height:36px;border-radius:50%;
               background:linear-gradient(135deg,#0ea5e9,#6366f1);
               display:flex;align-items:center;justify-content:center;
               font-size:13px;font-weight:900;color:#fff;flex-shrink:0">B</div>
          <div>
            <div style="font-size:14px;font-weight:700;color:#f1f5f9">
              Bismark N. G. Ababio
            </div>
            <div style="font-size:11px;color:#38bdf8;font-weight:600;letter-spacing:.3px">
              BismarkDataLab Inc
            </div>
          </div>
        </div>
        <div style="font-size:11px;color:#334155;margin-top:4px;padding-left:46px">
          GSE Analytics Terminal v2.0 &nbsp;·&nbsp; Ghana Stock Exchange
          &nbsp;·&nbsp; Data: dev.kwayisi.org
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-size:11px;color:#1e2d3d;font-family:monospace">Built with Streamlit &amp; Python</div>
        <div style="font-size:10px;color:#1a2535;margin-top:2px">© 2026 BismarkDataLab Inc. All rights reserved.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: STOCK DETAIL
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Stock Detail":
    if not symbols:
        st.error("Could not load market data.")
        st.stop()

    st.markdown("""
    <style>
    .sd-topbar{display:flex;align-items:center;gap:16px;margin-bottom:1.25rem;
        padding:16px 20px;background:#0d1117;border:1px solid #1e2d3d;border-radius:14px;
        flex-wrap:wrap}
    .sd-controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;flex:1}
    </style>""", unsafe_allow_html=True)

    # ── Top selector bar (prominent, on-page) ─────────────────────────────────
    st.markdown("### Stock detail")
    sel_c1, sel_c2, sel_c3, sel_c4 = st.columns([3, 1.5, 1, 1])

    # Pre-select from session state (set when clicking a card on Overview)
    default_sym = st.session_state.get("selected_symbol", symbols[0] if symbols else "GCB")
    default_idx = symbols.index(default_sym) if default_sym in symbols else 0

    symbol   = sel_c1.selectbox("Select equity", symbols, index=default_idx,
                  format_func=lambda s: f"{s}  —  {_GSE_NAMES.get(s, s)}")
    period   = sel_c2.selectbox("Period", ["1M","3M","6M","1Y","All"], index=2)
    show_bb  = sel_c3.checkbox("Bollinger Bands", value=True)
    show_sma = sel_c4.checkbox("SMA 50", value=False)

    st.session_state["selected_symbol"] = symbol

    # Also keep sidebar controls (secondary)
    with st.sidebar:
        st.divider()
        st.markdown('<div style="font-size:10px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Quick select</div>', unsafe_allow_html=True)
        sb_sym = st.selectbox("Symbol", symbols,
            index=symbols.index(symbol) if symbol in symbols else 0,
            key="sb_sym_detail",
            format_func=lambda s: f"{s} · {_GSE_NAMES.get(s,s)[:20]}")
        if sb_sym != symbol:
            st.session_state["selected_symbol"] = sb_sym
            st.rerun()

    hist = get_history(symbol)
    if not hist.empty:
        hist = add_indicators(hist)
        days = PERIOD_DAYS.get(period, 180)
        hist = hist.tail(days).reset_index(drop=True)

    profile = get_profile(symbol)
    row_live = df_live[df_live["symbol"] == symbol]
    name     = row_live["name"].values[0]   if not row_live.empty else symbol
    price    = row_live["price"].values[0]  if not row_live.empty else None
    change   = row_live["change"].values[0] if not row_live.empty else None

    # Resolve full company name — prefer database, then API, then symbol
    _db_name = _GSE_COMPANIES.get(symbol, {}).get("name", "")
    full_name = _db_name if _db_name and _db_name != symbol else (
        _GSE_NAMES.get(symbol) or (name if name != symbol else symbol)
    )
    # Use real logo if available, else sector badge
    _logo_uri_detail = _load_logo_b64(symbol)
    if _logo_uri_detail:
        _badge_detail = f'''<div style="width:56px;height:56px;border-radius:12px;
            background:#0d1117;border:1px solid #1e2d3d;padding:5px;flex-shrink:0;
            display:flex;align-items:center;justify-content:center">
            <img src="{_logo_uri_detail}" style="width:100%;height:100%;object-fit:contain;border-radius:8px"/>
        </div>'''
    else:
        _sc = _SC_COLORS.get(symbol, "#0c2a4a,#38bdf8")
        _bg, _fg = _sc.split(",")
        _badge_detail = f'''<div style="width:56px;height:56px;border-radius:12px;
            background:{_bg};border:1px solid {_fg}33;flex-shrink:0;
            display:flex;align-items:center;justify-content:center;
            flex-direction:column;line-height:1">
            <div style="font-size:20px;font-weight:900;color:{_fg};letter-spacing:-1px;
                 font-family:Arial Black,sans-serif">{symbol[0]}</div>
            <div style="font-size:9px;font-weight:700;color:{_fg}99;letter-spacing:1px">{symbol[1:3]}</div>
        </div>'''
    db_sector = _GSE_COMPANIES.get(symbol, {}).get("sector", "Equity")
    db_listed = _GSE_COMPANIES.get(symbol, {}).get("listed", "")
    listed_str = f"Listed {db_listed}" if db_listed and db_listed not in ["—",""] else ""

    _listed_span = f"<span style='font-size:11px;color:#334155'>· {listed_str}</span>" if listed_str else ""
    _header_html = f'''<div style="display:flex;align-items:center;gap:16px;margin-bottom:1.5rem;
         padding:20px;background:#0d1117;border:1px solid #1e2d3d;border-radius:14px">
      {_badge_detail}
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">
          <span style="background:#1e2d3d;color:#64748b;font-size:11px;font-weight:600;
              padding:3px 10px;border-radius:99px">{db_sector}</span>
          <span style="background:rgba(56,189,248,0.1);color:#38bdf8;font-size:11px;
              font-weight:600;padding:3px 10px;border-radius:99px">Equity</span>
          {_listed_span}
        </div>
        <div style="font-size:24px;font-weight:800;color:#f1f5f9;letter-spacing:-.3px">{symbol}</div>
        <div style="font-size:13px;color:#475569;margin-top:2px">{full_name}</div>
      </div>
    </div>'''
    st.markdown(_header_html, unsafe_allow_html=True)

    if price is not None:
        chg_col2 = "#4ade80" if (change or 0)>=0 else "#f87171"
        chg_bg2  = "rgba(34,197,94,0.12)" if (change or 0)>=0 else "rgba(239,68,68,0.12)"
        arrow2   = "▲" if (change or 0)>=0 else "▼"
        prev_p   = price/(1+(change or 0)/100) if (change or 0) != -100 else price
        abs_chg2 = price - prev_p
        st.markdown(f"""
        <div style="margin-bottom:1rem">
          <div style="font-size:38px;font-weight:900;color:#f1f5f9;font-family:monospace;
               letter-spacing:-1px;line-height:1">GH₵ {price:.2f}</div>
          <div style="display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap">
            <span style="background:{chg_bg2};color:{chg_col2};font-size:14px;font-weight:700;
                padding:5px 14px;border-radius:99px">{arrow2} {"+" if (change or 0)>=0 else ""}{change:.2f}% today</span>
            <span style="color:{chg_col2};font-size:14px;font-family:monospace">
              {"+" if abs_chg2>=0 else ""}GH₵ {abs_chg2:.2f}</span>
            <span style="color:#334155;font-size:12px">
              {"● MARKET OPEN" if market_is_open() else "● Closed"}</span>
          </div>
        </div>""", unsafe_allow_html=True)
        if not hist.empty:
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Period High", f"GH₵ {hist['price'].max():.2f}")
            sm2.metric("Period Low",  f"GH₵ {hist['price'].min():.2f}")
            sm3.metric("Avg Volume",  f"{int(hist['volume'].mean()):,}")
            sm4.metric("Days tracked", len(hist))

    # ── Company info card (database + API) ─────────────────────────────────
    db_info  = _GSE_COMPANIES.get(symbol, {})
    api_info = profile or {}
    co_sector  = db_info.get("sector",     api_info.get("sector",    "—"))
    co_listed  = db_info.get("listed",     "—")
    co_capital = db_info.get("capital",    "—")
    co_issued  = db_info.get("issued",     "—")
    co_auth    = db_info.get("authorised", "—")
    co_eps     = str(api_info.get("eps",   "—"))
    co_dps     = str(api_info.get("dps",   "—"))
    co_mktcap  = str(api_info.get("marketcap", "—"))

    with st.expander("Company profile", expanded=True):
        st.markdown(f"""
        <style>
        .co-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:.5rem}}
        .co-card{{background:#0d1117;border:1px solid #1e2d3d;border-radius:10px;padding:12px 16px}}
        .co-lbl {{font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;
                  letter-spacing:.08em;margin-bottom:4px}}
        .co-val {{font-size:13px;font-weight:600;color:#e2e8f0}}
        </style>
        <div class="co-grid">
          <div class="co-card"><div class="co-lbl">Sector</div>
            <div class="co-val" style="color:#38bdf8">{co_sector}</div></div>
          <div class="co-card"><div class="co-lbl">Date listed</div>
            <div class="co-val">{co_listed}</div></div>
          <div class="co-card"><div class="co-lbl">Stated capital</div>
            <div class="co-val">{co_capital}</div></div>
          <div class="co-card"><div class="co-lbl">Issued shares</div>
            <div class="co-val">{co_issued}</div></div>
          <div class="co-card"><div class="co-lbl">Authorised shares</div>
            <div class="co-val">{co_auth}</div></div>
          <div class="co-card"><div class="co-lbl">Market cap (API)</div>
            <div class="co-val">{co_mktcap}</div></div>
          <div class="co-card"><div class="co-lbl">EPS</div>
            <div class="co-val">{co_eps}</div></div>
          <div class="co-card"><div class="co-lbl">DPS</div>
            <div class="co-val">{co_dps}</div></div>
        </div>
        """, unsafe_allow_html=True)

    # ── About the company (like ISEDAN image 4) ────────────────────────────
    about_text = _GSE_ABOUT.get(symbol, "")
    _co_data    = _GSE_COMPANIES.get(symbol, {})
    with st.expander(f"About {full_name}", expanded=False):
        if about_text:
            st.markdown(f"""
            <div style="font-size:14px;color:#94a3b8;line-height:1.8;padding:4px 0;
                 text-align:justify">{about_text}</div>""", unsafe_allow_html=True)
        elif _co_data:
            st.markdown(f"""
            <div style="font-size:14px;color:#94a3b8;line-height:1.8">
              <b style="color:#e2e8f0">{full_name}</b> is listed on the Ghana Stock Exchange
              under the ticker <b style="color:#38bdf8">{symbol}</b> in the
              <b style="color:#e2e8f0">{_co_data.get("sector","—")}</b> sector.
              Date listed: {_co_data.get("listed","—")} &nbsp;·&nbsp;
              Issued shares: {_co_data.get("issued","—")} &nbsp;·&nbsp;
              Stated capital: {_co_data.get("capital","—")}
            </div>""", unsafe_allow_html=True)
        else:
            st.caption("No description available for this stock yet.")

    if hist.empty:
        st.info("No historical data available for this symbol.")
        st.stop()

    # ── Previous day comparison from CSV ────────────────────────────────────
    csv_hist = load_historical_comparison(symbol)
    if len(csv_hist) >= 2:
        prev_row   = csv_hist.iloc[-2]
        curr_price = float(row_live["price"].values[0]) if not row_live.empty else None
        prev_price = float(prev_row["price"])
        if curr_price:
            day_chg    = curr_price - prev_price
            day_chg_pct = (day_chg / prev_price * 100) if prev_price else 0
            prev_col1, prev_col2, prev_col3 = st.columns(3)
            prev_col1.metric("Yesterday's close", f"GH₵ {prev_price:.2f}")
            prev_col2.metric("Day change",
                f"GH₵ {abs(day_chg):.2f}",
                f"{day_chg_pct:+.2f}%")
            prev_col3.metric("Days tracked", len(csv_hist))

    # Main chart — price / volume / RSI / MACD
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.20, 0.25],
        vertical_spacing=0.04,
        subplot_titles=("Price & Volume", "RSI (14)", "MACD (12/26/9)"),
    )

    fig.add_trace(go.Scatter(x=hist["date"], y=hist["price"],
        name="Price", line=dict(color="#378ADD", width=2)), row=1, col=1)

    if show_bb and "BB_Upper" in hist.columns:
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["BB_Upper"],
            line=dict(color="#888780", width=1, dash="dot"), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["BB_Lower"],
            line=dict(color="#888780", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(136,135,128,0.08)", showlegend=False), row=1, col=1)

    if show_sma and "SMA50" in hist.columns:
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["SMA50"],
            name="SMA 50", line=dict(color="#EF9F27", width=1.5)), row=1, col=1)

    vol_colors = ["#1D9E75" if c >= 0 else "#E24B4A" for c in hist["change"].fillna(0)]
    fig.add_trace(go.Bar(x=hist["date"], y=hist["volume"],
        name="Volume", marker_color=vol_colors, opacity=0.5), row=1, col=1)

    fig.add_trace(go.Scatter(x=hist["date"], y=hist["RSI"],
        name="RSI", line=dict(color="#7F77DD", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="#E24B4A", opacity=0.5, row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#1D9E75", opacity=0.5, row=2, col=1)

    fig.add_trace(go.Scatter(x=hist["date"], y=hist["MACD"],
        name="MACD", line=dict(color="#378ADD", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist["date"], y=hist["Signal"],
        name="Signal", line=dict(color="#EF9F27", width=1.5)), row=3, col=1)

    hist_colors = ["#1D9E75" if v >= 0 else "#E24B4A" for v in hist["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=hist["date"], y=hist["MACD_Hist"],
        name="Histogram", marker_color=hist_colors, opacity=0.6), row=3, col=1)

    fig.update_layout(
        height=620, margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        hovermode="x unified", xaxis_rangeslider_visible=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    fig.update_xaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True)

    # RSI signal banner
    rsi_vals = hist["RSI"].dropna()
    if not rsi_vals.empty:
        rsi = rsi_vals.iloc[-1]
        if rsi > 70:
            st.warning(f"RSI {rsi:.1f} — overbought (>70). Consider taking profits.")
        elif rsi < 30:
            st.info(f"RSI {rsi:.1f} — oversold (<30). Potential buying opportunity.")
        else:
            st.success(f"RSI {rsi:.1f} — neutral zone.")

    # Raw data expander
    with st.expander("View raw data"):
        raw = hist[["date", "price", "volume", "RSI", "MACD", "Signal"]].copy()
        raw["date"]   = raw["date"].dt.strftime("%Y-%m-%d")
        raw["price"]  = raw["price"].map("{:.2f}".format)
        raw["RSI"]    = raw["RSI"].map(lambda x: f"{x:.1f}"  if pd.notna(x) else "—")
        raw["MACD"]   = raw["MACD"].map(lambda x: f"{x:.4f}" if pd.notna(x) else "—")
        raw["Signal"] = raw["Signal"].map(lambda x: f"{x:.4f}" if pd.notna(x) else "—")
        st.dataframe(raw.iloc[::-1], use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: SECTOR ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Sector Analysis":

    st.markdown("""
    <style>
    .sector-hdr{font-size:10px;font-weight:800;color:#475569;text-transform:uppercase;
        letter-spacing:.12em;margin:1.5rem 0 .6rem;padding-left:4px}
    .bubble-wrap{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:.5rem}
    .stock-bubble{padding:8px 16px;border-radius:99px;font-size:13px;font-weight:700;
        cursor:pointer;border:1px solid;transition:all .15s;white-space:nowrap}
    .bubble-up  {background:rgba(34,197,94,0.12);border-color:rgba(34,197,94,0.35);color:#4ade80}
    .bubble-dn  {background:rgba(239,68,68,0.12);border-color:rgba(239,68,68,0.35);color:#f87171}
    .bubble-nt  {background:rgba(30,45,61,0.5);border-color:#1e2d3d;color:#64748b}
    .bubble-up:hover{background:rgba(34,197,94,0.2);transform:scale(1.05)}
    .bubble-dn:hover{background:rgba(239,68,68,0.2);transform:scale(1.05)}
    .bubble-nt:hover{background:#111827;color:#94a3b8;transform:scale(1.05)}
    </style>""", unsafe_allow_html=True)

    st.markdown("### Sector map")
    st.caption("Click any bubble to open full stock detail")

    if df_live.empty:
        st.error("No market data.")
        st.stop()

    # Build sector groups
    df_s = df_live.copy()
    df_s["sector"] = df_s["symbol"].map(SECTOR_MAP).fillna("Other")
    df_s["name"]   = df_s.apply(lambda r: _GSE_NAMES.get(str(r["symbol"]), str(r["name"])) if str(r["name"])==str(r["symbol"]) else str(r["name"]), axis=1)

    # Summary metric cards
    sector_df = df_s.groupby("sector").agg(
        avg_change=("change","mean"), total_volume=("volume","sum"), count=("symbol","count")
    ).reset_index().sort_values("avg_change", ascending=False)

    best  = sector_df.iloc[0]
    worst = sector_df.iloc[-1]
    c1,c2,c3 = st.columns(3)
    c1.metric("Best sector",     best["sector"],  f"{best['avg_change']:+.2f}%")
    c2.metric("Worst sector",    worst["sector"], f"{worst['avg_change']:+.2f}%")
    c3.metric("Sectors tracked", len(sector_df))

    st.divider()

    # ── Sector bubble map ────────────────────────────────────────────────────
    sector_order = ["Financials","Telecoms","Oil & Gas","Mining","Consumer Goods",
                    "Agribusiness","Manufacturing","Healthcare","Insurance","Real Estate","Other"]

    for sector in sector_order:
        stocks = df_s[df_s["sector"]==sector]
        if stocks.empty:
            continue
        st.markdown(f'<div class="sector-hdr">{sector}</div>', unsafe_allow_html=True)
        bubbles_html = '<div class="bubble-wrap">'
        for _, row in stocks.sort_values("change", ascending=False).iterrows():
            sym = str(row["symbol"])
            chg = float(row["change"])
            if chg > 0:
                cls = "bubble-up"; tag = f"+{chg:.1f}%"
            elif chg < 0:
                cls = "bubble-dn"; tag = f"{chg:.1f}%"
            else:
                cls = "bubble-nt"; tag = ""
            label = f"{sym} <span style='font-size:11px'>{tag}</span>" if tag else sym
            bubbles_html += f'<span class="stock-bubble {cls}">{label}</span>'
        bubbles_html += '</div>'
        st.markdown(bubbles_html, unsafe_allow_html=True)

        # Navigation handled by a single compact selectbox below the map
        pass

    st.divider()

    # ── Stock navigator ──────────────────────────────────────────────────────
    all_sec_syms = df_s["symbol"].tolist()
    nav_pick = st.selectbox(
        "Open stock detail:",
        [""] + all_sec_syms,
        format_func=lambda s: f"{s}  —  {_GSE_NAMES.get(s, s)}" if s else "Select a stock to open detail…",
        label_visibility="collapsed",
        key="sec_nav_pick",
    )
    if nav_pick:
        st.session_state["selected_symbol"] = nav_pick
        st.session_state.page = "Stock Detail"
        st.rerun()

    st.divider()

    # ── Sector performance bar chart ────────────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:0">Sector performance</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a:
        colors = ["#4ade80" if v>=0 else "#f87171" for v in sector_df["avg_change"]]
        fig_bar = go.Figure(go.Bar(
            x=sector_df["avg_change"].round(2), y=sector_df["sector"],
            orientation="h", marker_color=colors,
            text=sector_df["avg_change"].map("{:+.2f}%".format),
            textposition="outside", textfont=dict(color="#94a3b8", size=11),
        ))
        fig_bar.update_layout(
            height=340, margin=dict(l=0,r=50,t=10,b=0),
            plot_bgcolor="#080c16", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="#1e2d3d", tickfont=dict(color="#334155")),
            yaxis=dict(showgrid=False, tickfont=dict(color="#94a3b8")),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_b:
        fig_pie = px.pie(sector_df[sector_df["total_volume"]>0],
            values="total_volume", names="sector", hole=0.5,
            color_discrete_sequence=["#38bdf8","#4ade80","#fb923c","#a78bfa",
                "#f472b6","#34d399","#fbbf24","#f87171","#60a5fa","#86efac"])
        fig_pie.update_layout(
            height=340, margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="#080c16", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(font=dict(color="#475569",size=10),bgcolor="rgba(0,0,0,0)"),
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label",
            textfont=dict(size=10))
        st.plotly_chart(fig_pie, use_container_width=True)


elif page == "Compare Stocks":
    st.title("Compare stocks")
    st.caption("Side-by-side normalised price performance")

    if not symbols:
        st.error("Could not load market data.")
        st.stop()

    with st.sidebar:
        st.divider()
        st.markdown("**Comparison controls**")
        selected  = st.multiselect("Select 2–5 equities", symbols,
                                   default=symbols[:2], max_selections=5)
        period    = st.selectbox("Period", ["1M", "3M", "6M", "1Y", "All"], index=2)
        normalise = st.checkbox("Normalise to 100 (indexed)", value=True)

    if len(selected) < 2:
        st.info("Select at least 2 equities from the sidebar to compare.")
        st.stop()

    # Check if any history exists at all
    _has_any_history = any(not get_history(s).empty for s in selected)
    if not _has_any_history:
        st.markdown("""
        <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:14px;
             padding:28px;text-align:center;margin:2rem 0">
          <div style="font-size:20px;color:#38bdf8;margin-bottom:10px">📈</div>
          <div style="font-size:15px;font-weight:700;color:#e2e8f0;margin-bottom:8px">
            No historical data yet</div>
          <div style="font-size:13px;color:#475569;max-width:420px;margin:0 auto;line-height:1.6">
            Historical price data builds automatically each day the app runs during
            GSE market hours (10:00–15:00 GMT). Run the app daily and charts will
            appear here within a few days.</div>
        </div>""", unsafe_allow_html=True)
        st.stop()

    days = PERIOD_DAYS.get(period, 180)
    fig  = go.Figure()
    stats_rows = []

    for i, sym in enumerate(selected):
        hist = get_history(sym)
        if hist.empty:
            continue  # silently skip — no history yet
        hist = hist.tail(days).reset_index(drop=True)
        name_row = df_live[df_live["symbol"] == sym]
        name = name_row["name"].values[0] if not name_row.empty else sym

        y = hist["price"]
        if normalise and len(y) > 0 and y.iloc[0] != 0:
            y = (y / y.iloc[0]) * 100

        fig.add_trace(go.Scatter(
            x=hist["date"], y=y.round(2),
            name=f"{sym} — {name}",
            line=dict(color=CHART_COLORS[i % len(CHART_COLORS)], width=2),
            hovertemplate="%{y:.2f}<extra>" + sym + "</extra>",
        ))

        raw    = hist["price"]
        pct_chg = ((raw.iloc[-1] - raw.iloc[0]) / raw.iloc[0] * 100) if len(raw) > 1 else 0
        stats_rows.append({
            "Symbol": sym, "Company": name,
            f"Return ({period})": f"{pct_chg:+.2f}%",
            "High": f"GH₵ {raw.max():.2f}",
            "Low":  f"GH₵ {raw.min():.2f}",
            "Volatility": f"{raw.std():.2f}",
        })

    if normalise:
        fig.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.4)

    fig.update_layout(
        height=450, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="Indexed (base=100)" if normalise else "Price (GH₵)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    fig.update_xaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True)

    if stats_rows:
        st.subheader(f"Performance summary · {period}")
        st.dataframe(pd.DataFrame(stats_rows), use_container_width=True, hide_index=True)

    # Correlation heatmap
    if len(selected) >= 2:
        st.subheader("Return correlation")
        price_series = {}
        for sym in selected:
            h = get_history(sym)
            if not h.empty:
                price_series[sym] = h.tail(days).set_index("date")["price"]

        if len(price_series) >= 2:
            corr = pd.DataFrame(price_series).dropna().pct_change().corr().round(2)
            fig_corr = go.Figure(go.Heatmap(
                z=corr.values, x=corr.columns.tolist(), y=corr.index.tolist(),
                colorscale=[[0, "#E24B4A"], [0.5, "#F1EFE8"], [1, "#1D9E75"]],
                zmin=-1, zmax=1,
                text=corr.values.round(2), texttemplate="%{text}",
            ))
            fig_corr.update_layout(
                height=320, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_corr, use_container_width=True)
            st.caption("1.0 = perfectly correlated · 0 = uncorrelated · -1.0 = inverse")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: PORTFOLIO TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Portfolio":

    st.markdown("""
    <style>
    .port-header{font-size:26px;font-weight:800;color:#f1f5f9;margin-bottom:4px}
    .port-sub{font-size:13px;color:#475569;margin-bottom:1.5rem}
    .pf-card{background:#0d1117;border:1px solid #1e2d3d;border-radius:14px;padding:18px 22px;margin-bottom:10px}
    .pf-sym{font-size:16px;font-weight:700;color:#f1f5f9}
    .pf-name{font-size:11px;color:#475569;margin-top:2px}
    .pf-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:12px}
    .pf-metric{background:#111827;border-radius:10px;padding:10px 14px}
    .pf-mlbl{font-size:10px;color:#475569;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
    .pf-mval{font-size:15px;font-weight:700;color:#e2e8f0;font-family:monospace}
    .summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:1.5rem}
    .sum-card{background:#0d1117;border:1px solid #1e2d3d;border-radius:12px;padding:16px 20px;position:relative;overflow:hidden}
    .sum-card::before{content:"";position:absolute;top:0;left:0;right:0;height:2px}
    .sum-green::before{background:linear-gradient(90deg,#22c55e,#16a34a)}
    .sum-red::before{background:linear-gradient(90deg,#ef4444,#dc2626)}
    .sum-blue::before{background:linear-gradient(90deg,#38bdf8,#0ea5e9)}
    .sum-purple::before{background:linear-gradient(90deg,#a78bfa,#7c3aed)}
    .sum-lbl{font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
    .sum-val{font-size:24px;font-weight:800;line-height:1}
    </style>""", unsafe_allow_html=True)

    st.markdown('<div class="port-header">💼 Portfolio tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="port-sub">Track your GSE holdings, monitor P&L and returns in real time</div>', unsafe_allow_html=True)

    # ── Add holding form ──────────────────────────────────────────────────────
    with st.expander("➕ Add new holding", expanded=len(st.session_state.portfolio) == 0):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        pf_sym   = c1.selectbox("Symbol", symbols, key="pf_sym").upper() if symbols else c1.text_input("Symbol").upper()
        pf_shares = c2.number_input("Shares", min_value=1, value=100, step=1)
        pf_price  = c3.number_input("Buy price (GH₵)", min_value=0.01, value=1.00, step=0.01, format="%.2f")
        pf_date   = c4.date_input("Date", value=pd.Timestamp.today())
        if st.button("Add to portfolio", use_container_width=True):
            st.session_state.portfolio.append({
                "symbol":    pf_sym,
                "shares":    int(pf_shares),
                "buy_price": float(pf_price),
                "date":      str(pf_date),
            })
            st.success(f"Added {int(pf_shares):,} shares of {pf_sym} at GH₵ {pf_price:.2f}")
            st.rerun()

    if not st.session_state.portfolio:
        st.markdown('''<div style="text-align:center;padding:3rem;color:#334155;font-size:14px">
            No holdings yet. Add your first position above.</div>''', unsafe_allow_html=True)
    else:
        # ── Calculate P&L for each holding ───────────────────────────────────
        holdings = []
        for h in st.session_state.portfolio:
            sym         = h["symbol"]
            shares      = h["shares"]
            buy_price   = h["buy_price"]
            live_row    = df_live[df_live["symbol"] == sym]
            curr_price  = float(live_row["price"].values[0]) if not live_row.empty else buy_price
            cost_basis  = shares * buy_price
            curr_value  = shares * curr_price
            pnl         = curr_value - cost_basis
            pnl_pct     = (pnl / cost_basis * 100) if cost_basis > 0 else 0
            day_chg     = float(live_row["change"].values[0]) if not live_row.empty else 0.0
            day_pnl     = curr_value * day_chg / 100
            holdings.append({
                **h,
                "curr_price": curr_price,
                "cost_basis": cost_basis,
                "curr_value": curr_value,
                "pnl":        pnl,
                "pnl_pct":   pnl_pct,
                "day_chg":   day_chg,
                "day_pnl":   day_pnl,
            })

        total_cost  = sum(h["cost_basis"] for h in holdings)
        total_value = sum(h["curr_value"] for h in holdings)
        total_pnl   = total_value - total_cost
        total_pct   = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        day_total   = sum(h["day_pnl"] for h in holdings)

        # ── Portfolio summary cards ───────────────────────────────────────────
        pnl_color = "#4ade80" if total_pnl >= 0 else "#f87171"
        day_color = "#4ade80" if day_total >= 0 else "#f87171"
        pnl_cls   = "sum-green" if total_pnl >= 0 else "sum-red"
        day_cls   = "sum-green" if day_total >= 0 else "sum-red"

        st.markdown(f"""
        <div class="summary-grid">
          <div class="sum-card sum-blue">
            <div class="sum-lbl">Portfolio value</div>
            <div class="sum-val" style="color:#38bdf8">GH₵ {total_value:,.2f}</div>
            <div style="font-size:11px;color:#334155;margin-top:4px">{len(holdings)} positions</div>
          </div>
          <div class="sum-card sum-purple">
            <div class="sum-lbl">Cost basis</div>
            <div class="sum-val" style="color:#a78bfa">GH₵ {total_cost:,.2f}</div>
            <div style="font-size:11px;color:#334155;margin-top:4px">Total invested</div>
          </div>
          <div class="sum-card {pnl_cls}">
            <div class="sum-lbl">Total P&L</div>
            <div class="sum-val" style="color:{pnl_color}">{"+" if total_pnl>=0 else ""}GH₵ {total_pnl:,.2f}</div>
            <div style="font-size:11px;color:{pnl_color};margin-top:4px">{"+" if total_pct>=0 else ""}{total_pct:.2f}% overall</div>
          </div>
          <div class="sum-card {day_cls}">
            <div class="sum-lbl">Today's P&L</div>
            <div class="sum-val" style="color:{day_color}">{"+" if day_total>=0 else ""}GH₵ {day_total:,.2f}</div>
            <div style="font-size:11px;color:#334155;margin-top:4px">Based on today's change</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # ── Portfolio allocation donut chart ──────────────────────────────────
        col_chart, col_list = st.columns([1, 2])

        with col_chart:
            fig_alloc = go.Figure(go.Pie(
                labels=[h["symbol"] for h in holdings],
                values=[h["curr_value"] for h in holdings],
                hole=0.55,
                textinfo="label+percent",
                textfont=dict(size=12, color="#e2e8f0"),
                marker=dict(colors=["#38bdf8","#4ade80","#fb923c","#a78bfa","#f472b6","#34d399","#fbbf24","#f87171"]),
            ))
            fig_alloc.update_layout(
                height=280, margin=dict(l=0,r=0,t=20,b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                annotations=[dict(text="Allocation", x=0.5, y=0.5,
                    font=dict(size=12, color="#475569"), showarrow=False)],
            )
            st.plotly_chart(fig_alloc, use_container_width=True)

        # ── Holdings list ─────────────────────────────────────────────────────
        with col_list:
            for i, h in enumerate(holdings):
                sym      = h["symbol"]
                cname    = _GSE_NAMES.get(sym, sym)
                pnl_c    = "#4ade80" if h["pnl"] >= 0 else "#f87171"
                pnl_bg   = "rgba(34,197,94,0.07)" if h["pnl"] >= 0 else "rgba(239,68,68,0.07)"
                sign     = "+" if h["pnl"] >= 0 else ""
                day_c    = "#4ade80" if h["day_chg"] >= 0 else "#f87171"
                logo     = _load_logo_b64(sym)
                if logo:
                    av_html = f'<img src="{logo}" style="width:36px;height:36px;object-fit:contain;border-radius:7px;background:#0d1117;padding:3px;border:1px solid #1e2d3d">'
                else:
                    sc = _SC_COLORS.get(sym, "#0c2a4a,#38bdf8")
                    bg2, fg2 = sc.split(",")
                    av_html = f'<div style="width:36px;height:36px;border-radius:7px;background:{bg2};color:{fg2};font-size:12px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0">{sym[:2]}</div>'

                st.markdown(f"""
                <div class="pf-card">
                  <div style="display:flex;align-items:center;justify-content:space-between">
                    <div style="display:flex;align-items:center;gap:12px">
                      {av_html}
                      <div><div class="pf-sym">{sym}</div><div class="pf-name">{cname}</div></div>
                    </div>
                    <div style="text-align:right">
                      <div style="font-size:14px;font-weight:700;color:#e2e8f0">GH₵ {h["curr_price"]:.2f}</div>
                      <div style="font-size:11px;color:{day_c}">{"+" if h["day_chg"]>=0 else ""}{h["day_chg"]:.2f}% today</div>
                    </div>
                  </div>
                  <div class="pf-grid">
                    <div class="pf-metric"><div class="pf-mlbl">Shares</div><div class="pf-mval">{h["shares"]:,}</div></div>
                    <div class="pf-metric"><div class="pf-mlbl">Avg cost</div><div class="pf-mval">GH₵ {h["buy_price"]:.2f}</div></div>
                    <div class="pf-metric"><div class="pf-mlbl">Value</div><div class="pf-mval">GH₵ {h["curr_value"]:,.0f}</div></div>
                    <div class="pf-metric"><div class="pf-mlbl">P&L</div>
                      <div class="pf-mval" style="color:{pnl_c}">{sign}GH₵ {h["pnl"]:,.2f}</div></div>
                    <div class="pf-metric"><div class="pf-mlbl">Return</div>
                      <div class="pf-mval" style="color:{pnl_c}">{sign}{h["pnl_pct"]:.2f}%</div></div>
                  </div>
                </div>""", unsafe_allow_html=True)

                col_rm, _ = st.columns([1, 5])
                if col_rm.button("Remove", key=f"rm_hold_{i}_{sym}"):
                    st.session_state.portfolio.pop(i)
                    st.rerun()

        # ── Export portfolio as CSV ───────────────────────────────────────────
        st.divider()
        pf_df = pd.DataFrame([{
            "Symbol": h["symbol"], "Company": _GSE_NAMES.get(h["symbol"], h["symbol"]),
            "Shares": h["shares"], "Buy Price": h["buy_price"],
            "Current Price": h["curr_price"], "Cost Basis": round(h["cost_basis"],2),
            "Current Value": round(h["curr_value"],2), "P&L": round(h["pnl"],2),
            "Return (%)": round(h["pnl_pct"],2), "Date": h["date"],
        } for h in holdings])
        csv_bytes = pf_df.to_csv(index=False).encode()
        st.download_button(
            "⬇ Download portfolio CSV", csv_bytes,
            file_name=f"gse_portfolio_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv", use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: ADVANCED CHARTS
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Advanced Charts":

    st.markdown("""
    <style>
    /* ── Robinhood-style chart page ── */
    .rh-header { padding:0 0 1rem; }
    .rh-price  { font-size:42px; font-weight:800; color:#f1f5f9; line-height:1; font-family:monospace; }
    .rh-change { font-size:14px; font-weight:600; padding:4px 12px; border-radius:99px;
                 display:inline-flex; align-items:center; gap:5px; margin-top:6px; }
    .rh-change.up { background:rgba(34,197,94,0.15); color:#4ade80; }
    .rh-change.dn { background:rgba(239,68,68,0.15); color:#f87171; }
    .rh-status { font-size:12px; color:#475569; margin-top:4px; }
    .period-tabs { display:flex; gap:4px; margin:1rem 0 .5rem; }
    .period-tab  { padding:5px 14px; border-radius:99px; font-size:12px; font-weight:700;
                   cursor:pointer; border:none; color:#475569; background:transparent;
                   letter-spacing:.03em; transition:all .15s; }
    .period-tab.active { background:#1e2d3d; color:#38bdf8; }
    .overlay-tabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:.75rem; }
    .ov-tab { padding:4px 12px; border-radius:99px; font-size:11px; font-weight:700;
              cursor:pointer; border:1px solid #1e2d3d; color:#475569;
              background:transparent; letter-spacing:.03em; transition:all .15s; }
    .ov-tab.active { border-color:#38bdf8; color:#38bdf8; background:rgba(56,189,248,0.08); }
    .stat-bar { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; margin:1rem 0; }
    .stat-item { background:#0d1117; border:1px solid #1e2d3d; border-radius:10px;
                 padding:10px 12px; }
    .stat-lbl { font-size:9px; font-weight:700; color:#334155; text-transform:uppercase;
                letter-spacing:.08em; margin-bottom:3px; }
    .stat-val { font-size:14px; font-weight:700; color:#e2e8f0; font-family:monospace; }
    </style>""", unsafe_allow_html=True)

    if not symbols:
        st.error("No data available.")
        st.stop()

    # ── Controls in sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.divider()
        st.markdown('<div style="font-size:10px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Chart</div>', unsafe_allow_html=True)
        default_ac = st.session_state.get("selected_symbol", symbols[0])
        default_ac_idx = symbols.index(default_ac) if default_ac in symbols else 0
        ac_symbol  = st.selectbox("Symbol", symbols, index=default_ac_idx, key="ac_sym",
            format_func=lambda s: f"{s}  {_GSE_NAMES.get(s,s)[:18]}")
        ac_type    = st.radio("Chart type", ["Line","Area","Candlestick"],
            horizontal=True, key="ac_type", label_visibility="collapsed")
        st.markdown('<div style="font-size:10px;color:#475569;margin:8px 0 4px">Overlays</div>', unsafe_allow_html=True)
        show_bb    = st.checkbox("Bollinger Bands", value=True,  key="ac_bb")
        show_sma20 = st.checkbox("SMA 20",          value=False, key="ac_sma20")
        show_sma50 = st.checkbox("SMA 50",          value=False, key="ac_sma50")
        show_ema   = st.checkbox("EMA 12/26",       value=False, key="ac_ema")
        st.markdown('<div style="font-size:10px;color:#475569;margin:8px 0 4px">Indicators</div>', unsafe_allow_html=True)
        show_vol   = st.checkbox("Volume",   value=True,  key="ac_vol")
        show_rsi   = st.checkbox("RSI (14)", value=True,  key="ac_rsi")
        show_macd  = st.checkbox("MACD",     value=True,  key="ac_macd")

    # Period selector (Robinhood-style tabs)
    ac_period = st.radio("Period", ["1W","1M","3M","6M","1Y","YTD","All"],
        horizontal=True, index=3, key="ac_per", label_visibility="collapsed")

    hist = get_history(ac_symbol)
    if not hist.empty:
        hist = add_indicators(hist)
        period_map = {"1W":7,"1M":30,"3M":90,"6M":180,"1Y":365,"YTD":365,"All":99999}
        hist = hist.tail(period_map.get(ac_period, 180)).reset_index(drop=True)

    live_row   = df_live[df_live["symbol"] == ac_symbol]
    curr_name  = _GSE_NAMES.get(ac_symbol, ac_symbol)
    curr_price = float(live_row["price"].values[0])  if not live_row.empty else None
    curr_chg   = float(live_row["change"].values[0]) if not live_row.empty else 0.0
    chg_col    = "#4ade80" if curr_chg >= 0 else "#f87171"
    chg_bg     = "rgba(34,197,94,0.12)" if curr_chg >= 0 else "rgba(239,68,68,0.12)"
    chg_arrow  = "▲" if curr_chg >= 0 else "▼"
    logo_uri   = _load_logo_b64(ac_symbol)

    # ── Robinhood-style header ─────────────────────────────────────────────────
    logo_html = f'<img src="{logo_uri}" style="width:52px;height:52px;object-fit:contain;border-radius:12px;background:#0d1117;padding:4px;border:1px solid #1e2d3d">' if logo_uri else f'<div style="width:52px;height:52px;border-radius:12px;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#38bdf8">{ac_symbol[:2]}</div>'

    st.markdown(f"""
    <div style="display:flex;align-items:flex-start;gap:18px;margin-bottom:.5rem">
      {logo_html}
      <div>
        <div style="font-size:13px;font-weight:600;color:#475569;letter-spacing:.5px">{ac_symbol} &nbsp;·&nbsp; {curr_name}</div>
        <div class="rh-price">GH₵ {f"{curr_price:.2f}" if curr_price else "—"}</div>
        <span style="background:{chg_bg};color:{chg_col};font-size:13px;font-weight:700;
            padding:4px 12px;border-radius:99px;display:inline-flex;align-items:center;gap:5px;margin-top:6px">
          {chg_arrow} {"+" if curr_chg>=0 else ""}{curr_chg:.2f}% today
        </span>
        <div style="font-size:11px;color:#334155;margin-top:6px">
          {"● MARKET OPEN" if market_is_open() else "● Market closed"} &nbsp;·&nbsp; {datetime.now(timezone.utc).strftime("%d %b %Y %H:%M GMT")}
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Stats bar ─────────────────────────────────────────────────────────────
    if not hist.empty:
        rsi_val  = hist["RSI"].dropna().iloc[-1]  if not hist["RSI"].dropna().empty   else None
        macd_val = hist["MACD"].dropna().iloc[-1] if not hist["MACD"].dropna().empty  else None
        sig_val  = hist["Signal"].dropna().iloc[-1] if not hist["Signal"].dropna().empty else None
        hi52 = hist["price"].max(); lo52 = hist["price"].min()
        avg_vol = int(hist["volume"].mean())
        prange  = ((curr_price - lo52)/(hi52-lo52)*100) if (curr_price and hi52!=lo52) else 50
        ms      = "Bullish" if (macd_val and sig_val and macd_val > sig_val) else "Bearish"
        ms_col  = "#4ade80" if ms=="Bullish" else "#f87171"
        rsi_col = "#f87171" if (rsi_val and rsi_val>70) else "#4ade80" if (rsi_val and rsi_val<30) else "#e2e8f0"
        period_ret = ((hist["price"].iloc[-1]-hist["price"].iloc[0])/hist["price"].iloc[0]*100) if len(hist)>1 else 0
        ret_col = "#4ade80" if period_ret>=0 else "#f87171"

        st.markdown(f"""
        <div class="stat-bar">
          <div class="stat-item"><div class="stat-lbl">Period high</div>
            <div class="stat-val">GH₵ {hi52:.2f}</div></div>
          <div class="stat-item"><div class="stat-lbl">Period low</div>
            <div class="stat-val">GH₵ {lo52:.2f}</div></div>
          <div class="stat-item"><div class="stat-lbl">Period return</div>
            <div class="stat-val" style="color:{ret_col}">{"+" if period_ret>=0 else ""}{period_ret:.2f}%</div></div>
          <div class="stat-item"><div class="stat-lbl">Avg volume</div>
            <div class="stat-val">{avg_vol:,}</div></div>
          <div class="stat-item"><div class="stat-lbl">RSI (14)</div>
            <div class="stat-val" style="color:{rsi_col}">{f"{rsi_val:.1f}" if rsi_val else "—"}</div></div>
          <div class="stat-item"><div class="stat-lbl">MACD signal</div>
            <div class="stat-val" style="color:{ms_col}">{ms}</div></div>
        </div>""", unsafe_allow_html=True)

    if hist.empty:
        st.info("No historical data yet — data builds daily when the app runs during market hours.")
        st.stop()

    # ── Build chart ───────────────────────────────────────────────────────────
    n_rows = 1 + (1 if show_rsi else 0) + (1 if show_macd else 0)
    heights = [0.60]
    titles  = [""]
    if show_rsi:  heights.append(0.20); titles.append("RSI (14)")
    if show_macd: heights.append(0.20); titles.append("MACD")
    total = sum(heights)
    heights = [h/total for h in heights]

    fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True,
        row_heights=heights, vertical_spacing=0.02, subplot_titles=titles)

    # Main chart — Robinhood green area by default
    line_color = "#4ade80" if (len(hist)>1 and hist["price"].iloc[-1] >= hist["price"].iloc[0]) else "#f87171"
    fill_color = "rgba(34,197,94,0.08)" if line_color=="#4ade80" else "rgba(239,68,68,0.08)"

    if ac_type == "Candlestick" and "open" in hist.columns:
        fig.add_trace(go.Candlestick(x=hist["date"],
            open=hist.get("open", hist["price"]), high=hist.get("high", hist["price"]),
            low=hist.get("low", hist["price"]),   close=hist["price"],
            increasing=dict(line_color="#4ade80", fillcolor="rgba(34,197,94,0.7)"),
            decreasing=dict(line_color="#f87171", fillcolor="rgba(239,68,68,0.7)"),
            name="OHLC"), row=1, col=1)
    elif ac_type == "Area":
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["price"], name="Price",
            fill="tozeroy", fillcolor=fill_color,
            line=dict(color=line_color, width=2.5)), row=1, col=1)
    else:  # Line (default — Robinhood style)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["price"], name="Price",
            fill="tozeroy", fillcolor=fill_color,
            line=dict(color=line_color, width=2.5, shape="spline", smoothing=0.5),
            hovertemplate="GH₵ %{y:.2f}<extra></extra>"), row=1, col=1)

    # Bollinger Bands
    if show_bb and "BB_Upper" in hist.columns:
        for band, name in [("BB_Upper","BB+"), ("BB_Lower","BB-")]:
            fig.add_trace(go.Scatter(x=hist["date"], y=hist[band], name=name,
                line=dict(color="rgba(71,85,105,0.5)", width=1, dash="dot"),
                showlegend=(name=="BB+")), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["BB_Lower"],
            fill="tonexty", fillcolor="rgba(71,85,105,0.05)",
            line=dict(width=0), showlegend=False), row=1, col=1)

    if show_sma20 and "BB_Mid" in hist.columns:
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["BB_Mid"], name="SMA 20",
            line=dict(color="#fbbf24", width=1.5, dash="dot")), row=1, col=1)
    if show_sma50 and "SMA50" in hist.columns:
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["SMA50"], name="SMA 50",
            line=dict(color="#fb923c", width=1.5, dash="dot")), row=1, col=1)
    if show_ema:
        ema12 = hist["price"].ewm(span=12, adjust=False).mean()
        ema26 = hist["price"].ewm(span=26, adjust=False).mean()
        fig.add_trace(go.Scatter(x=hist["date"], y=ema12, name="EMA 12",
            line=dict(color="#a78bfa", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist["date"], y=ema26, name="EMA 26",
            line=dict(color="#f472b6", width=1.5)), row=1, col=1)

    # Volume bars (colour-matched to price direction per bar)
    if show_vol:
        vol_colors = [line_color if i==0 else
            ("#4ade80" if hist["price"].iloc[i] >= hist["price"].iloc[i-1] else "#f87171")
            for i in range(len(hist))]
        fig.add_trace(go.Bar(x=hist["date"], y=hist["volume"],
            name="Volume", marker_color=vol_colors, opacity=0.35,
            yaxis="y2"), row=1, col=1)

    # RSI row
    rsi_row = 2 if show_rsi else None
    if show_rsi:
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["RSI"], name="RSI",
            line=dict(color="#a78bfa", width=1.8)), row=rsi_row, col=1)
        fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,68,68,0.04)", line_width=0,
            row=rsi_row, col=1)
        fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(34,197,94,0.04)", line_width=0,
            row=rsi_row, col=1)
        for lvl, col in [(70,"#f87171"),(50,"#334155"),(30,"#4ade80")]:
            fig.add_hline(y=lvl, line_dash="dot", line_color=col, opacity=0.4,
                row=rsi_row, col=1)

    # MACD row
    macd_row = (3 if show_rsi else 2) if show_macd else None
    if show_macd:
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["MACD"], name="MACD",
            line=dict(color="#38bdf8", width=1.8)), row=macd_row, col=1)
        fig.add_trace(go.Scatter(x=hist["date"], y=hist["Signal"], name="Signal",
            line=dict(color="#fbbf24", width=1.8)), row=macd_row, col=1)
        hc = ["#4ade80" if v>=0 else "#f87171" for v in hist["MACD_Hist"].fillna(0)]
        fig.add_trace(go.Bar(x=hist["date"], y=hist["MACD_Hist"],
            name="Histogram", marker_color=hc, opacity=0.6), row=macd_row, col=1)

    # ── Layout — clean Robinhood-style ────────────────────────────────────────
    fig.update_layout(
        height=620, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="#080c16", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#475569", family="monospace", size=11),
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
            bgcolor="rgba(0,0,0,0)", font=dict(color="#475569", size=10)),
        hoverlabel=dict(bgcolor="#0d1117", bordercolor="#1e2d3d",
            font=dict(color="#e2e8f0", size=12)),
    )
    # Axis styling — minimal gridlines like Robinhood
    for i in range(1, n_rows+1):
        fig.update_yaxes(row=i, col=1,
            showgrid=True, gridcolor="rgba(30,45,61,0.6)", gridwidth=1,
            zeroline=False, showline=False,
            tickfont=dict(color="#334155", size=10),
            tickformat=".2f")
        fig.update_xaxes(row=i, col=1,
            showgrid=False, zeroline=False, showline=False,
            tickfont=dict(color="#334155", size=10))

    st.plotly_chart(fig, use_container_width=True, config={
        "displayModeBar": True,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["select2d","lasso2d","autoScale2d"],
        "modeBarButtonsToAdd": ["drawline","drawopenpath","eraseshape"],
        "toImageButtonOptions": {"format":"png","filename":f"GSE_{ac_symbol}_{ac_period}"},
    })

    # ── RSI interpretation banner ────────────────────────────────────────────
    if not hist.empty and "RSI" in hist.columns:
        rsi_vals = hist["RSI"].dropna()
        if not rsi_vals.empty:
            rv = rsi_vals.iloc[-1]
            if rv > 70:
                st.markdown(f'<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);border-radius:10px;padding:12px 16px;font-size:13px;color:#f87171">⚠️ <b>RSI {rv:.1f}</b> — Overbought. Price may be due for a pullback.</div>', unsafe_allow_html=True)
            elif rv < 30:
                st.markdown(f'<div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.3);border-radius:10px;padding:12px 16px;font-size:13px;color:#4ade80">✅ <b>RSI {rv:.1f}</b> — Oversold. Potential accumulation zone.</div>', unsafe_allow_html=True)

    # ── Raw data ─────────────────────────────────────────────────────────────
    with st.expander("📋 Raw data"):
        raw = hist[["date","price","volume","RSI","MACD","Signal"]].copy()
        raw["date"] = raw["date"].dt.strftime("%Y-%m-%d")
        for c in ["price","RSI","MACD","Signal"]:
            raw[c] = raw[c].map(lambda x: f"{x:.4f}" if pd.notna(x) else "—")
        raw["volume"] = raw["volume"].map(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
        st.dataframe(raw.iloc[::-1], use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: DAILY MARKET REVIEW  (BlackStar-style)
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Market Review":

    today_str = datetime.now(timezone.utc).strftime("%d %b %Y")

    st.markdown(f"""
    <style>
    .mr-header{{display:flex;align-items:center;justify-content:space-between;
        padding:20px 24px;background:#0d1117;border:1px solid #1e2d3d;
        border-radius:14px;margin-bottom:1.25rem}}
    .mr-title{{font-size:22px;font-weight:800;color:#f1f5f9;letter-spacing:-.3px}}
    .mr-date {{font-size:14px;color:#475569;margin-top:3px}}
    .mr-brand{{font-size:13px;font-weight:700;color:#38bdf8;letter-spacing:.5px}}
    .mr-section{{font-size:10px;font-weight:800;color:#38bdf8;text-transform:uppercase;
        letter-spacing:.14em;margin:1.5rem 0 .75rem;display:flex;align-items:center;gap:10px}}
    .mr-section::before{{content:"";width:3px;height:14px;background:#38bdf8;border-radius:2px}}
    .mr-section::after{{content:"";flex:1;height:1px;background:linear-gradient(90deg,#1e2d3d,transparent)}}
    .mover-table{{width:100%;border-collapse:collapse;font-size:13px}}
    .mover-table th{{padding:9px 14px;text-align:left;font-size:10px;font-weight:700;
        color:#475569;text-transform:uppercase;letter-spacing:.06em;
        border-bottom:1px solid #1e2d3d;background:#111827}}
    .mover-table td{{padding:10px 14px;border-bottom:1px solid #0d1117;color:#e2e8f0}}
    .mover-table tr:hover td{{background:#111827}}
    .mover-table tr:last-child td{{border-bottom:none}}
    .idx-card{{background:#0d1117;border:1px solid #1e2d3d;border-radius:12px;
        padding:16px 20px;text-align:center;position:relative;overflow:hidden}}
    .idx-card::before{{content:"";position:absolute;top:0;left:0;right:0;height:2px;
        background:linear-gradient(90deg,#22c55e,#16a34a)}}
    .idx-lbl{{font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;
        letter-spacing:.08em;margin-bottom:6px}}
    .idx-val{{font-size:24px;font-weight:800;color:#4ade80;font-family:monospace}}
    .idx-sub{{font-size:11px;color:#334155;margin-top:4px}}
    </style>
    <div class="mr-header">
      <div>
        <div class="mr-title">Daily Equity Market Review</div>
        <div class="mr-date">{today_str} &nbsp;·&nbsp; Ghana Stock Exchange</div>
      </div>
      <div class="mr-brand">BismarkDataLab Inc</div>
    </div>""", unsafe_allow_html=True)

    if df_live.empty:
        st.error("No market data available.")
        st.stop()

    summary = market_summary(df_live)
    total_vol = summary.get("total_volume", 0)
    vol_bn    = df_live["price"].mul(df_live["volume"]).sum()

    # ── Market standings ───────────────────────────────────────────────────────
    st.markdown('<div class="mr-section">Market standings</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    mktcap_label = "243.85bn"  # Static until API provides it
    c1.markdown(f"""<div class="idx-card" style="border-top-color:#38bdf8">
        <div class="idx-lbl">Market Cap (GHS)</div>
        <div class="idx-val" style="color:#38bdf8">{mktcap_label}</div>
        <div class="idx-sub">Total market capitalisation</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="idx-card" style="border-top-color:#a78bfa">
        <div class="idx-lbl">Volume Traded</div>
        <div class="idx-val" style="color:#a78bfa">{total_vol/1e6:.2f}M</div>
        <div class="idx-sub">Shares traded today</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class="idx-card" style="border-top-color:#fbbf24">
        <div class="idx-lbl">Value Traded (GHS)</div>
        <div class="idx-val" style="color:#fbbf24">{vol_bn/1e6:.2f}M</div>
        <div class="idx-sub">Market turnover</div></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class="idx-card">
        <div class="idx-lbl">Advancers / Decliners</div>
        <div class="idx-val"><span style="color:#4ade80">{summary["gainers"]}</span>
          <span style="color:#334155;font-size:16px"> / </span>
          <span style="color:#f87171">{summary["losers"]}</span></div>
        <div class="idx-sub">{summary["unchanged"]} unchanged</div></div>""", unsafe_allow_html=True)

    # ── Day-end market movers ──────────────────────────────────────────────────
    st.markdown('<div class="mr-section">Day-end market movers</div>', unsafe_allow_html=True)

    movers = df_live[df_live["change"] != 0].copy()
    movers["prev_price"] = movers["price"] / (1 + movers["change"]/100)
    movers["price_chg"]  = movers["price"] - movers["prev_price"]
    movers = movers.sort_values("change", key=abs, ascending=False).head(12)

    rows_html = ""
    for _, r in movers.iterrows():
        sym   = str(r["symbol"])
        name  = _GSE_NAMES.get(sym, sym)
        prev  = r["prev_price"]
        close = r["price"]
        pchg  = r["price_chg"]
        pchg_pct = r["change"]
        col   = "#4ade80" if pchg >= 0 else "#f87171"
        arrow = "▲" if pchg >= 0 else "▼"
        logo  = _load_logo_b64(sym)
        av_html = f'<img src="{logo}" style="width:26px;height:26px;object-fit:contain;border-radius:5px;background:#0d1117;padding:2px">' if logo else f'<div style="width:26px;height:26px;border-radius:5px;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:900;color:#38bdf8">{sym[:2]}</div>'
        rows_html += f"""<tr>
          <td><div style="display:flex;align-items:center;gap:8px">{av_html}
            <div><div style="font-weight:700;color:#f1f5f9">{sym}</div>
            <div style="font-size:10px;color:#475569">{name[:28]}</div></div></div></td>
          <td style="font-family:monospace;color:#94a3b8">GH₵ {prev:.2f}</td>
          <td style="font-family:monospace;font-weight:700;color:#e2e8f0">GH₵ {close:.2f}</td>
          <td style="font-family:monospace;color:{col}">{arrow} {abs(pchg):.2f}</td>
          <td><span style="background:{"rgba(34,197,94,0.1)" if pchg>=0 else "rgba(239,68,68,0.1)"};
              color:{col};padding:3px 8px;border-radius:99px;font-size:12px;font-weight:700;
              font-family:monospace">{arrow} {abs(pchg_pct):.2f}%</span></td>
          <td style="font-family:monospace;color:#475569">{int(r["volume"]):,}</td>
        </tr>"""

    st.markdown(f"""
    <div style="border:1px solid #1e2d3d;border-radius:14px;overflow:hidden">
    <table class="mover-table">
      <thead><tr>
        <th>Ticker</th><th>Prev close</th><th>Close price</th>
        <th>Price chg</th><th>Chg %</th><th>Volume</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table></div>""", unsafe_allow_html=True)

    # ── Top 5 Volume & Value ───────────────────────────────────────────────────
    st.markdown('<div class="mr-section">Volume & value leaders</div>', unsafe_allow_html=True)
    col_v, col_val = st.columns(2)

    top_vol = df_live.nlargest(5, "volume")[["symbol","price","volume"]].copy()
    top_val = df_live.copy()
    top_val["value"] = top_val["price"] * top_val["volume"]
    top_val = top_val.nlargest(5, "value")[["symbol","price","volume","value"]]

    with col_v:
        st.markdown("**Top 5 volume traded**")
        max_vol = top_vol["volume"].max()
        for _, r in top_vol.iterrows():
            sym = str(r["symbol"])
            pct = r["volume"] / max_vol
            logo = _load_logo_b64(sym)
            av = f'<img src="{logo}" style="width:22px;height:22px;object-fit:contain;border-radius:4px">' if logo else f'<div style="width:22px;height:22px;border-radius:4px;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:900;color:#38bdf8">{sym[:2]}</div>'
            chg_r = df_live[df_live["symbol"]==sym]
            chg_v = float(chg_r["change"].values[0]) if not chg_r.empty else 0
            bar_c = "#4ade80" if chg_v >= 0 else "#f87171"
            vol_str = f"{int(r['volume'])/1000:.1f}K" if r["volume"]>=1000 else str(int(r["volume"]))
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              {av}
              <div style="flex:1">
                <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                  <span style="font-size:12px;font-weight:700;color:#e2e8f0">{sym}</span>
                  <span style="font-size:11px;color:#94a3b8;font-family:monospace">{vol_str}</span>
                </div>
                <div style="height:5px;background:#1e2d3d;border-radius:3px">
                  <div style="width:{pct*100:.0f}%;height:5px;background:{bar_c};border-radius:3px"></div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

    with col_val:
        st.markdown("**Top 5 value traded (GHS)**")
        max_val = top_val["value"].max()
        for _, r in top_val.iterrows():
            sym = str(r["symbol"])
            pct = r["value"] / max_val
            logo = _load_logo_b64(sym)
            av = f'<img src="{logo}" style="width:22px;height:22px;object-fit:contain;border-radius:4px">' if logo else f'<div style="width:22px;height:22px;border-radius:4px;background:#0c2a4a;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:900;color:#38bdf8">{sym[:2]}</div>'
            val_str = f"GH₵ {r['value']/1e6:.2f}M" if r["value"]>=1e6 else f"GH₵ {r['value']/1e3:.1f}K"
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              {av}
              <div style="flex:1">
                <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                  <span style="font-size:12px;font-weight:700;color:#e2e8f0">{sym}</span>
                  <span style="font-size:11px;color:#94a3b8;font-family:monospace">{val_str}</span>
                </div>
                <div style="height:5px;background:#1e2d3d;border-radius:3px">
                  <div style="width:{pct*100:.0f}%;height:5px;background:#38bdf8;border-radius:3px"></div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

    # ── YTD performance area chart ─────────────────────────────────────────────
    st.markdown('<div class="mr-section">YTD market performance</div>', unsafe_allow_html=True)
    csv_hist = load_historical_comparison("MTNGH")
    if not csv_hist.empty and len(csv_hist) > 5:
        all_syms = df_live["symbol"].tolist()
        fin_syms = [s for s in all_syms if _GSE_COMPANIES.get(s,{}).get("sector")=="Financials"]
        nonfin_syms = [s for s in all_syms if _GSE_COMPANIES.get(s,{}).get("sector")!="Financials"]

        fig_ytd = go.Figure()
        fig_ytd.add_trace(go.Scatter(x=csv_hist["date"], y=csv_hist["price"],
            fill="tozeroy", fillcolor="rgba(234,179,8,0.15)",
            line=dict(color="#eab308", width=2), name="Sample (MTNGH)"))
        fig_ytd.update_layout(
            height=240, margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="#080c16", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, tickfont=dict(color="#334155", size=10)),
            yaxis=dict(showgrid=True, gridcolor="#1e2d3d", tickfont=dict(color="#334155", size=10)),
            legend=dict(font=dict(color="#475569", size=10), bgcolor="rgba(0,0,0,0)"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_ytd, use_container_width=True)
    else:
        st.markdown('<div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:12px;padding:20px;text-align:center;color:#334155;font-size:13px">YTD chart builds as daily snapshots accumulate in gse_history.csv</div>', unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="margin-top:2rem;padding:14px 0;border-top:1px solid #1e2d3d;
         font-size:11px;color:#334155;line-height:1.6">
      <i>Sources: Ghana Stock Exchange, dev.kwayisi.org/apis/gse · Compiled by BismarkDataLab Inc</i><br>
      <i>The information has been compiled from sources we believe to be reliable but do not hold ourselves
      responsible for its completeness or accuracy. Not investment advice.</i>
    </div>""", unsafe_allow_html=True)
