# BOT VINTED RESELL V5.1
# Scanner Discord + filtri + scoring + notifiche.
# NOTE: segnala opportunita', NON acquista automaticamente.
#
# ENV:
#   DISCORD_TOKEN
#   DISCORD_CHANNEL_ID (opzionale)
#   SCAN_INTERVAL (default 10, minimo 8)
#   FRESHNESS_SECONDS (default 180, minimo 30)
#   TRADE_FACTOR (default 0.95)
#
# IMPORTANTE:
# - freshness usa SOLO il timestamp dell'annuncio, mai quello della foto.
# - timestamp mancante/non valido = scarto.
# - niente cuori nello scoring.
# - 403 Vinted = nessun retry aggressivo.
# - gli annunci diventano "visti" solo dopo una notifica Discord riuscita.

import asyncio
import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.parse
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify
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
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default

SCAN_INTERVAL = env_int("SCAN_INTERVAL", 10, 8)
FRESHNESS_SECONDS = env_int("FRESHNESS_SECONDS", 180, 30)

try:
    TRADE_FACTOR = float(os.getenv("TRADE_FACTOR", "0.95"))
except ValueError:
    TRADE_FACTOR = 0.95

TRADE_FACTOR = min(max(TRADE_FACTOR, 0.50), 1.00)

cfg_runtime = {
    "trattativa": TRADE_FACTOR,
    "max_secondi_freschezza": FRESHNESS_SECONDS,
    "scan_interval": SCAN_INTERVAL,
}

BASE_DIR = Path(__file__).resolve().parent
VISTI_FILE = BASE_DIR / "gia_visti.json"
PREF_FILE = BASE_DIR / "preferenze_utenti.json"

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
    r"\b(?:senza|nessun|nessuna|nessuno|non|mai|zero|niente)\b"
    r"(?:\s+\w+){0,3}\s*$",
    re.I,
)

def ha_difetto(testo):
    tl = normalizza(testo)

    for difetto in DIFETTI_ASSOLUTI:
        if match_parola_intera(difetto, tl):
            return True, difetto

    for difetto in DIFETTI_GENERICI:
        rx = _RX_CACHE.get("DEF:" + difetto)
        if rx is None:
            rx = re.compile(
                r"(?<!\w)"
                + re.escape(normalizza(difetto)).replace(r"\ ", r"\s+")
                + r"(?!\w)",
                re.I,
            )
            _RX_CACHE["DEF:" + difetto] = rx

        for m in rx.finditer(tl):
            prima = tl[max(0, m.start() - 45):m.start()]
            if NEGAZIONE_RE.search(prima):
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
    "nuovo senza etichette": "nuovo senza cartellino",
    "nuovo": "nuovo",
    "ottime": "ottime",
    "molto buono": "molto buono",
    "buone": "buone",
    "discrete": "discrete",
    "sufficiente": "sufficiente",
}

