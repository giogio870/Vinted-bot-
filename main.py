# BOT VINTED RESELL V5.2 FINAL GITHUB
# WINTER STRATEGY: selected models, controlled buy ceilings, low fake/capital risk.
# NO luxury/high-counterfeit targets; no auto-purchase is performed by the bot.
# Scanner Discord + filtri + scoring + notifiche.
# NOTE: segnala opportunita', NON acquista automaticamente.
#
# ENV:
#   DISCORD_TOKEN
#   DISCORD_CHANNEL_ID (opzionale)
#   SCAN_INTERVAL (default 10, minimo 8)
#   FRESHNESS_SECONDS (default 180, minimo 30)
#   TRADE_FACTOR (default 0.95)
#   DISCORD_PING_MODE (none/here/everyone, default none)
#   VINTED_403_COOLDOWN_SECONDS (default 300)
#
# IMPORTANTE:
# - freshness usa SOLO il timestamp dell'annuncio, mai quello della foto.
# - timestamp mancante/non valido = scarto.
# - niente cuori nello scoring.
# - 403 Vinted = nessun retry aggressivo.
# - gli annunci diventano "visti" solo dopo una notifica Discord riuscita.
# - stato persistente su SQLite (state.db); su Render serve un disco persistente.
# - modelli a margine stretto/capitale alto rimossi dalla strategia.

import asyncio
import logging
import os
import re
import time
import unicodedata
import urllib.parse
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import sqlite3
import threading
from flask import Flask, jsonify
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("vinted-bot")

# ================================================================
# ENV / CONFIG
# ================================================================

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_RAW = os.getenv("DISCORD_CHANNEL_ID", "").strip()

try:
    DISCORD_CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None
except ValueError:
    DISCORD_CHANNEL_ID = None

def env_int(name, default, minimum):
    try:
        value = int(os.getenv(name, str(default)))
        return value if value >= minimum else minimum
    except ValueError:
        return default

SCAN_INTERVAL = env_int("SCAN_INTERVAL", 10, 8)
FRESHNESS_SECONDS = min(env_int("FRESHNESS_SECONDS", 180, 30), 180)

try:
    TRADE_FACTOR = float(os.getenv("TRADE_FACTOR", "0.95"))
except ValueError:
    TRADE_FACTOR = 0.95

TRADE_FACTOR = min(max(TRADE_FACTOR, 0.50), 1.00)

PING_MODE = os.getenv("DISCORD_PING_MODE", "none").strip().lower()
if PING_MODE not in {"none", "here", "everyone"}:
    PING_MODE = "none"

VINTED_403_COOLDOWN = env_int("VINTED_403_COOLDOWN_SECONDS", 300, 60)

cfg_runtime = {
    "trattativa": TRADE_FACTOR,
    "max_secondi_freschezza": FRESHNESS_SECONDS,
    "scan_interval": SCAN_INTERVAL,
}

BASE_DIR = Path(__file__).resolve().parent
STATE_DB_PATH = Path(os.getenv("STATE_DB_PATH", str(BASE_DIR / "state.db")))

try:
    SELLER_COST_RATE = float(os.getenv("SELLER_COST_RATE", "0.0"))
except ValueError:
    SELLER_COST_RATE = 0.0
SELLER_COST_RATE = min(max(SELLER_COST_RATE, 0.0), 0.50)

try:
    SELLER_FIXED_COST = float(os.getenv("SELLER_FIXED_COST", "0.0"))
except ValueError:
    SELLER_FIXED_COST = 0.0
SELLER_FIXED_COST = max(0.0, SELLER_FIXED_COST)

# ================================================================
# DISCORD
# ================================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

canale_notifiche = None
scanner_task = None
report_task = None
scanner_lock = None

# ================================================================
# STATS
# ================================================================

def nuove_stats():
    return {
        "scaricati": 0,
        "alert": 0,
        "auto_buy": 0,
        "brand_no": 0,
        "modello_no": 0,
        "escluso_difetto": 0,
        "escluso_stile": 0,
        "condizione_no": 0,
        "taglia_no": 0,
        "seller_rischio": 0,
        "profitto_basso": 0,
        "freshness_sconosciuto": 0,
        "freshness_no": 0,
        "bambino": 0,
        "duplicati": 0,
        "rate_limit": 0,
        "errori_http": 0,
        "http_403": 0,
        "notifiche_fallite": 0,
    }

stats = nuove_stats()

# ================================================================
# UTILITY
# ================================================================

def normalizza(testo):
    try:
        return (
            unicodedata.normalize("NFKD", str(testo))
            .encode("ascii", "ignore")
            .decode("ascii")
            .lower()
        )
    except Exception:
        return str(testo).lower()

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

_RX_CACHE = {}

def match_parola_intera(keyword, testo):
    key = normalizza(keyword).strip()
    if not key:
        return False

    rx = _RX_CACHE.get(key)
    if rx is None:
        rx = re.compile(
            r"(?<!\w)"
            + re.escape(key).replace(r"\ ", r"\s+")
            + r"(?!\w)",
            re.I,
        )
        _RX_CACHE[key] = rx

    return rx.search(normalizza(testo)) is not None

# ================================================================
# BRAND
# ================================================================

BRAND_ALIASES = {
    "carhartt wip": [
        "carhartt wip", "carhartt", "carharrt", "carrhartt", "carhart"
    ],
    "the north face": [
        "the north face", "north face", "nort face", "northface", "tnf"
    ],
    "arc'teryx": [
        "arc'teryx", "arcteryx", "arc teryx"
    ],
    "patagonia": ["patagonia"],
    "nike": ["nike", "nikke"],
    "timberland": ["timberland", "timberlands"],
    "ralph lauren": [
        "ralph lauren", "polo ralph lauren", "raulph lauren", "ralf lauren"
    ],
    "stone island": [
        "stone island", "stoneisland", "ston island", "stone islan"
    ],
    "stussy": ["stussy"],
    "new balance": ["new balance", "newbalance"],
    "ugg": ["ugg", "uggs"],
    "barbour": ["barbour"],
    "woolrich": ["woolrich"],
    "moncler": ["moncler", "moncler genius", "moncler grenoble"],
    "canada goose": ["canada goose"],
    "gucci": ["gucci"],
    "prada": ["prada"],
    "dior": ["dior"],
    "balenciaga": ["balenciaga"],
    "louis vuitton": ["louis vuitton", "lv"],
}

def alias_in(alias, testo):
    return match_parola_intera(alias, testo)

# ================================================================
# DIFETTI
# ================================================================

# Queste frasi hanno priorita' assoluta: non devono mai essere "annullate"
# da una generica negazione come "non".
DIFETTI_ASSOLUTI = [
    "non originale",
    "non autentico",
    "non autentica",
    "autenticita dubbia",
    "non so se originale",
    "non so se autentico",
    "non so se autentica",
    "non garantisco autenticita",
    "replica",
    "fake",
    "falso",
    "falsa",
    "contraffatto",
    "contraffatta",
    "badge falso",
    "badge non originale",
]

