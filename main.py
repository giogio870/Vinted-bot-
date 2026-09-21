# BOT VINTED RESELL — FINAL APIFY MONITOR 2026
# Basato sulla logica del vecchio bot funzionante, con 12 modelli strategici precisi.
# WINTER STRATEGY: selected models, controlled buy ceilings, low fake/capital risk.
# NO luxury/high-counterfeit targets; no auto-purchase is performed by the bot.
# Scanner Discord + filtri + scoring + notifiche.
# NOTE: segnala opportunita', NON acquista automaticamente.
#
# ENV:
#   DISCORD_TOKEN
#   DISCORD_CHANNEL_ID (opzionale)
#   SCAN_INTERVAL (default 300, minimo 60)
#   FRESHNESS_SECONDS (default 180, minimo 30)
#   TRADE_FACTOR (default 0.95)
#   DISCORD_PING_MODE (none/here/everyone, default none)
#   APIFY_API_TOKEN (required on Render)
#   APIFY_ACTOR_ID (default scrape.badger/vinted-scraper)
#   APIFY_DOMAIN (default it)
#   APIFY_RESULTS_PER_RUN (default 20)
#   APIFY_QUERY_GROUPS_PER_SCAN (default 1)
#   APIFY_SCAN_INTERVAL (default 300 sec)
#   APIFY_MAX_PRICE (default 80; il codice alza automaticamente il tetto se serve)
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
import requests
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

# Apify = solo trasporto dati. Il bot continua a gestire filtri, scoring,
# blacklist e notifiche. Il token va SOLO nelle Environment Variables di Render.
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "").strip()
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "scrape.badger/vinted-scraper").strip()
APIFY_DOMAIN = os.getenv("APIFY_DOMAIN", "it").strip().lower() or "it"
APIFY_TIMEOUT_SECONDS = env_int("APIFY_TIMEOUT_SECONDS", 240, 30)
APIFY_SCAN_INTERVAL = env_int("APIFY_SCAN_INTERVAL", 300, 60)
APIFY_MAX_PRICE = env_int("APIFY_MAX_PRICE", 80, 1)

SCAN_INTERVAL = env_int("SCAN_INTERVAL", APIFY_SCAN_INTERVAL, 60)
FRESHNESS_SECONDS = min(env_int("FRESHNESS_SECONDS", 180, 30), 180)
FRESHNESS_REQUIRE_TIMESTAMP = os.getenv("FRESHNESS_REQUIRE_TIMESTAMP", "false").strip().lower() == "true"

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
    "new with tags": "nuovo con cartellino",
    "nuovo senza etichette": "nuovo senza cartellino",
    "new_without_tags": "nuovo senza cartellino",
    "new without tags": "nuovo senza cartellino",
    "nuovo": "nuovo",
    "new": "nuovo",
    "ottime": "ottime",
    "very_good": "ottime",
    "very good": "ottime",
    "molto buono": "molto buono",
    "buone": "buone",
    "good": "buone",
    "discrete": "discrete",
    "satisfactory": "discrete",
    "satisfactory condition": "discrete",
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
    "tnf_denali",
    "barbour_bedale",
    "barbour_beaufort",
    "woolrich_arctic",
    "patagonia_retrox",
    "patagonia_synchilla",
    "patagonia_better_sweater",
    "patagonia_torrentshell",
    "timberland_wheat",
    "ugg_ultramini",
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
    "the north face",
    "carhartt wip",
    "stussy",
    "nike",
    "ugg",
    "new balance",
]

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
    if rep > 1.0:
        rep = rep / 5.0

    return (
        (fb == 0 and items < 5)
        or
        (fb < 3 and rep < 0.8 and items < 10)
    )

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