CONDIZIONI_KEYWORDS = {
    "nuovo con cartellino": ["nuovo con cartellino", "new with tags", "nwt"],
    "nuovo senza cartellino": ["nuovo senza cartellino", "new without tags", "nwot"],
    "nuovo": ["nuovo", "new"],
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
            "wheat", "yellow", "giallo", "gialla", "grano", "premium"
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

def si_manca_certilogo(descrizione):
    d = normalizza(descrizione)

    marker = (
        r"(?:art\.?|articolo|article|codice|cod|"
        r"style|product|certilogo|clg)"
    )

    vicino_marker_numero = re.search(
        r"\b" + marker + r"\b[\s:#\-]{0,20}\d{6}\b",
        d,
        re.I,
    )

    vicino_numero_marker = re.search(
        r"\b\d{6}\b[\s:#\-]{0,20}\b" + marker + r"\b",
        d,
        re.I,
    )

    return not (vicino_marker_numero or vicino_numero_marker)

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
    data = {
        "id": model_id,
        "brand": brand,
        "nome": nome,
        "query": query,
        "keywords": keywords,
        "condizioni": condizioni,
        "sell_min": sell_min,
        "sell_max": sell_max,
        "profit_min": profit_min,
    }
    data.update(extra)
    return data

MODELLI = [
    # NUOVO: Nuptse giubbotto -> acquisto massimo 40 EUR.
    M(
        "tnf_nuptse", "the north face", "1996/1990 Retro Nuptse",
        "the north face nuptse",
        ["1996 retro nuptse", "nuptse 1996", "1996 nuptse",
         "1990 retro nuptse", "nuptse 1990", "retro nuptse",
         "nuptse 700", "700 nuptse", "nupste", "nuptze"],
        {
            "ottime": {"auto_buy": 30, "buy_max": 40},
            "buone": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 60},
            "nuovo con cartellino": {"buy_max": 85},
        },
        105, 135, 30,
        taglie_rifiuta=["XS"],
        escludi_se=["baltoro", "gilet", "vest", "smanicato", "chaleco", "sin mangas"],
    ),

    M(
        "carhartt_detroit", "carhartt wip", "Detroit/Michigan/Active Jacket",
        "carhartt detroit jacket",
        ["og detroit", "detroit jacket", "michigan coat", "active jacket",
         "carhartt wip detroit", "carhartt detroit", "hamilton brown", "detroit brown"],
        {
            "ottime": {"auto_buy": 40, "buy_max": 65},
            "buone": {"auto_buy": 28, "buy_max": 45},
            "nuovo senza cartellino": {"buy_max": 85},
            "nuovo con cartellino": {"buy_max": 110},
        },
        115, 145, 35,
        taglie_rifiuta=["XS"],
    ),

    M(
        "arcteryx_atom_lt", "arc'teryx", "Atom LT", "arcteryx atom lt",
        ["atom lt"],
        {
            "ottime": {"auto_buy": 55, "buy_max": 75},
            "nuovo senza cartellino": {"buy_max": 105},
            "nuovo con cartellino": {"buy_max": 125},
        },
        130, 155, 45,
    ),

    M(
        "arcteryx_beta_lt", "arc'teryx", "Beta LT", "arcteryx beta lt",
        ["beta lt"],
        {
            "ottime": {"auto_buy": 50, "buy_max": 65},
            "nuovo senza cartellino": {"buy_max": 90},
            "nuovo con cartellino": {"buy_max": 115},
        },
        115, 160, 38,
    ),

    M(
        "arcteryx_beta_ar", "arc'teryx", "Beta AR", "arcteryx beta ar",
        ["beta ar"],
        {
            "ottime": {"auto_buy": 85, "buy_max": 120},
            "nuovo senza cartellino": {"buy_max": 155},
            "nuovo con cartellino": {"buy_max": 180},
        },
        190, 250, 50,
    ),

    M(
        "arcteryx_cerium_lt", "arc'teryx", "Cerium LT", "arcteryx cerium",
        ["cerium lt", "arcteryx cerium"],
        {
            "ottime": {"auto_buy": 60, "buy_max": 85},
            "nuovo senza cartellino": {"buy_max": 115},
            "nuovo con cartellino": {"buy_max": 140},
        },
        160, 200, 45,
    ),

    M(
        "patagonia_retrox", "patagonia", "Retro-X", "patagonia retro x",
        ["retro-x", "retro x", "classic retro-x"],
        {
            "ottime": {"auto_buy": 30, "buy_max": 50},
            "nuovo con cartellino": {"buy_max": 70},
            "nuovo senza cartellino": {"buy_max": 70},
        },
        90, 120, 30,
    ),

    M(
        "patagonia_retropile", "patagonia", "Retro Pile", "patagonia retro pile",
        ["retro pile"],
        {
            "ottime": {"auto_buy": 25, "buy_max": 40},
            "nuovo con cartellino": {"buy_max": 55},
            "nuovo senza cartellino": {"buy_max": 55},
        },
        75, 105, 25,
    ),

    M(
        "patagonia_synchilla", "patagonia", "Synchilla", "patagonia synchilla",
        ["synchilla"],
        {
            "ottime": {"auto_buy": 15, "buy_max": 25},
            "nuovo con cartellino": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        45, 70, 25,
    ),

    M(
        "patagonia_bettersweater", "patagonia", "Better Sweater",
        "patagonia better sweater",
        ["better sweater"],
        {
            "ottime": {"auto_buy": 15, "buy_max": 25},
            "nuovo con cartellino": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        48, 65, 25,
    ),

    M(
        "nike_techfleece_felpa", "nike", "Tech Fleece Felpa",
        "nike tech fleece hoodie",
        ["tech fleece hoodie", "tech fleece felpa", "tech fleece crew"],
        {
            "ottime": {"auto_buy": 12, "buy_max": 15},
            "buone": {"buy_max": 10},
            "nuovo con cartellino": {"buy_max": 25},
            "nuovo senza cartellino": {"buy_max": 25},
        },
        30, 45, 25,
        taglie_rifiuta=["XS"], taglia_s_solo_sotto=20,
        escludi_se=["nocta"],
    ),

    M(
        "nike_techfleece_tuta", "nike", "Tech Fleece Tuta completa",
        "nike tech fleece tuta",
        ["tech fleece tuta", "tech fleece tracksuit", "tech fleece set"],
        {
            "ottime": {"auto_buy": 22, "buy_max": 25},
            "nuovo con cartellino": {"buy_max": 42},
            "nuovo senza cartellino": {"buy_max": 42},
        },
        50, 75, 25,
        taglie_rifiuta=["XS"], escludi_se=["nocta"],
    ),

    M(
        "nike_techfleece_pant", "nike", "Tech Fleece Pantalone",
        "nike tech fleece jogger",
        ["tech fleece jogger", "tech fleece pant", "tech fleece pantalone"],
        {
            "ottime": {"auto_buy": 17, "buy_max": 20},
            "nuovo con cartellino": {"buy_max": 32},
            "nuovo senza cartellino": {"buy_max": 32},
        },
        40, 58, 25,
        taglie_rifiuta=["XS"], taglia_s_solo_sotto=20,
        escludi_se=["nocta"],
    ),

    M(
        "nike_nocta_hoodie", "nike", "Nocta Hoodie", "nike nocta hoodie",
        ["nocta hoodie", "nike x nocta hoodie", "nocta tech hoodie"],
        {
            "ottime": {"auto_buy": 30, "buy_max": 35},
            "nuovo con cartellino": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        55, 80, 25,
    ),

    M(
        "nike_nocta_pant", "nike", "Nocta Joggers", "nike nocta joggers",
        ["nocta joggers", "nocta pant", "nike x nocta pant"],
        {
            "ottime": {"auto_buy": 22, "buy_max": 25},
            "nuovo con cartellino": {"buy_max": 32},
            "nuovo senza cartellino": {"buy_max": 32},
        },
        42, 60, 25,
    ),

    M(
        "nike_nocta_tuta", "nike", "Nocta Tracksuit completa",
        "nike nocta tracksuit",
        ["nocta tracksuit", "nike x nocta tracksuit", "nocta tuta"],
        {
            "ottime": {"auto_buy": 55, "buy_max": 60},
            "nuovo con cartellino": {"buy_max": 75},
            "nuovo senza cartellino": {"buy_max": 75},
        },
        95, 130, 30,
    ),

    M(
        "timberland_wheat", "timberland", "Premium 6-Inch Wheat",
        "timberland premium 6 inch wheat",
        ["premium 6-inch wheat", "premium 6 inch wheat", "6-inch premium",
         "6 inch premium", "wheat boot", "wheat premium", "yellow premium",
         "gialla premium", "gialle premium"],
        {
            "ottime": {"auto_buy": 40, "buy_max": 45},
            "buone": {"auto_buy": 25, "buy_max": 28},
            "nuovo": {"buy_max": 65},
        },
        95, 125, 30,
        taglie_alert_extra=["36", "37", "38"],
        discrete_eccezione={"buy_max": 18},
    ),

    M(
        "rl_polobear", "ralph lauren", "Polo Bear",
        "ralph lauren polo bear",
        ["polo bear", "bear sweater", "bear knit", "polo bear knit",
         "polo bear sweatshirt", "polo bear hoodie"],
        {
            "ottime": {"auto_buy": 18, "buy_max": 25},
            "nuovo con cartellino": {"buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 40},
        },
        65, 90, 30,
        taglia_s_solo_sotto=20,
        escludi_se=["patch", "thermocollant", "iron-on", "iron on",
                    "toppa", "ecusson", "aufnaher", "sticker", "pin",
                    "spilla", "badge"],
    ),

    M(
        "rl_polobear_zaino", "ralph lauren", "Polo Bear Zaino/Borsa",
        "polo bear zaino",
        ["polo bear zaino", "polo bear rucksack", "polo bear backpack",
         "polo bear borsa", "bear zaino", "bear backpack", "bear borsa"],
        {"ottime": {"auto_buy": 20, "buy_max": 30}},
        80, 110, 35,
        escludi_se=["patch", "thermocollant", "iron-on", "iron on",
                    "toppa", "ecusson", "aufnaher", "sticker", "pin", "spilla"],
    ),

    M(
        "si_crewneck", "stone island", "Sweatshirt/Crewneck",
        "stone island sweatshirt",
        ["crewneck", "sweatshirt", "felpa girocollo"],
        {
            "ottime": {"auto_buy": 35, "buy_max": 55},
            "nuovo": {"buy_max": 75},
        },
        105, 135, 45,
        escludi_se=["hoodie", "zip", "overshirt", "jacket", "giacca", "giubbotto"],
    ),

    M(
        "si_ziphoodie", "stone island", "Zip Hoodie",
        "stone island zip hoodie",
        ["zip hoodie", "felpa cappuccio zip"],
        {
            "ottime": {"auto_buy": 35, "buy_max": 50},
            "nuovo": {"buy_max": 75},
        },
        115, 150, 45,
        escludi_se=["overshirt", "jacket", "giacca", "giubbotto"],
    ),

    M(
        "si_hoodie", "stone island", "Hoodie",
        "stone island hoodie",
        ["hoodie", "felpa cappuccio"],
        {
            "ottime": {"auto_buy": 30, "buy_max": 50},
            "nuovo": {"buy_max": 75},
        },
        105, 135, 45,
        escludi_se=["zip", "overshirt", "jacket", "giacca", "giubbotto"],
    ),

    M(
        "si_overshirt", "stone island", "Overshirt",
        "stone island overshirt",
        ["overshirt"],
        {
            "ottime": {"auto_buy": 50, "buy_max": 75},
            "nuovo": {"buy_max": 110},
        },
        145, 185, 45,
        escludi_se=["jacket", "giacca", "giubbotto"],
    ),

    M(
        "si_jacket", "stone island", "Jacket",
        "stone island jacket",
        ["jacket", "giacca", "giubbotto"],
        {
            "ottime": {"auto_buy": 55, "buy_max": 75},
            "nuovo": {"buy_max": 115},
        },
        135, 175, 45,
    ),

    M(
        "ugg_ultramini", "ugg", "Ultra Mini", "ugg ultra mini",
        ["ultra mini"],
        {
            "ottime": {"auto_buy": 45, "buy_max": 60},
            "nuovo senza cartellino": {"buy_max": 85},
            "nuovo con cartellino": {"buy_max": 95},
        },
        100, 130, 30,
        escludi_se=["kids", "bambino", "bimba", "bimbo"],
    ),

    M(
        "nb_9060", "new balance", "9060", "new balance 9060",
        ["9060"],
        {
            "ottime": {"auto_buy": 30, "buy_max": 40},
            "nuovo senza cartellino": {"buy_max": 60},
            "nuovo con cartellino": {"buy_max": 70},
        },
        75, 110, 25,
        escludi_se=["kids", "bambino"],
    ),

    M(
        "stussy_8ball", "stussy", "8 Ball / World Tour", "stussy 8 ball",
        ["8 ball", "world tour"],
        {"ottime": {"auto_buy": 15, "buy_max": 25}},
        50, 85, 25,
        richiedi_secondo=[
            "t-shirt", "tee", "longsleeve", "hoodie", "felpa",
            "sweat", "sweatshirt", "crewneck",
        ],
        escludi_se=[
            "porte cles", "portachiavi", "keychain", "keyring",
            "charm", "portachiave", "figure", "palla", "8 ball key",
            "pendentif",
        ],
        richiedi_taglia=True,
        taglia_s_solo_sotto=20,
    ),
]

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

    for keyword in modello.get("keywords", []):
        if not match_parola_intera(keyword, tl):
            continue

        richiesti = modello.get("richiedi_secondo")

        if richiesti and not any(
            match_parola_intera(r, tl)
            for r in richiesti
        ):
            return None

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
    # Stima conservativa: sell_min * trattativa - prezzo.
    # Non e' un profitto contabile netto: non include eventuali costi esterni.
    sell_riferimento = modello["sell_min"]

    profitto = (
        sell_riferimento * cfg_runtime["trattativa"]
        - prezzo
    )

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
    if (
        modello_trovato["brand"] == "stone island"
        and prezzo < 30
        and si_manca_certilogo(descrizione)
    ):
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
    }

# ================================================================
# PERSISTENZA
# ================================================================

# OrderedDict: ID -> timestamp notifica.
gia_visti = OrderedDict()

ultimo_affare = None

# ID -> dati degli ultimi affari notificati.
affari_recenti = OrderedDict()

def carica_visti():
    global gia_visti

    try:
        if not VISTI_FILE.exists():
            gia_visti = OrderedDict()
            return

        with open(VISTI_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            gia_visti = OrderedDict(
                (str(k), float(v))
                for k, v in data.items()
            )
        elif isinstance(data, list):
            now = time.time()
            gia_visti = OrderedDict(
                (str(x), now)
                for x in data
            )
        else:
            gia_visti = OrderedDict()

        while len(gia_visti) > 10000:
            gia_visti.popitem(last=False)

        log.info(
            "Caricati %s annunci notificati",
            len(gia_visti),
        )

    except Exception as exc:
        log.warning(
            "Errore caricamento visti: %s",
            exc,
        )
        gia_visti = OrderedDict()

def salva_visti():
    try:
        while len(gia_visti) > 10000:
            gia_visti.popitem(last=False)

        temp_file = VISTI_FILE.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                gia_visti,
                f,
                ensure_ascii=True,
            )

        os.replace(temp_file, VISTI_FILE)

    except Exception as exc:
        log.warning(
            "Errore salvataggio visti: %s",
            exc,
        )

def carica_pref():
    try:
        if not PREF_FILE.exists():
            return {}

        with open(PREF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception as exc:
        log.warning(
            "Errore caricamento preferenze: %s",
            exc,
        )
        return {}

def salva_pref(preferenze):
    try:
        temp_file = PREF_FILE.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                preferenze,
                f,
                indent=2,
                ensure_ascii=True,
            )

        os.replace(temp_file, PREF_FILE)

    except Exception as exc:
        log.warning(
            "Errore salvataggio preferenze: %s",
            exc,
        )

def get_blacklist(user_id=None):
    pref = carica_pref()

    if user_id is not None:
        data = pref.get(str(user_id), {})
        if not isinstance(data, dict):
            return []

        return [
            normalizza(str(x)).strip()
            for x in data.get("blacklist_titoli", [])
            if len(normalizza(str(x)).strip()) >= 4
        ]

    # Scanner globale: unisce le blacklist degli utenti.
    # Il comando !bad salva comunque la segnalazione per utente.
    result = []

    for data in pref.values():
        if not isinstance(data, dict):
            continue

        for titolo in data.get("blacklist_titoli", []):
            valore = normalizza(str(titolo)).strip()

            if len(valore) >= 4:
                result.append(valore)

    return list(set(result))

def titolo_blacklistato(titolo, blacklist):
    tl = normalizza(titolo)

    return any(
        match_parola_intera(b, tl)
        for b in blacklist
    )

# ================================================================
# HTTP VINTED
# ================================================================

vinted_session = None
session_lock = threading.Lock()
last_session_refresh = 0.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

def get_session():
    global vinted_session
    global last_session_refresh

    now = time.time()

    with session_lock:
        if (
            vinted_session is None
            or now - last_session_refresh > 600
        ):
            vinted_session = requests.Session()

            vinted_session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            })

            last_session_refresh = now

            log.info("Sessione HTTP inizializzata")

    return vinted_session

async def vinted_get(session, url, headers):
    """
    GET con retry limitato.
    429: rispetta Retry-After.
    5xx: retry limitato.
    403: nessun retry aggressivo e nessun tentativo di bypass.
    """

    delays = [2.0, 5.0, 10.0]

    for tentativo in range(3):
        try:
            response = await asyncio.to_thread(
                session.get,
                url,
                headers=headers,
                timeout=12,
            )

            if response.status_code == 200:
                return response

            if response.status_code == 403:
                stats["http_403"] += 1

                log.error(
                    "HTTP 403 su Vinted: accesso rifiutato. "
                    "Nessun retry aggressivo."
                )

                return None

            if response.status_code == 429:
                stats["rate_limit"] += 1

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = delays[tentativo]

                delay = min(max(delay, 2.0), 60.0)

                log.warning(
                    "Rate limit Vinted. Attendo %.1fs",
                    delay,
                )

                await asyncio.sleep(delay)
                continue

            if response.status_code in (
                500, 502, 503, 504
            ):
                stats["errori_http"] += 1

                await asyncio.sleep(
                    delays[tentativo]
                )
                continue

            stats["errori_http"] += 1

            log.warning(
                "HTTP %s su Vinted",
                response.status_code,
            )

            return None

        except requests.RequestException as exc:
            stats["errori_http"] += 1

            log.warning(
                "Errore HTTP tentativo %s: %s",
                tentativo + 1,
                exc,
            )

            await asyncio.sleep(
                delays[tentativo]
            )

    return None

# ================================================================
# QUERY / SCHEDULER
# ================================================================

QUERY_FISSE = [
    "carhartt wip detroit",
    "north face nuptse",
    "arcteryx atom lt",
    "nike tech fleece",
    "timberland premium 6-inch wheat",
    "ralph lauren polo bear",
    "patagonia better sweater",
]

QUERY_SECONDARIE = [
    "arcteryx beta lt",
    "arcteryx beta ar",
    "arcteryx cerium lt",
    "patagonia retro-x",
    "patagonia retro pile",
    "patagonia synchilla",
    "nike tech fleece tracksuit",
    "nike tech fleece jogger",
    "nike nocta",
    "stussy 8 ball",
    "stussy world tour",
    "stone island crewneck",
    "stone island hoodie",
    "stone island zip hoodie",
    "stone island overshirt",
    "stone island jacket",
    "polo bear zaino",
    "ugg ultra mini",
    "new balance 9060",
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
        emoji = "ð©"
        colore = 0x2ECC71
        ping = "@everyone AUTO-BUY SIGNAL"
    else:
        emoji = "ð¨"
        colore = 0xF1C40F
        ping = "@here ALERT"

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
        f"**Profitto stimato:** "
        f"+{res['profitto_stimato']:.2f} EUR\n"
        f"**Profitto minimo:** "
        f"{modello['profit_min']} EUR\n"
        f"**Freshness:** "
        f"{round(res['freshness'])} sec\n\n"
        "Controlla sempre foto, etichette, codici "
        "e autenticita' prima di comprare.\n\n"
        f"[VAI ALL'ANNUNCIO]({res['url']})"
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
                everyone=True,
                roles=True,
                users=True,
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
    session,
    query,
    blacklist,
):
    global ultimo_affare
    global nuovi_dal_salvataggio

    encoded = urllib.parse.quote(query)

    url = (
        "https://www.vinted.it/api/v2/catalog/items"
        f"?search_text={encoded}"
        "&order=newest_first"
        "&per_page=20"
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://www.vinted.it/",
    }

    response = await vinted_get(
        session,
        url,
        headers,
    )

    if response is None:
        return

    try:
        data = response.json()
    except ValueError:
        log.warning(
            "Risposta non JSON per query %s",
            query,
        )
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

        titolo = str(
            item.get("title", "") or ""
        )

        if titolo_blacklistato(
            titolo,
            blacklist,
        ):
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
        session = get_session()
        blacklist = get_blacklist()

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
                    session,
                    query,
                    blacklist,
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
            nuovi_dal_salvataggio >= 20
            or cicli_dal_salvataggio >= 20
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
    """
    Blacklist precisa:
    !bad 123456789

    Non usa piu' ultimo_affare per decidere quale articolo bloccare.
    """

    iid = iid.strip()

    if not iid.isdigit():
        await ctx.send(
            "Uso: !bad <ID annuncio>"
        )
        return

    affare = affari_recenti.get(iid)

    if not affare:
        await ctx.send(
            "ID non trovato tra gli ultimi affari notificati."
        )
        return

    pref = carica_pref()
    uid = str(ctx.author.id)

    if uid not in pref:
        pref[uid] = {
            "blacklist_titoli": []
        }

    lista = pref[uid].setdefault(
        "blacklist_titoli",
        []
    )

    titolo = normalizza(
        affare["titolo"]
    )[:100]

    if titolo and titolo not in lista:
        lista.append(titolo)

    pref[uid]["blacklist_titoli"] = lista[-200:]

    salva_pref(pref)

    await ctx.send(
        "Blacklistato: "
        + affare["titolo"][:80]
    )

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
        "`!bad <ID>` - blacklist articolo preciso\n"
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

# ================================================================
# FLASK HEALTH
# ================================================================

app = Flask(__name__)

@app.route("/")
def home():
    return (
        "Vinted Resell Bot V5.1 online",
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

    carica_visti()

    threading.Thread(
        target=avvia_flask,
        daemon=True,
    ).start()

    log.info(
        "Avvio Vinted Resell Bot V5.1..."
    )

    bot.run(TOKEN)

if __name__ == "__main__":
    main()