DIFETTI_GENERICI = [
    "macchia", "macchie", "macchiato", "macchiata",
    "sporco", "sporca", "sporchi", "sporche",
    "scolorito", "scolorita", "scolorimento",
    "strappo", "strappata", "strappato",
    "buco", "buchi", "foro", "fori",
    "zip rotta", "cerniera rotta", "zip difettosa",
    "cerniera difettosa", "cucitura rotta",
    "danneggiato", "danneggiata", "rovinato", "rovinata",
    "difetto", "difetti", "usura evidente",
    "molto usato", "molto usata",
    "da riparare", "da sistemare", "riparazione",
    "custom", "personalizzato", "personalizzata",
    "modificato", "modificata",
    "tarme", "tarmato", "tarmata",
    "pilling forte", "usura forte",
    "sgonfio", "sgonfia",
    "perde piume", "piume fuori", "piuma fuori",
    "suola staccata", "suola rotta", "pelle rotta",
    "crepe", "deformata", "deformato",
    "lacci mancanti", "tessuto consumato",
    "gore tex danneggiato", "membrana danneggiata",
    "riparato",
]

NEGAZIONE_RE = re.compile(
    r"\b(?:senza|nessun|nessuna|nessuno|non|mai|zero|niente)\b",
    re.I,
)

def _difetto_negato(testo, start, end):
    # Considera solo una finestra breve prima del difetto.
    # Le negazioni generiche annullano il difetto solo se sono
    # chiaramente riferite a quella parola. Le frasi di autenticita'
    # restano invece assolute e sono gia' controllate prima.
    prima = testo[max(0, start - 55):start]
    return bool(NEGAZIONE_RE.search(prima))

def ha_difetto(testo):
    tl = normalizza(testo)

    # Esclusioni assolute: priorita' massima.
    for difetto in DIFETTI_ASSOLUTI:
        if match_parola_intera(difetto, tl):
            return True, difetto

    for difetto in DIFETTI_GENERICI:
        key = "DEF:" + difetto
        rx = _RX_CACHE.get(key)
        if rx is None:
            rx = re.compile(
                r"(?<!\w)"
                + re.escape(normalizza(difetto)).replace(r"\ ", r"\s+")
                + r"(?!\w)",
                re.I,
            )
            _RX_CACHE[key] = rx

        for m in rx.finditer(tl):
            if _difetto_negato(tl, m.start(), m.end()):
                continue
            return True, difetto

    return False, ""

# ================================================================
# STILE
# ================================================================

STILE_PATTERN = re.compile(
    r"(?<!\w)(?:simile a|ispirato a|inspired by|inspired)(?!\w)",
    re.I,
)

def ha_pattern_stile(testo, brand):
    tl = normalizza(testo)

    aliases = BRAND_ALIASES.get(brand, [])
    if not aliases:
        return False

    for match in STILE_PATTERN.finditer(tl):
        finestra = tl[
            max(0, match.start() - 80):
            min(len(tl), match.end() + 80)
        ]

        if any(alias_in(alias, finestra) for alias in aliases):
            return True

    return False

# ================================================================
# BAMBINI
# ================================================================

BAMBINO_PATTERN = re.compile(
    r"(?<!\w)(?:bambino|bambina|bambini|bambine|"
    r"bimbo|bimba|bimbi|bimbe|junior|kids?|children?|child)(?!\w)",
    re.I,
)

BAMBINO_ETA_PATTERN = re.compile(
    r"\b(\d{1,2})\s*anni\b",
    re.I,
)

BAMBINO_CODICI_PATTERN = re.compile(
    r"\b(?:152|164|176|yl|ym)\b",
    re.I,
)

def is_bambino(testo, taglia):
    tl = normalizza(testo)

    if BAMBINO_PATTERN.search(tl):
        return True

    for match in BAMBINO_ETA_PATTERN.finditer(tl):
        try:
            if int(match.group(1)) < 18:
                return True
        except ValueError:
            pass

    tg = str(taglia or "")
    if re.search(r"\bann(?:i|o)?\b", tg, re.I):
        return True

    return bool(BAMBINO_CODICI_PATTERN.search(tg))

# ================================================================
# CONDIZIONI
# ================================================================

CONDIZIONI_API_MAP = {
    "nuovo con etichette": "nuovo con cartellino",
    "new_with_tags": "nuovo con cartellino",
    "nuovo senza etichette": "nuovo senza cartellino",
    "new_without_tags": "nuovo senza cartellino",
    "nuovo": "nuovo",
    "new": "nuovo",
    "ottime": "ottime",
    "very_good": "ottime",
    "molto buono": "molto buono",
    "buone": "buone",
    "good": "buone",
    "discrete": "discrete",
    "satisfactory": "discrete",
    "sufficiente": "sufficiente",
}

CONDIZIONI_KEYWORDS = {
    "nuovo con cartellino": [
        "nuovo con cartellino", "nuovo con etichette",
        "new with tags", "brand new with tags", "nwt"
    ],
    "nuovo senza cartellino": [
        "nuovo senza cartellino", "nuovo senza etichette",
        "new without tags", "brand new without tags", "nwot"
    ],
    "nuovo": ["nuovo", "new", "brand new"],
    "ottime": ["ottime condizioni", "ottime"],
    "molto buono": ["molto buono", "molto buona"],
    "buone": ["buone condizioni", "buone"],
    "discrete": ["discrete condizioni", "discrete", "soddisfacenti"],
    "sufficiente": ["sufficiente"],
}

TAGLIE_RIFIUTA_GLOBALE = ["XXS"]

BUONE_AMMESSE = {
    "tnf_nuptse",
    "carhartt_detroit",
    "timberland_wheat",
    "tnf_denali",
    "barbour_bedale_beaufort",
    "woolrich_arctic",
    "patagonia_down_sweater",
    "patagonia_nano_puff",
}

DISCRETE_AMMESSE = {
    "timberland_wheat",
}

# ================================================================
# COLORE
# ================================================================

COLORE_BLOCCANTE = {
    "timberland_wheat": {
        "richiedi_uno": [
            "wheat", "yellow", "giallo", "gialla", "grano"
        ],
    },
    "carhartt_detroit": {
        "se_keyword_in": ["hamilton brown", "detroit brown"],
        "rifiuta_se_contiene": ["black", "nero", "blue", "navy"],
    },
}

def colore_ok(model_id, testo, keyword_matchata):
    regola = COLORE_BLOCCANTE.get(model_id)
    if not regola:
        return True

    tl = normalizza(testo)

    if "richiedi_uno" in regola:
        return any(
            match_parola_intera(x, tl)
            for x in regola["richiedi_uno"]
        )

    if any(
        normalizza(keyword_matchata) == normalizza(x)
        for x in regola.get("se_keyword_in", [])
    ):
        return not any(
            match_parola_intera(x, tl)
            for x in regola.get("rifiuta_se_contiene", [])
        )

    return True

# ================================================================
# SELLER
# ================================================================

SELLER_RISCHIO_BRANDS = [
    "arc'teryx",
    "stone island",
    "the north face",
    "carhartt wip",
    "stussy",
    "nike",
    "ugg",
    "new balance",
]

AUTH_RISK_BRANDS = {
    "the north face",
    "arc'teryx",
    "stone island",
    "carhartt wip",
    "stussy",
    "nike",
    "ugg",
    "new balance",
}

# Brand che escludiamo esplicitamente dalla strategia low-capital:
# troppo capitale e/o rischio contraffazione per il margine cercato.
BRAND_BLOCCATI = {
    "moncler",
    "canada goose",
    "gucci",
    "prada",
    "dior",
    "balenciaga",
    "louis vuitton",
}

def seller_rischioso(item):
    user = item.get("user") or {}

    if user.get("feedback_count") is None and user.get("item_count") is None:
        return False

    fb = safe_int(user.get("feedback_count"), 0)
    items = safe_int(user.get("item_count"), 0)
    rep = safe_float(user.get("feedback_reputation"), 1.0)

    return (
        (fb == 0 and items < 5)
        or
        (fb < 3 and rep < 0.8 and items < 10)
    )