# Strategia low-capital: 12 modelli precisi, margine realistico,
# rotazione abbastanza veloce e rischio contraffazione contenuto.
MODELLI = [
    M(
        "tnf_nuptse", "the north face", "1996/1990 Retro Nuptse",
        "the north face 1996 retro nuptse",
        ["1996 retro nuptse", "nuptse 1996", "1990 retro nuptse", "nuptse 1990", "retro nuptse", "nuptse 700", "700 nuptse"],
        {"ottime": {"auto_buy": 20, "buy_max": 30}, "buone": {"buy_max": 30}, "nuovo senza cartellino": {"buy_max": 40}, "nuovo con cartellino": {"buy_max": 40}},
        90, 120, 30, taglie_rifiuta=["XS"],
        escludi_se=["baltoro", "gilet", "vest", "smanicato", "chaleco", "sin mangas"],
    ),
    M(
        "carhartt_detroit", "carhartt wip", "Detroit Jacket",
        "carhartt wip detroit jacket",
        ["detroit jacket", "og detroit", "carhartt detroit", "detroit brown", "hamilton brown"],
        {"ottime": {"auto_buy": 30, "buy_max": 40}, "buone": {"auto_buy": 25, "buy_max": 35}, "nuovo senza cartellino": {"buy_max": 45}, "nuovo con cartellino": {"buy_max": 60}},
        70, 110, 30, taglie_rifiuta=["XS"],
        escludi_se=["michigan", "active jacket", "og active"],
    ),
    M(
        "tnf_denali", "the north face", "Denali Fleece",
        "the north face denali fleece",
        ["denali fleece", "denali jacket", "tnf denali", "north face denali"],
        {"ottime": {"auto_buy": 15, "buy_max": 25}, "buone": {"buy_max": 20}, "nuovo senza cartellino": {"buy_max": 30}, "nuovo con cartellino": {"buy_max": 40}},
        45, 70, 20, taglie_rifiuta=["XS", "XXS"],
        escludi_se=["gilet", "vest", "smanicato"],
    ),
    M(
        "patagonia_synchilla", "patagonia", "Synchilla",
        "patagonia synchilla",
        ["synchilla", "synchilla fleece", "synchilla snap-t", "synchilla snap t"],
        {"ottime": {"auto_buy": 18, "buy_max": 25}, "buone": {"buy_max": 22}, "nuovo senza cartellino": {"buy_max": 32}, "nuovo con cartellino": {"buy_max": 35}},
        45, 65, 20,
        escludi_se=["gilet", "vest", "smanicato", "kids", "bambino"],
    ),
    M(
        "patagonia_retrox", "patagonia", "Retro-X",
        "patagonia retro x",
        ["retro-x", "retro x", "classic retro-x", "classic retro x"],
        {"ottime": {"auto_buy": 25, "buy_max": 35}, "buone": {"buy_max": 30}, "nuovo senza cartellino": {"buy_max": 45}, "nuovo con cartellino": {"buy_max": 50}},
        65, 100, 30,
        escludi_se=["gilet", "vest", "smanicato", "kids", "bambino"],
    ),
    M(
        "patagonia_better_sweater", "patagonia", "Better Sweater",
        "patagonia better sweater",
        ["better sweater", "better sweater fleece", "patagonia better sweater"],
        {"ottime": {"auto_buy": 15, "buy_max": 22}, "buone": {"buy_max": 20}, "nuovo senza cartellino": {"buy_max": 28}, "nuovo con cartellino": {"buy_max": 32}},
        38, 60, 18,
        escludi_se=["gilet", "vest", "smanicato", "kids", "bambino"],
    ),
    M(
        "patagonia_torrentshell", "patagonia", "Torrentshell",
        "patagonia torrentshell",
        ["torrentshell", "torrentshell 3l", "torrentshell 3-l"],
        {"ottime": {"auto_buy": 30, "buy_max": 40}, "buone": {"buy_max": 35}, "nuovo senza cartellino": {"buy_max": 50}, "nuovo con cartellino": {"buy_max": 60}},
        80, 120, 30,
        escludi_se=["pantalone", "pants", "gilet", "vest", "smanicato", "kids", "bambino"],
    ),
    M(
        "barbour_bedale", "barbour", "Bedale",
        "barbour bedale",
        ["barbour bedale", "bedale"],
        {"ottime": {"auto_buy": 25, "buy_max": 40}, "buone": {"auto_buy": 20, "buy_max": 35}, "nuovo senza cartellino": {"buy_max": 55}, "nuovo con cartellino": {"buy_max": 70}},
        80, 120, 30, taglie_rifiuta=["XS"],
        escludi_se=["beaufort", "border", "international", "bambino", "kids", "gilet", "vest", "smanicato"],
    ),
    M(
        "barbour_beaufort", "barbour", "Beaufort",
        "barbour beaufort",
        ["barbour beaufort", "beaufort"],
        {"ottime": {"auto_buy": 25, "buy_max": 40}, "buone": {"auto_buy": 20, "buy_max": 35}, "nuovo senza cartellino": {"buy_max": 55}, "nuovo con cartellino": {"buy_max": 70}},
        80, 120, 30, taglie_rifiuta=["XS"],
        escludi_se=["bedale", "border", "international", "bambino", "kids", "gilet", "vest", "smanicato"],
    ),
    M(
        "woolrich_arctic", "woolrich", "Arctic Parka",
        "woolrich arctic parka",
        ["arctic parka", "woolrich arctic"],
        {"ottime": {"auto_buy": 25, "buy_max": 35}, "buone": {"buy_max": 30}, "nuovo senza cartellino": {"buy_max": 45}, "nuovo con cartellino": {"buy_max": 60}},
        70, 105, 25, taglie_rifiuta=["XS"],
        escludi_se=["arctic jacket", "bambino", "kids", "gilet", "vest", "smanicato"],
    ),
    M(
        "timberland_wheat", "timberland", "Premium 6-Inch Wheat",
        "timberland premium 6 inch wheat",
        ["premium 6-inch wheat", "premium 6 inch wheat", "6-inch premium", "6 inch premium", "wheat boot", "wheat premium"],
        {"ottime": {"auto_buy": 20, "buy_max": 30}, "buone": {"auto_buy": 15, "buy_max": 25}, "nuovo": {"buy_max": 40}, "nuovo con cartellino": {"buy_max": 45}, "nuovo senza cartellino": {"buy_max": 40}},
        55, 80, 25, taglie_alert_extra=["36", "37", "38"], discrete_eccezione={"buy_max": 18},
    ),
    M(
        "ugg_ultramini", "ugg", "Ultra Mini",
        "ugg ultra mini",
        ["ultra mini", "ugg ultra-mini", "ugg classic ultra mini"],
        {"ottime": {"auto_buy": 20, "buy_max": 30}, "buone": {"buy_max": 25}, "nuovo senza cartellino": {"buy_max": 40}, "nuovo con cartellino": {"buy_max": 45}},
        55, 80, 25,
        escludi_se=["kids", "bambino", "bimba", "bimbo"],
    ),
]

# Fuori strategia: modelli meno convincenti per il budget e il profilo di rischio scelto.
MODELLI_RIMOSSI = {
    "patagonia_down_sweater",
    "patagonia_nano_puff",
}


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

    # 5) Freshness
    # Questo Actor ordina i risultati con newest_first ma il suo output
    # tabellare verificato non espone un timestamp Vinted dell'annuncio.
    # Se un timestamp esiste, lo usiamo rigorosamente. Altrimenti, in modalita
    # relativa, il filtro temporale viene sostituito dal dedup tra sweep.
    freshness = freshness_item(item)

    if freshness is not None:
        if freshness > cfg_runtime["max_secondi_freschezza"]:
            stats["freshness_no"] += 1
            return None
    elif FRESHNESS_REQUIRE_TIMESTAMP:
        stats["freshness_sconosciuto"] += 1
        return None
    else:
        # Questo Actor non espone un timestamp Vinted affidabile nel dataset
        # osservato. Non inventiamo un'eta': usiamo newest_first + dedup per ID.
        freshness = 0.0

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
            str(item.get("url", "") or "").strip()
            or "https://www.vinted.it/items/" + str(item.get("id", ""))
        ),
        "foto": (
            (item.get("photo") or {}).get("url", "")
            or ""
        ),
        "seller_rischio": seller_rischio,
        "freshness": freshness,
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