# ================================================================
# STONE ISLAND / CERTILOGO
# ================================================================

def evidenza_certilogo(descrizione):
    """Richiede un codice CLG/Certilogo plausibile di 12 cifre."""
    d = normalizza(descrizione)
    compact12 = r"(?:\d[\s\-]?){12}"
    return bool(
        re.search(r"\bclg\s*[:#\-]?\s*" + compact12 + r"\b", d, re.I)
        or re.search(r"\bcertilogo\b.{0,30}\b" + compact12 + r"\b", d, re.I)
        or re.search(r"\b" + compact12 + r"\b.{0,30}\bcertilogo\b", d, re.I)
    )

def authenticity_warning(brand, descrizione):
    return brand == "stone island" and not evidenza_certilogo(descrizione)

# ================================================================
# MODELLI
# ================================================================


def M(
    model_id,
    brand,
    nome,
    query,
    keywords,
    condizioni,
    sell_min,
    sell_max,
    profit_min,
    **extra,
):
    return {
        "id": model_id,
        "brand": brand,
        "nome": nome,
        "query": query,
        "keywords": keywords,
        "condizioni": condizioni,
        "sell_min": sell_min,
        "sell_max": sell_max,
        "profit_min": profit_min,
        **extra,
    }


# Strategia low-capital: pochi modelli, margine realistico,
# rotazione abbastanza veloce e rischio contraffazione contenuto.
MODELLI = [
    M(
        "tnf_nuptse", "the north face", "1996/1990 Retro Nuptse",
        "the north face nuptse",
        [
            "1996 retro nuptse", "nuptse 1996", "1996 nuptse",
            "1990 retro nuptse", "nuptse 1990", "retro nuptse",
            "nuptse 700", "700 nuptse", "nupste", "nuptze",
        ],
        {
            "ottime": {"auto_buy": 20, "buy_max": 30},
            "buone": {"buy_max": 30},
            "nuovo senza cartellino": {"buy_max": 40},
            "nuovo con cartellino": {"buy_max": 40},
        },
        90, 120, 30,
        taglie_rifiuta=["XS"],
        escludi_se=["baltoro", "gilet", "vest", "smanicato", "chaleco", "sin mangas"],
    ),
    M(
        "carhartt_detroit", "carhartt wip", "Detroit/Michigan/Active Jacket",
        "carhartt detroit jacket",
        [
            "og detroit", "detroit jacket", "michigan coat", "active jacket",
            "carhartt wip detroit", "carhartt detroit", "hamilton brown", "detroit brown",
        ],
        {
            "ottime": {"auto_buy": 30, "buy_max": 40},
            "buone": {"auto_buy": 25, "buy_max": 35},
            "nuovo senza cartellino": {"buy_max": 45},
            "nuovo con cartellino": {"buy_max": 60},
        },
        70, 110, 30,
        taglie_rifiuta=["XS"],
    ),
    M(
        "tnf_denali", "the north face", "Denali Fleece",
        "the north face denali",
        ["denali fleece", "denali jacket", "tnf denali", "north face denali"],
        {
            "ottime": {"auto_buy": 15, "buy_max": 25},
            "buone": {"buy_max": 20},
            "nuovo senza cartellino": {"buy_max": 30},
            "nuovo con cartellino": {"buy_max": 40},
        },
        45, 70, 20,
        taglie_rifiuta=["XS", "XXS"],
        escludi_se=["gilet", "vest", "smanicato"],
    ),
    M(
        "barbour_bedale", "barbour", "Bedale/Beaufort",
        "barbour bedale beaufort",
        ["bedale", "beaufort", "barbour bedale", "barbour beaufort", "barbour border"],
        {
            "ottime": {"auto_buy": 25, "buy_max": 40},
            "buone": {"auto_buy": 20, "buy_max": 35},
            "nuovo senza cartellino": {"buy_max": 55},
            "nuovo con cartellino": {"buy_max": 70},
        },
        80, 120, 30,
        taglie_rifiuta=["XS"],
        escludi_se=["bambino", "kids", "gilet", "vest", "smanicato"],
    ),
    M(
        "patagonia_retrox", "patagonia", "Retro-X",
        "patagonia retro x",
        ["retro-x", "retro x", "classic retro-x"],
        {
            "ottime": {"auto_buy": 20, "buy_max": 30},
            "buone": {"buy_max": 25},
            "nuovo con cartellino": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        65, 100, 25,
    ),
    M(
        "patagonia_down_sweater", "patagonia", "Down Sweater",
        "patagonia down sweater",
        ["down sweater", "patagonia down", "down sweater jacket"],
        {
            "ottime": {"auto_buy": 20, "buy_max": 30},
            "buone": {"buy_max": 25},
            "nuovo con cartellino": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        65, 95, 25,
        escludi_se=["gilet", "vest", "smanicato"],
    ),
    M(
        "patagonia_nano_puff", "patagonia", "Nano Puff",
        "patagonia nano puff",
        ["nano puff", "nano-puff", "patagonia nano"],
        {
            "ottime": {"auto_buy": 18, "buy_max": 28},
            "buone": {"buy_max": 25},
            "nuovo con cartellino": {"buy_max": 38},
            "nuovo senza cartellino": {"buy_max": 38},
        },
        60, 90, 25,
        escludi_se=["gilet", "vest", "smanicato"],
    ),
    M(
        "timberland_wheat", "timberland", "Premium 6-Inch Wheat",
        "timberland premium 6 inch wheat",
        [
            "premium 6-inch wheat", "premium 6 inch wheat", "6-inch premium",
            "6 inch premium", "wheat boot", "wheat premium",
        ],
        {
            "ottime": {"auto_buy": 20, "buy_max": 30},
            "buone": {"auto_buy": 15, "buy_max": 25},
            "nuovo": {"buy_max": 40},
            "nuovo con cartellino": {"buy_max": 45},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        55, 80, 25,
        taglie_alert_extra=["36", "37", "38"],
        discrete_eccezione={"buy_max": 18},
    ),
    M(
        "ugg_ultramini", "ugg", "Ultra Mini",
        "ugg ultra mini",
        ["ultra mini", "ugg ultra-mini"],
        {
            "ottime": {"auto_buy": 20, "buy_max": 30},
            "buone": {"buy_max": 25},
            "nuovo senza cartellino": {"buy_max": 40},
            "nuovo con cartellino": {"buy_max": 45},
        },
        55, 80, 25,
        escludi_se=["kids", "bambino", "bimba", "bimbo"],
    ),
    M(
        "woolrich_arctic", "woolrich", "Arctic Parka",
        "woolrich arctic parka",
        ["arctic parka", "woolrich arctic", "arctic jacket", "woolrich parka"],
        {
            "ottime": {"auto_buy": 25, "buy_max": 35},
            "buone": {"buy_max": 30},
            "nuovo senza cartellino": {"buy_max": 45},
            "nuovo con cartellino": {"buy_max": 60},
        },
        70, 105, 25,
        taglie_rifiuta=["XS"],
        escludi_se=["bambino", "kids", "gilet", "vest", "smanicato"],
    ),
]

# Tutti i modelli non presenti sopra sono volutamente fuori strategia.
MODELLI_RIMOSSI = set()


# ================================================================
# FRESHNESS
# ================================================================

def estrai_created_ts(item):
    """
    Usa SOLO il timestamp dell'annuncio.
    Non usa mai photo.high_resolution.timestamp.
    """
    raw = item.get("created_at_ts")

    if raw is None:
        raw = item.get("created_at")

    if raw is None:
        return None

    try:
        if isinstance(raw, str):
            raw_clean = raw.strip()

            try:
                value = float(raw_clean)
            except ValueError:
                return datetime.fromisoformat(
                    raw_clean.replace("Z", "+00:00")
                ).timestamp()
            else:
                ts = value
        else:
            ts = float(raw)

        if ts > 1e11:
            ts /= 1000.0

        # Timestamp palesemente invalido.
        if ts <= 0 or ts > time.time() + 300:
            return None

        return ts

    except Exception:
        return None

def freshness_item(item):
    ts = estrai_created_ts(item)

    if ts is None:
        return None

    return max(0.0, time.time() - ts)

# ================================================================
# MODEL MATCH
# ================================================================

def match_modello(modello, testo):
    tl = normalizza(testo)

    for esclusione in modello.get("escludi_se", []):
        if match_parola_intera(esclusione, tl):
            return None

    aliases = BRAND_ALIASES.get(modello["brand"], [])

    for keyword in modello.get("keywords", []):
        key = normalizza(keyword)
        matches = list(re.finditer(
            r"(?<!\w)" + re.escape(key).replace(r"\ ", r"\s+") + r"(?!\w)",
            tl,
            re.I,
        ))
        if not matches:
            continue

        if len(key) <= 12:
            vicino = False
            for m in matches:
                finestra = tl[max(0, m.start()-90):min(len(tl), m.end()+90)]
                if any(alias_in(a, finestra) for a in aliases):
                    vicino = True
                    break
            if not vicino:
                continue

        richiesti = modello.get("richiedi_secondo")
        if richiesti and not any(match_parola_intera(r, tl) for r in richiesti):
            continue

        return keyword

    return None

# ================================================================
# CONDIZIONE / TAGLIA
# ================================================================

def condizione_da_item(item, titolo, descrizione):
    status = normalizza(
        str(item.get("status", "") or "").strip()
    )

    if status in CONDIZIONI_API_MAP:
        return CONDIZIONI_API_MAP[status]

    testo = (
        status
        + " "
        + normalizza(titolo)
        + " "
        + normalizza(descrizione)
    )

    ordine = [
        "nuovo con cartellino",
        "nuovo senza cartellino",
        "nuovo",
        "ottime",
        "molto buono",
        "buone",
        "discrete",
        "sufficiente",
    ]

    for condizione in ordine:
        for keyword in CONDIZIONI_KEYWORDS.get(condizione, []):
            if match_parola_intera(keyword, testo):
                return condizione

    return ""

def taglia_da_item(item):
    raw = str(item.get("size_title", "") or "")
    return raw.split("/")[0].strip().upper()

# ================================================================
# PROFITTO / SCORE
# ================================================================

def calcola_profitto(modello, prezzo):
    """
    Profitto netto stimato lato venditore.
    La Protezione acquisti e' mostrata da Vinted al compratore e non viene
    sottratta automaticamente dal ricavo del venditore.
    Costi extra reali possono essere configurati via ENV.
    """
    sell_riferimento = float(modello["sell_min"])
    ricavo = sell_riferimento * cfg_runtime["trattativa"]
    costi_extra = ricavo * SELLER_COST_RATE + SELLER_FIXED_COST
    profitto = ricavo - costi_extra - prezzo
    return round(profitto, 2), sell_riferimento

def calcola_score(
    modello,
    condizione,
    prezzo,
    profitto,
    seller_rischio,
    freshness,
):
    # 100 punti senza cuori:
    # profitto 40 + prezzo 25 + freshness 20 + condizione 15.
    score = 0

    if profitto >= modello["profit_min"] + 40:
        score += 40
    elif profitto >= modello["profit_min"] + 20:
        score += 30
    elif profitto >= modello["profit_min"]:
        score += 20

    block = modello["condizioni"].get(condizione)
    buy_max = block.get("buy_max") if block else None

    if buy_max:
        ratio = prezzo / max(float(buy_max), 1)

        if ratio <= 0.50:
            score += 25
        elif ratio <= 0.75:
            score += 20
        elif ratio <= 1:
            score += 10

    if freshness <= 30:
        score += 20
    elif freshness <= 90:
        score += 16
    elif freshness <= 180:
        score += 10

    if condizione in ("nuovo", "nuovo con cartellino"):
        score += 15
    elif condizione == "ottime":
        score += 12
    elif condizione == "buone":
        score += 5

    if seller_rischio:
        score -= 15

    return max(0, min(100, score))

# ================================================================
# VALUTAZIONE
# ================================================================

def valuta_item(item):
    titolo = str(item.get("title", "") or "")
    descrizione = str(item.get("description", "") or "")[:1000]
    testo_completo = titolo + " " + descrizione

    prezzo = safe_float(
        (item.get("price") or {}).get("amount")
    )

    if prezzo <= 0:
        return None

    # 1) Bambino
    taglia = taglia_da_item(item)

    if is_bambino(testo_completo, taglia):
        stats["bambino"] += 1
        return None

    # 2) Difetti
    difetto, _ = ha_difetto(testo_completo)

    if difetto:
        stats["escluso_difetto"] += 1
        return None

    # 3) Brand
    foto_url = (
        (item.get("photo") or {}).get("url", "")
        or ""
    ).strip()

    if not foto_url:
        stats["modello_no"] += 1
        return None

    brand_text = (
        titolo
        + " "
        + str(item.get("brand_title", "") or "")
    )

    brands_trovati = []

    for brand, aliases in BRAND_ALIASES.items():
        if any(alias_in(alias, brand_text) for alias in aliases):
            brands_trovati.append(brand)

    if not brands_trovati:
        stats["brand_no"] += 1
        return None

    if any(b in BRAND_BLOCCATI for b in brands_trovati):
        stats["brand_no"] += 1
        return None

    # 4) Modello
    modello_trovato = None
    keyword_matchata = None

    for modello in MODELLI:
        if modello["brand"] not in brands_trovati:
            continue

        keyword = match_modello(
            modello,
            testo_completo,
        )

        if keyword is not None:
            modello_trovato = modello
            keyword_matchata = keyword
            break

    if modello_trovato is None:
        stats["modello_no"] += 1
        return None

    # 5) Freshness rigorosa 0-180 sec (config runtime)
    freshness = freshness_item(item)

    if freshness is None:
        stats["freshness_sconosciuto"] += 1
        return None

    if freshness > cfg_runtime["max_secondi_freschezza"]:
        stats["freshness_no"] += 1
        return None

    # 6) Stile
    if ha_pattern_stile(
        testo_completo,
        modello_trovato["brand"],
    ):
        stats["escluso_stile"] += 1
        return None

    # 7) Colore
    if not colore_ok(
        modello_trovato["id"],
        testo_completo,
        keyword_matchata,
    ):
        stats["modello_no"] += 1
        return None

    # 8) Taglia obbligatoria
    if modello_trovato.get("richiedi_taglia"):
        if not taglia or "UNICA" in taglia:
            stats["modello_no"] += 1
            return None

    # 9) Seller
    seller_rischio = seller_rischioso(item)

    if (
        modello_trovato["brand"] in SELLER_RISCHIO_BRANDS
        and seller_rischio
    ):
        stats["seller_rischio"] += 1
        return None

    # 10) Condizione
    condizione = condizione_da_item(
        item,
        titolo,
        descrizione,
    )

    if not condizione:
        stats["condizione_no"] += 1
        return None

    if (
        condizione == "buone"
        and modello_trovato["id"] not in BUONE_AMMESSE
    ):
        stats["condizione_no"] += 1
        return None

    if (
        condizione == "discrete"
        and modello_trovato["id"] not in DISCRETE_AMMESSE
    ):
        stats["condizione_no"] += 1
        return None

    # 11) Blocco condizione / buy max
    if condizione == "discrete":
        eccezione = modello_trovato.get("discrete_eccezione")

        if not eccezione:
            stats["condizione_no"] += 1
            return None

        cond_block = {"buy_max": eccezione["buy_max"]}
        auto_buy_soglia = None

    else:
        cond_block = modello_trovato["condizioni"].get(condizione)

        if (
            cond_block is None
            and condizione == "molto buono"
        ):
            base = modello_trovato["condizioni"].get("ottime")

            if base:
                cond_block = {
                    "buy_max": round(
                        base.get("buy_max", 0) * 0.90
                    )
                }

        if (
            cond_block is None
            and condizione in (
                "nuovo con cartellino",
                "nuovo senza cartellino",
            )
        ):
            cond_block = modello_trovato["condizioni"].get("nuovo")

        if cond_block is None:
            stats["condizione_no"] += 1
            return None

        auto_buy_soglia = cond_block.get("auto_buy")

    buy_max = safe_float(cond_block.get("buy_max"))

    if prezzo > buy_max:
        return None

    # 12) Taglie rifiutate
    taglie_rifiuta = (
        modello_trovato.get("taglie_rifiuta", [])
        + TAGLIE_RIFIUTA_GLOBALE
    )

    if taglia in [str(x).upper() for x in taglie_rifiuta]:
        stats["taglia_no"] += 1
        return None

    soglia_s = modello_trovato.get("taglia_s_solo_sotto")

    if (
        soglia_s is not None
        and taglia == "S"
        and prezzo >= soglia_s
    ):
        stats["taglia_no"] += 1
        return None

    # 13) Profitto
    profitto_stimato, sell_riferimento = calcola_profitto(
        modello_trovato,
        prezzo,
    )

    if profitto_stimato < modello_trovato["profit_min"]:
        stats["profitto_basso"] += 1
        return None

    # 14) Tier
    tier = "ALERT"

    if (
        auto_buy_soglia is not None
        and prezzo <= auto_buy_soglia
    ):
        tier = "AUTO-BUY SIGNAL"

    # Stone Island molto economico senza evidenza di codice
    auth_warning = authenticity_warning(
        modello_trovato["brand"],
        descrizione,
    )

    if auth_warning:
        tier = "ALERT"

    # Taglie extra Timberland: solo AUTO-BUY
    taglie_extra = modello_trovato.get("taglie_alert_extra", [])

    if (
        taglia in [str(x).upper() for x in taglie_extra]
        and tier != "AUTO-BUY SIGNAL"
    ):
        stats["taglia_no"] += 1
        return None

    score = calcola_score(
        modello_trovato,
        condizione,
        prezzo,
        profitto_stimato,
        seller_rischio,
        freshness,
    )

    return {
        "modello": modello_trovato,
        "tier": tier,
        "score": score,
        "condizione": condizione,
        "prezzo": prezzo,
        "buy_max": buy_max,
        "auto_buy_soglia": auto_buy_soglia,
        "profitto_stimato": profitto_stimato,
        "sell_usato": sell_riferimento,
        "taglia": taglia,
        "titolo": titolo,
        "descrizione": descrizione,
        "iid": str(item.get("id", "")),
        "url": (
            "https://www.vinted.it/items/"
            + str(item.get("id", ""))
        ),
        "foto": (
            (item.get("photo") or {}).get("url", "")
            or ""
        ),
        "seller_rischio": seller_rischio,
        "freshness": freshness,
        "auth_warning": auth_warning,
    }

# ================================================================
# PERSISTENZA SQLITE
# ================================================================

gia_visti = OrderedDict()
ultimo_affare = None
affari_recenti = OrderedDict()
blacklist_ids = set()

def init_db():
    STATE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(STATE_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                item_id TEXT PRIMARY KEY,
                notified_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                item_id TEXT PRIMARY KEY,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()

def carica_stato():
    global gia_visti, blacklist_ids
    try:
        init_db()
        with sqlite3.connect(STATE_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT item_id, notified_at FROM seen "
                "ORDER BY notified_at ASC LIMIT 10000"
            ).fetchall()
            gia_visti = OrderedDict(
                (str(iid), float(ts)) for iid, ts in rows
            )
            blacklist_ids = {
                str(iid).strip()
                for (iid,) in conn.execute("SELECT item_id FROM blacklist").fetchall()
                if str(iid).strip().isdigit()
            }
        log.info(
            "Stato SQLite caricato: %s visti, %s blacklist",
            len(gia_visti),
            len(blacklist_ids),
        )
    except Exception as exc:
        log.warning("Errore caricamento SQLite: %s", exc)
        gia_visti = OrderedDict()
        blacklist_ids = set()

def salva_visti():
    try:
        with sqlite3.connect(STATE_DB_PATH) as conn:
            conn.executemany(
                "INSERT INTO seen(item_id, notified_at) VALUES(?, ?) "
                "ON CONFLICT(item_id) DO UPDATE SET notified_at=excluded.notified_at",
                [(str(iid), float(ts)) for iid, ts in gia_visti.items()],
            )
            conn.execute("""
                DELETE FROM seen
                WHERE item_id NOT IN (
                    SELECT item_id FROM seen
                    ORDER BY notified_at DESC
                    LIMIT 10000
                )
            """)
            conn.commit()
    except Exception as exc:
        log.warning("Errore salvataggio visti SQLite: %s", exc)

def add_blacklist(iid):
    iid = str(iid).strip()
    if not iid.isdigit():
        return False
    blacklist_ids.add(iid)
    try:
        with sqlite3.connect(STATE_DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO blacklist(item_id, created_at) VALUES(?, ?)",
                (iid, time.time()),
            )
            conn.commit()
        return True
    except Exception as exc:
        log.warning("Errore blacklist SQLite: %s", exc)
        return False

def remove_blacklist(iid):
    iid = str(iid).strip()
    if iid not in blacklist_ids:
        return False
    blacklist_ids.remove(iid)
    try:
        with sqlite3.connect(STATE_DB_PATH) as conn:
            conn.execute("DELETE FROM blacklist WHERE item_id = ?", (iid,))
            conn.commit()
        return True
    except Exception as exc:
        log.warning("Errore rimozione blacklist SQLite: %s", exc)
        return False

def is_blacklisted(iid):
    return str(iid).strip() in blacklist_ids

carica_stato()

# ================================================================
# HTTP VINTED
# ================================================================

vinted_browser = None
vinted_context = None
vinted_page = None
vinted_403_until = 0.0
vinted_browser_ready = False

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BROWSER_PROFILE_DIR = Path(os.getenv(
    "VINTED_BROWSER_PROFILE",
    str(BASE_DIR / "vinted_browser_profile"),
))

async def crea_sessione_vinted():
    """Avvia un browser Chrome reale e mantiene una sessione persistente.

    Non usa token/cookie forniti dall'utente e non tenta bypass di CAPTCHA
    o sistemi anti-bot. Se Vinted blocca la sessione, il bot si ferma
    temporaneamente e riprova più tardi.
    """
    global vinted_browser, vinted_context, vinted_page, vinted_browser_ready

    if vinted_page is not None and not vinted_page.is_closed():
        return vinted_page

    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    pw = await async_playwright().start()

    try:
        vinted_context = await pw.chromium.launch_persistent_context(
             user_data_dir=str(BROWSER_PROFILE_DIR),
             channel="chrome",
            headless=True,
            viewport={"width": 1440, "height": 900},
            locale="it-IT",
            user_agent=USER_AGENT,
            args=["--disable-notifications"],
)

        )
    except Exception:
        # Fallback al Chromium installato da Playwright. Nessun bypass.
        vinted_context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=os.getenv("VINTED_HEADLESS", "false").strip().lower() == "true",
            viewport={"width": 1440, "height": 900},
            locale="it-IT",
            user_agent=USER_AGENT,
            args=["--disable-notifications"],
        )

    vinted_browser = pw
    vinted_page = vinted_context.pages[0] if vinted_context.pages else await vinted_context.new_page()
    vinted_browser_ready = False

    try:
        response = await vinted_page.goto(
            "https://www.vinted.it/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        status = response.status if response else 0
        if status in (401, 403, 429):
            log.warning("Vinted homepage HTTP %s: sessione browser non pronta.", status)
        else:
            vinted_browser_ready = True
            log.info("Sessione browser Vinted pronta | homepage=%s", status)
    except PlaywrightTimeoutError:
        log.warning("Timeout caricamento homepage Vinted.")
    except Exception as exc:
        log.warning("Errore apertura homepage Vinted: %s", exc)

    return vinted_page

async def chiudi_sessione_vinted():
    global vinted_browser, vinted_context, vinted_page, vinted_browser_ready

    try:
        if vinted_context is not None:
            await vinted_context.close()
    except Exception:
        pass

    try:
        if vinted_browser is not None:
            await vinted_browser.stop()
    except Exception:
        pass

    vinted_browser = None
    vinted_context = None
    vinted_page = None
    vinted_browser_ready = False

async def vinted_catalog_browser(page, query):
    """Carica la ricerca Vinted dal browser e cattura la risposta catalogo.

    La richiesta API, se presente, e' quella generata dalla normale pagina
    Vinted nel browser. Non vengono creati token, cookie o header speciali.
    """
    global vinted_403_until

    if time.time() < vinted_403_until:
        return None

    encoded = urllib.parse.quote(query)
    url = (
        "https://www.vinted.it/catalog"
        f"?search_text={encoded}"
        "&order=newest_first"
    )

    captured = {"data": None, "status": None}

    async def on_response(response):
        if "/api/v2/catalog/items" not in response.url:
            return
        if response.status != 200:
            captured["status"] = response.status
            return
        try:
            captured["data"] = await response.json()
        except Exception:
            pass

    page.on("response", on_response)
    try:
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        homepage_status = response.status if response else 0

        # Lascia il tempo al frontend di effettuare la normale chiamata catalogo.
        for _ in range(12):
            if captured["data"] is not None:
                break
            await asyncio.sleep(0.5)

        if captured["data"] is not None:
            return captured["data"]

        status = captured["status"] or homepage_status
        if status == 403:
            stats["http_403"] += 1
            vinted_403_until = time.time() + VINTED_403_COOLDOWN
            log.error(
                "Vinted ha restituito HTTP 403 dal browser: pausa %ss; nessun bypass.",
                VINTED_403_COOLDOWN,
            )
        elif status == 429:
            stats["rate_limit"] += 1
            log.warning("Vinted ha restituito HTTP 429 dal browser.")
        elif status:
            stats["errori_http"] += 1
            log.warning("HTTP %s su Vinted browser per query '%s'.", status, query)
        else:
            stats["errori_http"] += 1
            log.warning("Nessuna risposta catalogo catturata per '%s'.", query)

        return None
    except PlaywrightTimeoutError:
        stats["errori_http"] += 1
        log.warning("Timeout ricerca Vinted browser: %s", query)
        return None
    except Exception as exc:
        stats["errori_http"] += 1
        log.warning("Errore Vinted browser per '%s': %s", query, exc)
        return None
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

# ================================================================
# QUERY / SCHEDULER
# ================================================================

QUERY_FISSE = [
    "the north face nuptse",
    "carhartt wip detroit",
    "the north face denali",
    "barbour bedale",
    "barbour beaufort",
]

QUERY_SECONDARIE = [
    "patagonia retro x",
    "patagonia down sweater",
    "patagonia nano puff",
    "timberland premium 6 inch wheat",
    "ugg ultra mini",
    "woolrich arctic parka",
]

query_next_due = {
    query: 0.0
    for query in QUERY_SECONDARIE
}

nuovi_dal_salvataggio = 0
cicli_dal_salvataggio = 0

# ================================================================
# NOTIFICHE
# ================================================================

async def invia_notifica(res):
    global canale_notifiche

    if canale_notifiche is None:
        return False

    modello = res["modello"]

    if res["tier"] == "AUTO-BUY SIGNAL":
        emoji = "🟩"
        colore = 0x2ECC71
    else:
        emoji = "🟨"
        colore = 0xF1C40F

    if PING_MODE == "everyone":
        ping = "@everyone"
    elif PING_MODE == "here":
        ping = "@here"
    else:
        ping = None

    auto_buy = (
        f"{res['auto_buy_soglia']} EUR"
        if res["auto_buy_soglia"] is not None
        else "n.d."
    )

    extra = ""

    if str(res["taglia"]) in [
        str(x) for x in modello.get("taglie_alert_extra", [])
    ]:
        extra += " | TAGLIA RICERCATA"

    if res["seller_rischio"]:
        extra += " | SELLER DA VERIFICARE"

    titolo_embed = (
        f"{emoji} {res['tier']} | "
        f"{modello['brand'].upper()} "
        f"{modello['nome']} | "
        f"{res['prezzo']:.2f} EUR"
    )

    desc = (
        f"**{res['titolo']}**{extra}\n\n"
        f"**Score:** {res['score']}/100\n"
        f"**Modello:** {modello['nome']}\n"
        f"**Condizione:** {res['condizione']}\n"
        f"**Taglia:** {res['taglia'] or 'n.d.'}\n"
        f"**Prezzo:** {res['prezzo']:.2f} EUR\n"
        f"**AUTO-BUY max:** {auto_buy}\n"
        f"**BUY MAX:** {res['buy_max']:.2f} EUR\n"
        f"**SELL conservativo:** "
        f"{modello['sell_min']}-{modello['sell_max']} EUR\n"
        f"**Profitto netto stimato:** "
        f"+{res['profitto_stimato']:.2f} EUR\n"
        f"**Profitto minimo:** "
        f"{modello['profit_min']} EUR\n"
        f"**Freshness:** "
        f"{round(res['freshness'])} sec\n\n"
        "Controlla sempre foto, etichette, codici "
        "e autenticita' prima di comprare.\n"
        + ("⚠️ AUTENTICITÀ DA VERIFICARE: manca evidenza CLG/QR.\n"
           if res.get("auth_warning") else "")
        + "\n"
        + f"[VAI ALL'ANNUNCIO]({res['url']})"
    )

    embed = discord.Embed(
        title=titolo_embed,
        description=desc,
        color=colore,
    )

    if res.get("foto"):
        try:
            embed.set_image(url=res["foto"])
        except Exception:
            pass

    try:
        await canale_notifiche.send(
            content=ping,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=(PING_MODE in {"here", "everyone"}),
                roles=False,
                users=False,
            ),
        )

        return True

    except Exception as exc:
        stats["notifiche_fallite"] += 1

        log.error(
            "Errore notifica Discord: %s",
            exc,
        )

        return False

# ================================================================
# SCANSIONE
# ================================================================

async def scansione_query(
    page,
    query,
):
    global ultimo_affare
    global nuovi_dal_salvataggio

    data = await vinted_catalog_browser(page, query)

    if data is None:
        return

    items = data.get("items", [])

    if not isinstance(items, list):
        return

    # Evita doppio processing nello stesso risultato/ciclo,
    # senza trasformare ogni item in "visto" prima dei filtri.
    ciclo_processati = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        iid = str(item.get("id", ""))

        if not iid:
            continue

        if iid in ciclo_processati:
            continue

        ciclo_processati.add(iid)

        # gia_visti = notificati con successo.
        if iid in gia_visti:
            stats["duplicati"] += 1
            continue

        stats["scaricati"] += 1

        # Freshness rigorosa prima di tutto.
        freshness = freshness_item(item)

        if freshness is None:
            stats["freshness_sconosciuto"] += 1
            continue

        if freshness > cfg_runtime["max_secondi_freschezza"]:
            stats["freshness_no"] += 1
            continue

        if is_blacklisted(iid):
            continue

        risultato = valuta_item(item)

        if not risultato:
            continue

        # NON segnare come visto prima della notifica.
        notificato = await invia_notifica(
            risultato
        )

        if not notificato:
            continue

        gia_visti[iid] = time.time()

        while len(gia_visti) > 10000:
            gia_visti.popitem(last=False)

        ultimo_affare = {
            "titolo": risultato["titolo"],
            "id": iid,
            "prezzo": risultato["prezzo"],
            "ts": time.time(),
        }

        affari_recenti[iid] = {
            "titolo": risultato["titolo"],
            "ts": time.time(),
        }

        while len(affari_recenti) > 200:
            affari_recenti.popitem(last=False)

        if risultato["tier"] == "AUTO-BUY SIGNAL":
            stats["auto_buy"] += 1
        else:
            stats["alert"] += 1

        nuovi_dal_salvataggio += 1

        await asyncio.sleep(0.5)

async def controllo_vinted():
    global nuovi_dal_salvataggio
    global cicli_dal_salvataggio

    if scanner_lock is None:
        return

    async with scanner_lock:
        page = await crea_sessione_vinted()
        now = time.time()

        secondarie_due = [
            query
            for query, due in query_next_due.items()
            if due <= now
        ]

        # Mantiene sempre le fisse + le secondarie che sono realmente dovute.
        # Se nessuna secondaria e' dovuta, ne prende una per non lasciare
        # completamente ferme le query meno frequenti.
        if not secondarie_due:
            secondarie_due = [
                min(
                    query_next_due,
                    key=query_next_due.get,
                )
            ]

        queries = QUERY_FISSE + secondarie_due

        log.info(
            "Nuovo ciclo: %s query",
            len(queries),
        )

        for query in queries:
            try:
                await scansione_query(
                    page,
                    query,
                )
            except Exception as exc:
                log.exception(
                    "Errore query '%s': %s",
                    query,
                    exc,
                )

            # Pacing normale: non e' un bypass del rate limiting.
            await asyncio.sleep(1.2)

            if query in query_next_due:
                # Ogni secondaria torna dovuta entro una finestra controllata.
                query_next_due[query] = (
                    time.time()
                    + max(
                        60,
                        cfg_runtime["scan_interval"]
                        * max(1, len(QUERY_SECONDARIE) // 2),
                    )
                )

        cicli_dal_salvataggio += 1

        if (
            nuovi_dal_salvataggio >= 10
            or cicli_dal_salvataggio >= 10
        ):
            salva_visti()
            nuovi_dal_salvataggio = 0
            cicli_dal_salvataggio = 0

        log.info(
            "Ciclo completato | notificati=%s | 403=%s",
            len(gia_visti),
            stats["http_403"],
        )

async def scanner_loop():
    while not bot.is_closed():
        start = time.monotonic()

        try:
            if canale_notifiche is not None:
                await controllo_vinted()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception(
                "Errore scanner principale: %s",
                exc,
            )

        elapsed = time.monotonic() - start

        await asyncio.sleep(
            max(
                0,
                cfg_runtime["scan_interval"] - elapsed,
            )
        )

# ================================================================
# REPORT
# ================================================================

async def report_loop():
    while not bot.is_closed():
        await asyncio.sleep(600)

        if canale_notifiche is None:
            continue

        try:
            report = (
                "DEBUG 10 min\n"
                f"Scaricati: {stats['scaricati']}\n"
                f"ALERT: {stats['alert']}\n"
                f"AUTO-BUY: {stats['auto_buy']}\n"
                f"Brand no: {stats['brand_no']}\n"
                f"Modello no: {stats['modello_no']}\n"
                f"Difetti: {stats['escluso_difetto']}\n"
                f"Stile: {stats['escluso_stile']}\n"
                f"Condizione no: {stats['condizione_no']}\n"
                f"Taglia no: {stats['taglia_no']}\n"
                f"Bambino: {stats['bambino']}\n"
                f"Seller rischio: {stats['seller_rischio']}\n"
                f"Profitto basso: {stats['profitto_basso']}\n"
                f"Freshness sconosciuto: {stats['freshness_sconosciuto']}\n"
                f"Freshness scaduta: {stats['freshness_no']}\n"
                f"Duplicati: {stats['duplicati']}\n"
                f"Rate limit: {stats['rate_limit']}\n"
                f"403: {stats['http_403']}\n"
                f"Errori HTTP: {stats['errori_http']}\n"
                f"Notifiche fallite: {stats['notifiche_fallite']}\n"
                f"Notificati totali: {len(gia_visti)}"
            )

            await canale_notifiche.send(
                f"```text\n{report}\n```"
            )

            stats.clear()
            stats.update(nuove_stats())

        except Exception as exc:
            log.warning(
                "Errore report: %s",
                exc,
            )

# ================================================================
# CANALE
# ================================================================

def trova_canale():
    if DISCORD_CHANNEL_ID:
        channel = bot.get_channel(
            DISCORD_CHANNEL_ID
        )

        if channel:
            return channel

    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                if channel.permissions_for(
                    guild.me
                ).send_messages:
                    return channel
            except Exception:
                continue

    return None

# ================================================================
# COMMANDS
# ================================================================

@bot.command()
async def ping(ctx):
    await ctx.send("Pong. Bot attivo.")

@bot.command(name="stats")
async def cmd_stats(ctx):
    s = stats

    await ctx.send(
        f"Scaricati: {s['scaricati']} | "
        f"ALERT: {s['alert']} | "
        f"AUTO-BUY: {s['auto_buy']}\n"
        f"Brand no: {s['brand_no']} | "
        f"Modello no: {s['modello_no']} | "
        f"Difetti: {s['escluso_difetto']}\n"
        f"Freshness sconosciuto: "
        f"{s['freshness_sconosciuto']} | "
        f"Freshness scaduta: {s['freshness_no']}\n"
        f"Rate limit: {s['rate_limit']} | "
        f"403: {s['http_403']}\n"
        f"Visti/notificati: {len(gia_visti)}"
    )

@bot.command()
async def config(ctx):
    await ctx.send(
        "Configurazione:\n"
        f"trattativa = {cfg_runtime['trattativa']}\n"
        f"freshness = {cfg_runtime['max_secondi_freschezza']} sec\n"
        f"scan interval = {cfg_runtime['scan_interval']} sec\n"
        f"freshness massima = 180 sec\n"
        f"ping = {PING_MODE}\n"
        f"403 cooldown = {VINTED_403_COOLDOWN} sec\n"
        f"seller costi = {SELLER_COST_RATE:.2%} + {SELLER_FIXED_COST:.2f} EUR\n"
        f"database = {STATE_DB_PATH}\n"
        f"blacklist ID = {len(blacklist_ids)}\n"
        f"modelli = {len(MODELLI)}"
    )

@bot.command(name="set")
async def cmd_set(
    ctx,
    chiave: str = "",
    valore: str = "",
):
    chiave = chiave.strip()

    if chiave not in cfg_runtime:
        await ctx.send(
            "Chiavi disponibili: "
            "trattativa, "
            "max_secondi_freschezza, "
            "scan_interval"
        )
        return

    if not valore:
        await ctx.send(
            "Uso: !set <chiave> <valore>"
        )
        return

    try:
        if chiave == "trattativa":
            nuovo_valore = float(valore)

            if not 0.50 <= nuovo_valore <= 1.00:
                raise ValueError
        else:
            nuovo_valore = int(valore)

            if nuovo_valore < 1:
                raise ValueError

            if chiave == "max_secondi_freschezza":
                nuovo_valore = min(nuovo_valore, 180)

        cfg_runtime[chiave] = nuovo_valore

        await ctx.send(
            f"OK: {chiave} = {nuovo_valore}"
        )

    except ValueError:
        await ctx.send(
            "Valore non valido."
        )

@bot.command()
async def modelli(ctx):
    righe = [
        f"- {m['nome']} | "
        f"SELL {m['sell_min']}-{m['sell_max']} EUR | "
        f"MIN +{m['profit_min']} EUR"
        for m in MODELLI
    ]

    blocco = (
        f"Modelli attivi ({len(MODELLI)}):\n"
    )

    for riga in righe:
        if len(blocco) + len(riga) + 1 > 1900:
            await ctx.send(blocco)
            blocco = ""

        blocco += riga + "\n"

    if blocco:
        await ctx.send(blocco)

@bot.command()
async def ultimo(ctx):
    if not ultimo_affare:
        await ctx.send(
            "Nessun affare segnalato."
        )
        return

    await ctx.send(
        "Ultimo affare:\n"
        f"{ultimo_affare['titolo']}\n"
        f"Prezzo: {ultimo_affare['prezzo']} EUR\n"
        f"ID: {ultimo_affare['id']}"
    )

@bot.command()
async def bad(ctx, iid: str = ""):
    """Blacklist globale e precisa per ID annuncio."""

    iid = iid.strip()

    if not iid.isdigit():
        await ctx.send("Uso: !bad <ID annuncio>")
        return

    if not add_blacklist(iid):
        await ctx.send("Errore nel salvataggio della blacklist.")
        return

    affare = affari_recenti.get(iid)
    if affare:
        testo = affare["titolo"][:80]
        await ctx.send(f"Blacklistato ID {iid}: {testo}")
    else:
        await ctx.send(f"Blacklistato ID {iid}.")

@bot.command(name="blacklist")
async def cmd_blacklist(ctx):
    ids = sorted(blacklist_ids)
    if not ids:
        await ctx.send("Blacklist vuota.")
        return
    text = "Blacklist ID (" + str(len(ids)) + "):\n" + "\n".join(ids)
    if len(text) <= 1900:
        await ctx.send(text)
    else:
        for i in range(0, len(ids), 150):
            await ctx.send("\n".join(ids[i:i+150]))

@bot.command()
async def unbad(ctx, iid: str = ""):
    """Rimuove un ID dalla blacklist globale."""

    iid = iid.strip()

    if not iid.isdigit():
        await ctx.send("Uso: !unbad <ID annuncio>")
        return

    if iid not in blacklist_ids:
        await ctx.send("ID non presente in blacklist.")
        return

    if not remove_blacklist(iid):
        await ctx.send("Errore nella rimozione della blacklist.")
        return
    await ctx.send(f"Rimosso dalla blacklist: {iid}")

@bot.command()
async def resetstats(ctx):
    stats.clear()
    stats.update(nuove_stats())

    await ctx.send(
        "Statistiche resettate."
    )

@bot.command()
async def helpbot(ctx):
    await ctx.send(
        "**Comandi Vinted Bot**\n"
        "`!ping` - stato bot\n"
        "`!stats` - statistiche\n"
        "`!config` - configurazione\n"
        "`!set <chiave> <valore>` - modifica config\n"
        "`!modelli` - modelli attivi\n"
        "`!ultimo` - ultimo affare\n"
        "`!bad <ID>` - blacklist globale per ID\n"
        "`!unbad <ID>` - rimuove ID dalla blacklist\n"
        "`!resetstats` - reset statistiche"
    )

# ================================================================
# ON MESSAGE
# ================================================================

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

# ================================================================
# READY
# ================================================================

@bot.event
async def on_ready():
    global canale_notifiche
    global scanner_task
    global report_task
    global scanner_lock

    log.info(
        "Bot online: %s",
        bot.user,
    )

    log.info(
        "Modelli configurati: %s",
        len(MODELLI),
    )

    canale_notifiche = trova_canale()

    if canale_notifiche:
        log.info(
            "Canale notifiche: #%s",
            getattr(
                canale_notifiche,
                "name",
                "n.d.",
            ),
        )
    else:
        log.warning(
            "Nessun canale notifiche trovato"
        )

    if scanner_lock is None:
        scanner_lock = asyncio.Lock()

    await crea_sessione_vinted()

    if (
        scanner_task is None
        or scanner_task.done()
    ):
        scanner_task = asyncio.create_task(
            scanner_loop()
        )

    if (
        report_task is None
        or report_task.done()
    ):
        report_task = asyncio.create_task(
            report_loop()
        )

@bot.event
async def on_close():
    await chiudi_sessione_vinted()

# ================================================================
# FLASK HEALTH
# ================================================================

app = Flask(__name__)

@app.route("/")
def home():
    return (
        "Vinted Resell Bot V5.3 Browser online",
        200,
    )

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "bot_ready": bot.is_ready(),
        "models": len(MODELLI),
        "notified_items": len(gia_visti),
        "scan_interval": cfg_runtime["scan_interval"],
        "freshness": cfg_runtime["max_secondi_freschezza"],
        "http_403": stats["http_403"],
        "vinted_403_cooldown": max(0, round(vinted_403_until - time.time())),
        "ping_mode": PING_MODE,
        "blacklist_ids": len(blacklist_ids),
    }), 200

def avvia_flask():
    try:
        port = int(
            os.getenv(
                "PORT",
                "10000",
            )
        )

        app.run(
            host="0.0.0.0",
            port=port,
        )

    except Exception as exc:
        log.error(
            "Flask terminato: %s",
            exc,
        )

# ================================================================
# MAIN
# ================================================================

def main():
    if not TOKEN:
        log.error(
            "Manca DISCORD_TOKEN."
        )
        raise SystemExit(1)

    carica_stato()

    threading.Thread(
        target=avvia_flask,
        daemon=True,
    ).start()

    log.info(
        "Avvio Vinted Resell Bot V5.3 Browser..."
    )

    bot.run(TOKEN)

if __name__ == "__main__":
    main()