def salva_visto(iid, ts=None):
    """Persistenza immediata di un singolo annuncio notificato con successo."""
    try:
        iid = str(iid).strip()
        if not iid:
            return False
        ts = float(ts if ts is not None else time.time())
        with sqlite3.connect(STATE_DB_PATH, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout = 10000")
            conn.execute(
                "INSERT INTO seen(item_id, notified_at) VALUES(?, ?) "
                "ON CONFLICT(item_id) DO UPDATE SET notified_at=excluded.notified_at",
                (iid, ts),
            )
            conn.commit()
        return True
    except Exception as exc:
        log.warning("Errore salvataggio singolo visto SQLite: %s", exc)
        return False

def salva_visti():
    """Fallback batch per allineare la RAM al database."""
    try:
        with sqlite3.connect(STATE_DB_PATH, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout = 10000")
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

# ================================================================
# APIFY / VINTED COLLECTOR
# ================================================================

apify_403_until = 0.0

# Actor verificato: scrape.badger/vinted-scraper
# Endpoint ufficiale: run-sync-get-dataset-items
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "scrape.badger/vinted-scraper").strip()
APIFY_API_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"

# Questo Actor usa Search Items con UNA query per run.
# Per contenere i costi, il bot raggruppa i modelli per brand e ruota i gruppi.
APIFY_RESULTS_PER_RUN = env_int("APIFY_RESULTS_PER_RUN", 20, 1)
APIFY_QUERY_GROUPS_PER_SCAN = env_int("APIFY_QUERY_GROUPS_PER_SCAN", 1, 1)


def _parse_iso_timestamp(raw):
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            ts = float(raw)
            if ts > 1e11:
                ts /= 1000.0
            return ts if ts > 0 else None
        value = str(raw).strip()
        if not value:
            return None
        try:
            ts = float(value)
            if ts > 1e11:
                ts /= 1000.0
            return ts if ts > 0 else None
        except ValueError:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def slug_vinted(testo):
    testo = normalizza(testo)
    testo = re.sub(r"[^a-z0-9]+", "-", testo).strip("-")
    return testo[:110]


def normalizza_item_apify(row):
    """Adatta l'output reale di scrape.badger al formato interno."""
    if not isinstance(row, dict):
        return None

    # Campi osservati nell'output dell'Actor:
    # brand_title, display_title, id, market, photo_url,
    # price_amount, price_currency, seller_id, seller_login, size, status...
    iid = row.get("id") or row.get("item_id") or row.get("itemId")
    title = row.get("display_title") or row.get("title") or ""
    url = row.get("url") or row.get("item_url") or row.get("itemUrl") or ""
    brand = row.get("brand_title") or row.get("brand") or row.get("brandTitle") or ""
    size = row.get("size") or row.get("size_title") or row.get("sizeTitle") or ""
    condition = row.get("status") or row.get("condition") or ""
    description = row.get("description") or ""

    price = row.get("price_amount")
    if price is None:
        price = row.get("priceAmount")
    if price is None:
        price = row.get("price")
    if isinstance(price, dict):
        price = price.get("amount")

    photo_url = (
        row.get("photo_url")
        or row.get("photoUrl")
        or row.get("image_url")
        or row.get("imageUrl")
        or ""
    )

    # Seller fields disponibili nel risultato tabellare dell'Actor.
    seller = {
        "feedback_count": row.get("seller_feedback_count") or row.get("sellerFeedbackCount"),
        "feedback_reputation": row.get("seller_feedback_reputation") or row.get("sellerRating"),
        "item_count": row.get("seller_item_count") or row.get("sellerItemCount"),
    }

    # Alcune versioni/risultati possono avere un timestamp; se non c'e',
    # non lo inventiamo.
    created = (
        row.get("created_at")
        or row.get("createdAt")
        or row.get("listed_at")
        or row.get("listedAt")
        or row.get("created_at_ts")
    )

    normalized = {
        "id": str(iid or "").strip(),
        "title": str(title or ""),
        "description": str(description or ""),
        "brand_title": str(brand or ""),
        "size_title": str(size or ""),
        "status": str(condition or ""),
        "price": {"amount": price},
        "photo": {"url": str(photo_url or "")},
        "user": seller,
        "seller_login": str(row.get("seller_login") or ""),
        "seller_id": str(row.get("seller_id") or ""),
        "url": str(url or ""),
        "created_at": created,
        "created_at_ts": _parse_iso_timestamp(created),
        "market": str(row.get("market") or APIFY_DOMAIN),
        "currency": str(row.get("price_currency") or "EUR"),
        "service_fee": row.get("service_fee"),
    }

    if not normalized["url"] and normalized["id"]:
        slug = slug_vinted(normalized["title"])
        normalized["url"] = (
            f"https://www.vinted.{APIFY_DOMAIN}/items/"
            f"{normalized['id']}-{slug}"
            if slug else
            f"https://www.vinted.{APIFY_DOMAIN}/items/{normalized['id']}"
        )

    return normalized


async def chiudi_sessione_vinted():
    return None


async def crea_sessione_vinted():
    if not APIFY_API_TOKEN:
        log.error("Manca APIFY_API_TOKEN nelle Environment Variables di Render.")
        return False
    log.info(
        "Collector Apify pronto | actor=%s | market=%s | results/run=%s",
        APIFY_ACTOR_ID,
        APIFY_DOMAIN,
        APIFY_RESULTS_PER_RUN,
    )
    return True


# Query mirate: ogni run cerca un modello preciso.
# Il cursore ruota i 12 modelli senza dover creare 12 Actor separati.
# Il filtro/scoring finale resta sempre nel bot.
QUERY_GROUPS = [
    ["the north face nuptse"],
    ["carhartt wip detroit jacket"],
    ["the north face denali"],
    ["patagonia synchilla"],
    ["patagonia retro x"],
    ["patagonia better sweater"],
    ["patagonia torrentshell"],
    ["barbour bedale"],
    ["barbour beaufort"],
    ["woolrich arctic parka"],
    ["timberland premium 6 inch wheat"],
    ["ugg ultra mini"],
]

query_group_cursor = 0


def gruppi_da_scansionare():
    global query_group_cursor
    if not QUERY_GROUPS:
        return []

    scelti = []
    for _ in range(min(APIFY_QUERY_GROUPS_PER_SCAN, len(QUERY_GROUPS))):
        scelti.append(QUERY_GROUPS[query_group_cursor % len(QUERY_GROUPS)])
        query_group_cursor = (query_group_cursor + 1) % len(QUERY_GROUPS)
    return scelti


async def apify_search(query, max_results=None):
    """Una ricerca Search Items compatibile con l'Actor reale."""
    global apify_403_until

    if not APIFY_API_TOKEN:
        stats["errori_http"] += 1
        return None

    if time.time() < apify_403_until:
        return None

    max_results = max_results or APIFY_RESULTS_PER_RUN

    # Prezzo massimo realmente necessario: il filtro definitivo resta nel bot.
    buy_ceiling = max(
        safe_float(block.get("buy_max"))
        for modello in MODELLI
        for block in modello.get("condizioni", {}).values()
        if block.get("buy_max") is not None
    )
    collector_max_price = max(APIFY_MAX_PRICE, buy_ceiling + 10)

    payload = {
        "mode": "Search Items",
        "query": query,
        "market": APIFY_DOMAIN,
        "price_to": str(collector_max_price),
        "order": "newest_first",
        "max_results": max_results,
    }

    url = APIFY_API_URL.format(
        actor=urllib.parse.quote(APIFY_ACTOR_ID.replace("/", "~"), safe="~")
    )

    headers = {
        "Authorization": f"Bearer {APIFY_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "VintedResellBot/2026",
    }

    try:
        response = await asyncio.to_thread(
            requests.post,
            url,
            params={"token": APIFY_API_TOKEN},
            json=payload,
            headers=headers,
            timeout=APIFY_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        stats["errori_http"] += 1
        log.warning("Errore collegamento Apify: %s", exc)
        return None

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            stats["errori_http"] += 1
            log.warning("Apify ha restituito una risposta non JSON.")
            return None

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Alcune risposte wrapper possono contenere items.
            return data.get("items", [])
        return []

    if response.status_code in (401, 403):
        stats["http_403"] += 1
        apify_403_until = time.time() + 300
        log.error("Apify HTTP %s: token/permessi da controllare. Pausa 300s.", response.status_code)
        return None

    if response.status_code == 402:
        stats["errori_http"] += 1
        log.error("Apify HTTP 402: credito/limite insufficiente.")
        return None

    if response.status_code == 429:
        stats["rate_limit"] += 1
        log.warning("Apify HTTP 429: rate limit.")
        return None

    stats["errori_http"] += 1
    log.warning(
        "Apify HTTP %s: %s",
        response.status_code,
        response.text[:300].replace("\n", " "),
    )
    return None


async def apify_catalog(query_groups):
    """Esegue le ricerche necessarie e unisce i risultati senza duplicati."""
    merged = []
    seen = set()

    for group in query_groups:
        for query in group:
            data = await apify_search(query)
            if data is None:
                continue
            for row in data:
                iid = str((row or {}).get("id") or (row or {}).get("item_id") or "").strip()
                key = iid or str(row)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(row)

    return merged

# ================================================================
# QUERY / SCHEDULER
# ================================================================

# Manteniamo i modelli e le query nel codice: l'Actor non va configurato
# manualmente 12 volte. L'Actor riceve una query per run.
QUERY_FISSE = [q[0] for q in QUERY_GROUPS]

QUERY_APIFY = QUERY_FISSE

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
        "e autenticita' prima di comprare.\n\n"
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

async def scansione_items(items):
    global ultimo_affare
    global nuovi_dal_salvataggio

    ciclo_processati = set()

    for raw_item in items:
        item = normalizza_item_apify(raw_item)
        if not item:
            continue

        iid = str(item.get("id", ""))
        if not iid or iid in ciclo_processati:
            continue
        ciclo_processati.add(iid)

        if iid in gia_visti:
            stats["duplicati"] += 1
            continue

        stats["scaricati"] += 1

        if is_blacklisted(iid):
            continue

        risultato = valuta_item(item)
        if not risultato:
            continue

        notificato = False
        for tentativo in range(3):
            notificato = await invia_notifica(risultato)
            if notificato:
                break
            if tentativo < 2:
                await asyncio.sleep(1.0)

        if not notificato:
            # Non salviamo localmente l'annuncio come notificato.
            # In monitor mode Apify puo' comunque averlo marcato remoto;
            # per questo ritentiamo subito nello stesso sweep invece di
            # considerare l'errore definitivamente recuperato.
            continue

        notified_ts = time.time()
        gia_visti[iid] = notified_ts
        while len(gia_visti) > 10000:
            gia_visti.popitem(last=False)

        # Persistenza immediata: se Render riavvia subito dopo l'alert,
        # l'annuncio non viene perso dal database locale.
        await asyncio.to_thread(salva_visto, iid, notified_ts)

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
        await asyncio.sleep(0.3)


async def controllo_vinted():
    global nuovi_dal_salvataggio
    global cicli_dal_salvataggio

    if scanner_lock is None:
        return

    async with scanner_lock:
        if not await crea_sessione_vinted():
            return

        gruppi = gruppi_da_scansionare()
        log.info(
            "Nuovo sweep Apify | gruppi=%s | results/run=%s | query=%s",
            len(gruppi),
            APIFY_RESULTS_PER_RUN,
            [q for g in gruppi for q in g],
        )

        data = await apify_catalog(gruppi)
        if not data:
            return

        await scansione_items(data)

        cicli_dal_salvataggio += 1
        if nuovi_dal_salvataggio >= 10 or cicli_dal_salvataggio >= 3:
            await asyncio.to_thread(salva_visti)
            nuovi_dal_salvataggio = 0
            cicli_dal_salvataggio = 0

        log.info(
            "Sweep completato | record=%s | notificati=%s | errori=%s",
            len(data),
            len(gia_visti),
            stats["errori_http"],
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
                f"Apify 403: {stats['http_403']}\n"
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
        f"Apify actor = {APIFY_ACTOR_ID}\n"
        f"Apify results/run = {APIFY_RESULTS_PER_RUN}\n"
        f"Apify groups/scan = {APIFY_QUERY_GROUPS_PER_SCAN}\n"
        f"Timestamp obbligatorio = {FRESHNESS_REQUIRE_TIMESTAMP}\n"
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
        "Vinted Resell Bot FINAL APIFY online",
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
        "apify_403_cooldown": max(0, round(apify_403_until - time.time())),
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
        "Avvio Vinted Resell Bot FINAL APIFY MONITOR 2026..."
    )

    try:
        bot.run(TOKEN)
    finally:
        # Ultimo flush anche in caso di shutdown normale/errore.
        salva_visti()

if __name__ == "__main__":
    main()
