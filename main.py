# ================================================================
# BOT VINTED RESELL V5
# Discord + Vinted scanner + filtri + scoring + notifiche
#
# ENV:
#   DISCORD_TOKEN       = token Discord
#   DISCORD_CHANNEL_ID  = ID canale notifiche (opzionale)
#   SCAN_INTERVAL       = secondi tra i cicli (default 10)
#   FRESHNESS_SECONDS   = eta massima annuncio (default 180)
#   TRADE_FACTOR        = fattore trattativa (default 0.95)
#
# COMMANDS:
#   !ping
#   !stats
#   !config
#   !set <chiave> <valore>
#   !modelli
#   !ultimo
#   !resetstats
#
# NOTE:
#   Il bot segnala opportunita'. NON acquista automaticamente.
# ================================================================

import asyncio
import json
import logging
import os
import random
import re
import threading
import time
import unicodedata
import urllib.parse
from pathlib import Path

import requests
from flask import Flask, jsonify
import discord
from discord.ext import commands, tasks


# ================================================================
# LOGGING
# ================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

log = logging.getLogger("vinted-bot")


# ================================================================
# ENV
# ================================================================

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_RAW = os.getenv("DISCORD_CHANNEL_ID", "").strip()

try:
    DISCORD_CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None
except ValueError:
    DISCORD_CHANNEL_ID = None

try:
    SCAN_INTERVAL = max(8, int(os.getenv("SCAN_INTERVAL", "10")))
except ValueError:
    SCAN_INTERVAL = 10

try:
    FRESHNESS_SECONDS = max(
        30,
        int(os.getenv("FRESHNESS_SECONDS", "180"))
    )
except ValueError:
    FRESHNESS_SECONDS = 180

try:
    TRADE_FACTOR = float(os.getenv("TRADE_FACTOR", "0.95"))
except ValueError:
    TRADE_FACTOR = 0.95

TRADE_FACTOR = min(max(TRADE_FACTOR, 0.50), 1.00)


# ================================================================
# FILE
# ================================================================

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
    help_command=None
)

canale_notifiche = None


# ================================================================
# SESSION
# ================================================================

vinted_session = None
session_lock = threading.Lock()
last_session_refresh = 0

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
        "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
    )
]


# ================================================================
# RUNTIME CONFIG
# ================================================================

cfg_runtime = {
    "trattativa": TRADE_FACTOR,
    "max_secondi_freschezza": FRESHNESS_SECONDS,
    "scan_interval": SCAN_INTERVAL,
}


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
        "notifiche_fallite": 0,
    }


stats = nuove_stats()


# ================================================================
# UTILITY
# ================================================================

def normalizza(testo):
    try:
        return (
            unicodedata
            .normalize("NFKD", str(testo))
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


# ================================================================
# BRAND
# ================================================================

BRAND_ALIASES = {
    "carhartt wip": [
        "carhartt wip",
        "carhartt",
        "carharrt",
        "carrhartt",
        "carhart",
    ],
    "the north face": [
        "the north face",
        "north face",
        "nort face",
        "northface",
        "tnf",
    ],
    "arc'teryx": [
        "arc'teryx",
        "arcteryx",
        "arc teryx",
    ],
    "patagonia": [
        "patagonia",
    ],
    "nike": [
        "nike",
        "nikke",
    ],
    "timberland": [
        "timberland",
        "timberlands",
    ],
    "ralph lauren": [
        "ralph lauren",
        "polo ralph lauren",
        "raulph lauren",
        "ralf lauren",
    ],
    "stone island": [
        "stone island",
        "stoneisland",
        "ston island",
        "stone islan",
    ],
    "stussy": [
        "stussy",
    ],
    "moncler": [
        "moncler",
    ],
    "lacoste": [
        "lacoste",
    ],
}


_ALIAS_RE_CACHE = {}


def alias_in(alias, testo):
    key = normalizza(alias)

    rx = _ALIAS_RE_CACHE.get(key)

    if rx is None:
        rx = re.compile(
            r"\b" + re.escape(key) + r"\b",
            re.I
        )
        _ALIAS_RE_CACHE[key] = rx

    return rx.search(normalizza(testo)) is not None


# ================================================================
# DIFETTI
# ================================================================

DIFETTI_ESCLUSIONE = [
    "macchia",
    "macchie",
    "macchiato",
    "macchiata",
    "sporco",
    "sporca",
    "sporchi",
    "sporche",
    "scolorito",
    "scolorita",
    "scolorimento",
    "strappo",
    "strappata",
    "strappato",
    "buco",
    "buchi",
    "foro",
    "fori",
    "zip rotta",
    "cerniera rotta",
    "zip difettosa",
    "cerniera difettosa",
    "cucitura rotta",
    "danneggiato",
    "danneggiata",
    "rovinato",
    "rovinata",
    "difetto",
    "difetti",
    "usura evidente",
    "molto usato",
    "molto usata",
    "da riparare",
    "da sistemare",
    "riparazione",
    "custom",
    "personalizzato",
    "personalizzata",
    "modificato",
    "modificata",
    "replica",
    "fake",
    "falso",
    "falsa",
    "contraffatto",
    "contraffatta",
    "non originale",
    "non autentico",
    "non autentica",
    "autenticita dubbia",
    "non so se originale",
    "non so se autentico",
    "non so se autentica",
    "non garantisco autenticita",
    "credo sia originale",
    "sembra originale",
    "potrebbe essere originale",
    "tarme",
    "tarmato",
    "tarmata",
    "pilling forte",
    "usura forte",
    "sgonfio",
    "sgonfia",
    "perde piume",
    "piume fuori",
    "piuma fuori",
    "suola staccata",
    "suola rotta",
    "pelle rotta",
    "crepe",
    "deformata",
    "deformato",
    "lacci mancanti",
    "badge falso",
    "badge non originale",
    "tessuto consumato",
    "gore-tex danneggiato",
    "membrana danneggiata",
    "riparato",
]


NEGazioni = [
    "senza ",
    "nessun",
    "nessuna",
    "non ",
    "mai ",
    "zero ",
    "niente ",
]


def ha_difetto(testo):
    tl = " " + normalizza(testo) + " "

    for difetto in DIFETTI_ESCLUSIONE:
        start = 0

        while True:
            idx = tl.find(difetto, start)

            if idx == -1:
                break

            prima = tl[max(0, idx - 30):idx]

            if not any(n in prima for n in NEGazioni):
                return True, difetto

            start = idx + len(difetto)

    return False, ""


# ================================================================
# STILE / REPLICA
# ================================================================

STILE_PATTERN = re.compile(
    r"\b(simile a|ispirato a|inspired by|inspired)\b",
    re.I
)


def ha_pattern_stile(testo, brand):
    tl = normalizza(testo)

    if not STILE_PATTERN.search(tl):
        return False

    aliases = BRAND_ALIASES.get(brand, [])

    return any(alias_in(alias, tl) for alias in aliases)


# ================================================================
# BAMBINI
# ================================================================

BAMBINO_ESCLUSIONE = [
    "bambino",
    "bambina",
    "junior",
    "kids",
    "da bambino",
    "per bambino",
    "child",
    "kid",
    "junior fit",
    "bimbo",
    "bimba",
]

BAMBINO_ETA_PATTERN = re.compile(
    r"\b(\d{1,2})\s*anni\b",
    re.I
)

BAMBINO_CODICI_PATTERN = re.compile(
    r"\b(152|164|176|yl|ym)\b",
    re.I
)


def ha_eta_bambino(testo):
    for match in BAMBINO_ETA_PATTERN.finditer(testo):
        try:
            if int(match.group(1)) < 18:
                return True
        except Exception:
            continue

    return False


_BAMBINO_ESCLUSIONE_SEMPLICE = [
    "bambino", "bambina", "junior",
    "da bambino", "per bambino", "junior fit",
]

_BAMBINO_ESCLUSIONE_WB = re.compile(
    r"\b(kids|kid|child|bimbo|bimba)\b", re.I
)


def is_bambino(testo, taglia):
    tl = normalizza(testo)

    if any(x in tl for x in _BAMBINO_ESCLUSIONE_SEMPLICE):
        return True

    if _BAMBINO_ESCLUSIONE_WB.search(tl):
        return True

    if ha_eta_bambino(tl):
        return True

    tg = str(taglia or "")

    if "ann" in tg.lower():
        return True

    if BAMBINO_CODICI_PATTERN.search(tg):
        return True

    return False


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
    "nuovo con cartellino": [
        "nuovo con cartellino",
        "new with tags",
        "nwt",
    ],
    "nuovo senza cartellino": [
        "nuovo senza cartellino",
        "new without tags",
        "nwot",
    ],
    "nuovo": [
        "nuovo",
        "new",
    ],
    "ottime": [
        "ottime condizioni",
        "ottime",
    ],
    "molto buono": [
        "molto buono",
        "molto buona",
    ],
    "buone": [
        "buone condizioni",
        "buone",
    ],
    "discrete": [
        "discrete condizioni",
        "discrete",
        "soddisfacenti",
    ],
    "sufficiente": [
        "sufficiente",
    ],
}


TAGLIE_RIFIUTA_GLOBALE = [
    "XXS"
]


BUONE_AMMESSE = {
    "tnf_nuptse",
    "carhartt_detroit",
    "timberland_wheat",
}


DISCRETE_AMMESSE = {
    "timberland_wheat"
}


# ================================================================
# COLORE
# ================================================================

COLORE_BLOCCANTE = {
    "timberland_wheat": {
        "richiedi_uno": [
            "wheat",
            "yellow",
            "giallo",
            "gialla",
            "grano",
            "premium",
        ]
    },
    "carhartt_detroit": {
        "se_keyword_in": [
            "hamilton brown",
            "detroit brown",
        ],
        "rifiuta_se_contiene": [
            "black",
            "nero",
            "blue",
            "navy",
        ],
    },
}


def colore_ok(model_id, testo, keyword_matchata):
    regola = COLORE_BLOCCANTE.get(model_id)

    if not regola:
        return True

    tl = normalizza(testo)

    if "richiedi_uno" in regola:
        return any(
            normalizza(x) in tl
            for x in regola["richiedi_uno"]
        )

    if "se_keyword_in" in regola:
        if normalizza(keyword_matchata) in [
            normalizza(x)
            for x in regola["se_keyword_in"]
        ]:
            if any(
                normalizza(x) in tl
                for x in regola["rifiuta_se_contiene"]
            ):
                return False

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
    "moncler",
]


def seller_rischioso(item):
    user = item.get("user") or {}

    feedback_count = user.get("feedback_count")
    item_count = user.get("item_count")
    reputation = user.get("feedback_reputation")

    if feedback_count is None and item_count is None:
        return False

    try:
        fb = safe_int(feedback_count, 0)
        items = safe_int(item_count, 0)
        rep = safe_float(reputation, 1.0)

        if fb == 0 and items < 5:
            return True

        if fb < 3 and rep < 0.8 and items < 10:
            return True

    except Exception:
        return False

    return False


# ================================================================
# STONE ISLAND AUTENTICITA'
# ================================================================

_SI_CODICE_PATTERN = re.compile(
    r"\b(art|article|articolo|codice|style|product|certilogo|clg)"
    r"[\s.:/#-]*\d{4,8}\b",
    re.I
)


def si_manca_certilogo(descrizione):
    d = normalizza(descrizione)

    marcatori = [
        "art number", "numero articolo",
        "codice articolo", "codice prodotto",
        "certilogo", "clg",
    ]

    if any(m in d for m in marcatori):
        return False

    if _SI_CODICE_PATTERN.search(d):
        return False

    return True


# ================================================================
# MODELLI
# ================================================================

MODELLI = [

    {
        "id": "tnf_nuptse",
        "brand": "the north face",
        "nome": "1996/1990 Retro Nuptse",
        "query": "the north face nuptse",
        "keywords": [
            "1996 retro nuptse",
            "nuptse 1996",
            "1996 nuptse",
            "1990 retro nuptse",
            "nuptse 1990",
            "retro nuptse",
            "nuptse 700",
            "700 nuptse",
            "nupste",
            "nuptze",
        ],
        "escludi_se": [
            "baltoro",
            "gilet",
            "vest",
            "smanicato",
            "chaleco",
            "sin mangas",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 45,
                "buy_max": 70
            },
            "buone": {
                "buy_max": 45
            },
            "nuovo senza cartellino": {
                "buy_max": 75
            },
            "nuovo con cartellino": {
                "buy_max": 100
            },
        },
        "sell_min": 105,
        "sell_max": 135,
        "profit_min": 30,
        "taglie_rifiuta": ["XS"],
    },

    {
        "id": "carhartt_detroit",
        "brand": "carhartt wip",
        "nome": "Detroit/Michigan/Active Jacket",
        "query": "carhartt detroit jacket",
        "freshness_sec": 1800,
        "keywords": [
            "og detroit",
            "detroit jacket",
            "michigan coat",
            "active jacket",
            "carhartt wip detroit",
            "carhartt detroit",
            "hamilton brown",
            "detroit brown",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 40,
                "buy_max": 65
            },
            "buone": {
                "auto_buy": 28,
                "buy_max": 45
            },
            "nuovo senza cartellino": {
                "buy_max": 85
            },
            "nuovo con cartellino": {
                "buy_max": 110
            },
        },
        "sell_min": 115,
        "sell_max": 145,
        "profit_min": 35,
        "taglie_rifiuta": ["XS"],
    },

    {
        "id": "arcteryx_atom_lt",
        "brand": "arc'teryx",
        "nome": "Atom LT",
        "query": "arcteryx atom lt",
        "keywords": ["atom lt"],
        "condizioni": {
            "ottime": {
                "auto_buy": 55,
                "buy_max": 75
            },
            "nuovo senza cartellino": {
                "buy_max": 105
            },
            "nuovo con cartellino": {
                "buy_max": 125
            },
        },
        "sell_min": 130,
        "sell_max": 155,
        "profit_min": 45,
    },

    {
        "id": "arcteryx_beta_lt",
        "brand": "arc'teryx",
        "nome": "Beta LT",
        "query": "arcteryx beta lt",
        "keywords": ["beta lt"],
        "condizioni": {
            "ottime": {
                "auto_buy": 50,
                "buy_max": 65
            },
            "nuovo senza cartellino": {
                "buy_max": 90
            },
            "nuovo con cartellino": {
                "buy_max": 115
            },
        },
        "sell_min": 115,
        "sell_max": 160,
        "profit_min": 38,
    },

    {
        "id": "arcteryx_beta_ar",
        "brand": "arc'teryx",
        "nome": "Beta AR",
        "query": "arcteryx beta ar",
        "freshness_sec": 1800,
        "keywords": ["beta ar"],
        "condizioni": {
            "ottime": {
                "auto_buy": 85,
                "buy_max": 120
            },
            "nuovo senza cartellino": {
                "buy_max": 155
            },
            "nuovo con cartellino": {
                "buy_max": 180
            },
        },
        "sell_min": 190,
        "sell_max": 250,
        "profit_min": 50,
    },

    {
        "id": "arcteryx_cerium_lt",
        "brand": "arc'teryx",
        "nome": "Cerium LT",
        "query": "arcteryx cerium",
        "keywords": [
            "cerium lt",
            "arcteryx cerium",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 60,
                "buy_max": 85
            },
            "nuovo senza cartellino": {
                "buy_max": 115
            },
            "nuovo con cartellino": {
                "buy_max": 140
            },
        },
        "sell_min": 160,
        "sell_max": 200,
        "profit_min": 45,
    },

    {
        "id": "patagonia_retrox",
        "brand": "patagonia",
        "nome": "Retro-X",
        "query": "patagonia retro x",
        "keywords": [
            "retro-x",
            "retro x",
            "classic retro-x",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 30,
                "buy_max": 50
            },
            "nuovo con cartellino": {
                "buy_max": 70
            },
            "nuovo senza cartellino": {
                "buy_max": 70
            },
        },
        "sell_min": 90,
        "sell_max": 120,
        "profit_min": 30,
    },

    {
        "id": "patagonia_retropile",
        "brand": "patagonia",
        "nome": "Retro Pile",
        "query": "patagonia retro pile",
        "keywords": ["retro pile"],
        "condizioni": {
            "ottime": {
                "auto_buy": 25,
                "buy_max": 40
            },
            "nuovo con cartellino": {
                "buy_max": 55
            },
            "nuovo senza cartellino": {
                "buy_max": 55
            },
        },
        "sell_min": 75,
        "sell_max": 105,
        "profit_min": 25,
    },

    {
        "id": "patagonia_synchilla",
        "brand": "patagonia",
        "nome": "Synchilla",
        "query": "patagonia synchilla",
        "keywords": ["synchilla"],
        "condizioni": {
            "ottime": {
                "auto_buy": 15,
                "buy_max": 25
            },
            "nuovo con cartellino": {
                "buy_max": 40
            },
            "nuovo senza cartellino": {
                "buy_max": 40
            },
        },
        "sell_min": 45,
        "sell_max": 70,
        "profit_min": 25,
    },

    {
        "id": "patagonia_bettersweater",
        "brand": "patagonia",
        "nome": "Better Sweater",
        "query": "patagonia better sweater",
        "keywords": ["better sweater"],
        "condizioni": {
            "ottime": {
                "auto_buy": 15,
                "buy_max": 25
            },
            "nuovo con cartellino": {
                "buy_max": 40
            },
            "nuovo senza cartellino": {
                "buy_max": 40
            },
        },
        "sell_min": 48,
        "sell_max": 65,
        "profit_min": 25,
    },

    {
        "id": "nike_techfleece_felpa",
        "brand": "nike",
        "nome": "Tech Fleece Felpa",
        "query": "nike tech fleece hoodie",
        "keywords": [
            "tech fleece hoodie",
            "tech fleece felpa",
            "tech fleece crew",
        ],
        "escludi_se": ["nocta"],
        "condizioni": {
            "ottime": {
                "auto_buy": 12,
                "buy_max": 15
            },
            "buone": {
                "buy_max": 10
            },
            "nuovo con cartellino": {
                "buy_max": 25
            },
            "nuovo senza cartellino": {
                "buy_max": 25
            },
        },
        "sell_min": 30,
        "sell_max": 45,
        "profit_min": 25,
        "taglie_rifiuta": ["XS"],
        "taglia_s_solo_sotto": 20,
    },

    {
        "id": "nike_techfleece_tuta",
        "brand": "nike",
        "nome": "Tech Fleece Tuta completa",
        "query": "nike tech fleece tuta",
        "keywords": [
            "tech fleece tuta",
            "tech fleece tracksuit",
            "tech fleece set",
        ],
        "escludi_se": ["nocta"],
        "condizioni": {
            "ottime": {
                "auto_buy": 22,
                "buy_max": 25
            },
            "nuovo con cartellino": {
                "buy_max": 42
            },
            "nuovo senza cartellino": {
                "buy_max": 42
            },
        },
        "sell_min": 50,
        "sell_max": 75,
        "profit_min": 25,
        "taglie_rifiuta": ["XS"],
    },

    {
        "id": "nike_techfleece_pant",
        "brand": "nike",
        "nome": "Tech Fleece Pantalone",
        "query": "nike tech fleece jogger",
        "keywords": [
            "tech fleece jogger",
            "tech fleece pant",
            "tech fleece pantalone",
        ],
        "escludi_se": ["nocta"],
        "condizioni": {
            "ottime": {
                "auto_buy": 17,
                "buy_max": 20
            },
            "nuovo con cartellino": {
                "buy_max": 32
            },
            "nuovo senza cartellino": {
                "buy_max": 32
            },
        },
        "sell_min": 40,
        "sell_max": 58,
        "profit_min": 25,
        "taglie_rifiuta": ["XS"],
        "taglia_s_solo_sotto": 20,
    },

    {
        "id": "nike_nocta_hoodie",
        "brand": "nike",
        "nome": "Nocta Hoodie",
        "query": "nike nocta hoodie",
        "keywords": [
            "nocta hoodie",
            "nike x nocta hoodie",
            "nocta tech hoodie",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 30,
                "buy_max": 35
            },
            "nuovo con cartellino": {
                "buy_max": 40
            },
            "nuovo senza cartellino": {
                "buy_max": 40
            },
        },
        "sell_min": 55,
        "sell_max": 80,
        "profit_min": 25,
    },

    {
        "id": "nike_nocta_pant",
        "brand": "nike",
        "nome": "Nocta Joggers",
        "query": "nike nocta joggers",
        "keywords": [
            "nocta joggers",
            "nocta pant",
            "nike x nocta pant",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 22,
                "buy_max": 25
            },
            "nuovo con cartellino": {
                "buy_max": 32
            },
            "nuovo senza cartellino": {
                "buy_max": 32
            },
        },
        "sell_min": 42,
        "sell_max": 60,
        "profit_min": 25,
    },

    {
        "id": "nike_nocta_tuta",
        "brand": "nike",
        "nome": "Nocta Tracksuit completa",
        "query": "nike nocta tracksuit",
        "keywords": [
            "nocta tracksuit",
            "nike x nocta tracksuit",
            "nocta tuta",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 55,
                "buy_max": 60
            },
            "nuovo con cartellino": {
                "buy_max": 75
            },
            "nuovo senza cartellino": {
                "buy_max": 75
            },
        },
        "sell_min": 95,
        "sell_max": 130,
        "profit_min": 30,
    },

    {
        "id": "timberland_wheat",
        "brand": "timberland",
        "nome": "Premium 6-Inch Wheat",
        "query": "timberland premium 6 inch wheat",
        "keywords": [
            "premium 6-inch wheat",
            "premium 6 inch wheat",
            "6-inch premium",
            "6 inch premium",
            "wheat boot",
            "wheat premium",
            "yellow premium",
            "gialla premium",
            "gialle premium",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 40,
                "buy_max": 45
            },
            "buone": {
                "auto_buy": 25,
                "buy_max": 28
            },
            "nuovo": {
                "buy_max": 65
            },
        },
        "sell_min": 95,
        "sell_max": 125,
        "profit_min": 30,
        "taglie_alert_extra": [
            "36",
            "37",
            "38",
        ],
        "discrete_eccezione": {
            "buy_max": 18
        },
    },

    {
        "id": "rl_polobear",
        "brand": "ralph lauren",
        "nome": "Polo Bear",
        "query": "ralph lauren polo bear",
        "keywords": [
            "polo bear",
            "bear sweater",
            "bear knit",
            "polo bear knit",
            "polo bear sweatshirt",
            "polo bear hoodie",
        ],
        "escludi_se": [
            "patch",
            "thermocollant",
            "iron-on",
            "iron on",
            "toppa",
            "ecusson",
            "aufnaher",
            "sticker",
            "pin",
            "spilla",
            "badge",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 18,
                "buy_max": 25
            },
            "nuovo con cartellino": {
                "buy_max": 40
            },
            "nuovo senza cartellino": {
                "buy_max": 40
            },
        },
        "sell_min": 65,
        "sell_max": 90,
        "profit_min": 30,
        "taglia_s_solo_sotto": 20,
    },

    {
        "id": "rl_polobear_zaino",
        "brand": "ralph lauren",
        "nome": "Polo Bear Zaino/Borsa",
        "query": "polo bear zaino",
        "keywords": [
            "polo bear zaino",
            "polo bear rucksack",
            "polo bear backpack",
            "polo bear borsa",
            "bear zaino",
            "bear backpack",
            "bear borsa",
        ],
        "escludi_se": [
            "patch",
            "thermocollant",
            "iron-on",
            "iron on",
            "toppa",
            "ecusson",
            "aufnaher",
            "sticker",
            "pin",
            "spilla",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 20,
                "buy_max": 30
            },
        },
        "sell_min": 80,
        "sell_max": 110,
        "profit_min": 35,
    },

    {
        "id": "si_crewneck",
        "brand": "stone island",
        "nome": "Sweatshirt/Crewneck",
        "query": "stone island sweatshirt",
        "keywords": [
            "crewneck",
            "sweatshirt",
            "felpa girocollo",
        ],
        "escludi_se": [
            "hoodie",
            "zip",
            "overshirt",
            "jacket",
            "giacca",
            "giubbotto",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 35,
                "buy_max": 55
            },
            "nuovo": {
                "buy_max": 75
            },
        },
        "sell_min": 105,
        "sell_max": 135,
        "profit_min": 45,
    },

    {
        "id": "si_ziphoodie",
        "brand": "stone island",
        "nome": "Zip Hoodie",
        "query": "stone island zip hoodie",
        "keywords": [
            "zip hoodie",
            "felpa cappuccio zip",
        ],
        "escludi_se": [
            "overshirt",
            "jacket",
            "giacca",
            "giubbotto",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 35,
                "buy_max": 50
            },
            "nuovo": {
                "buy_max": 75
            },
        },
        "sell_min": 115,
        "sell_max": 150,
        "profit_min": 45,
    },

    {
        "id": "si_hoodie",
        "brand": "stone island",
        "nome": "Hoodie",
        "query": "stone island hoodie",
        "keywords": [
            "hoodie",
            "felpa cappuccio",
        ],
        "escludi_se": [
            "zip",
            "overshirt",
            "jacket",
            "giacca",
            "giubbotto",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 30,
                "buy_max": 50
            },
            "nuovo": {
                "buy_max": 75
            },
        },
        "sell_min": 105,
        "sell_max": 135,
        "profit_min": 45,
    },

    {
        "id": "si_overshirt",
        "brand": "stone island",
        "nome": "Overshirt",
        "query": "stone island overshirt",
        "keywords": [
            "overshirt"
        ],
        "escludi_se": [
            "jacket",
            "giacca",
            "giubbotto",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 50,
                "buy_max": 75
            },
            "nuovo": {
                "buy_max": 110
            },
        },
        "sell_min": 145,
        "sell_max": 185,
        "profit_min": 45,
    },

    {
        "id": "si_jacket",
        "brand": "stone island",
        "nome": "Jacket",
        "query": "stone island jacket",
        "keywords": [
            "jacket",
            "giacca",
            "giubbotto",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 55,
                "buy_max": 75
            },
            "nuovo": {
                "buy_max": 115
            },
        },
        "sell_min": 135,
        "sell_max": 175,
        "profit_min": 45,
    },

    {
        "id": "moncler_piumino",
        "brand": "moncler",
        "nome": "Piumino Moncler",
        "query": "moncler piumino",
        "keywords": [
            "moncler",
        ],
        "escludi_se": [
            "gilet",
            "vest",
            "smanicato",
            "bambino",
            "bambina",
            "bimbo",
            "bimba",
            "replica",
            "fake",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 80,
                "buy_max": 130
            },
            "buone": {
                "auto_buy": 55,
                "buy_max": 90
            },
            "nuovo senza cartellino": {
                "buy_max": 180
            },
            "nuovo con cartellino": {
                "buy_max": 220
            },
        },
        "sell_min": 200,
        "sell_max": 320,
        "profit_min": 50,
        "taglie_rifiuta": ["XS"],
    },

    {
        "id": "lacoste_felpa",
        "brand": "lacoste",
        "nome": "Lacoste Felpa/Maglione",
        "query": "lacoste felpa",
        "keywords": [
            "felpa lacoste",
            "lacoste felpa",
            "lacoste hoodie",
            "lacoste sweatshirt",
            "maglione lacoste",
            "lacoste maglione",
        ],
        "escludi_se": [
            "replica",
            "fake",
            "bambino",
            "bambina",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 12,
                "buy_max": 20
            },
            "nuovo senza cartellino": {
                "buy_max": 30
            },
            "nuovo con cartellino": {
                "buy_max": 40
            },
        },
        "sell_min": 38,
        "sell_max": 55,
        "profit_min": 25,
        "taglie_rifiuta": ["XS"],
    },

    {
        "id": "lacoste_polo",
        "brand": "lacoste",
        "nome": "Lacoste Polo",
        "query": "lacoste polo",
        "keywords": [
            "polo lacoste",
            "lacoste polo",
            "lacoste l.12.12",
            "l.12.12",
        ],
        "escludi_se": [
            "replica",
            "fake",
            "bambino",
            "bambina",
        ],
        "condizioni": {
            "ottime": {
                "auto_buy": 8,
                "buy_max": 15
            },
            "nuovo senza cartellino": {
                "buy_max": 22
            },
            "nuovo con cartellino": {
                "buy_max": 30
            },
        },
        "sell_min": 28,
        "sell_max": 42,
        "profit_min": 20,
        "taglie_rifiuta": ["XS"],
    },

    {
        "id": "stussy_8ball",
        "brand": "stussy",
        "nome": "8 Ball / World Tour",
        "query": "stussy 8 ball",
        "keywords": [
            "8 ball",
            "world tour",
        ],
        "richiedi_secondo": [
            "t-shirt",
            "tee",
            "longsleeve",
            "hoodie",
            "felpa",
            "sweat",
            "sweatshirt",
            "crewneck",
        ],
        "escludi_se": [
            "porte cles",
            "portachiavi",
            "keychain",
            "keyring",
            "charm",
            "portachiave",
            "figure",
            "palla",
            "8 ball key",
            "pendentif",
        ],
        "richiedi_taglia": True,
        "condizioni": {
            "ottime": {
                "auto_buy": 15,
                "buy_max": 25
            },
        },
        "sell_min": 50,
        "sell_max": 85,
        "profit_min": 25,
        "taglia_s_solo_sotto": 20,
    },
]


# Tetto largo usato nel controllo veloce PRIMA di sapere quale modello ha
# matchato (in scansione_query) â deve essere almeno grande quanto la finestra
# piÃ¹ larga tra tutti i modelli (es. Detroit/Beta AR a 1800s), altrimenti quei
# modelli rari verrebbero scartati qui prima ancora di arrivare a valuta_item,
# dove poi si applica il controllo preciso per-modello (vedi punto 4b)
FRESHNESS_CEILING = max(
    [FRESHNESS_SECONDS]
    + [m.get("freshness_sec", FRESHNESS_SECONDS) for m in MODELLI]
)


# ================================================================
# QUERY
# ================================================================

QUERY_FISSE = [
    "carhartt wip detroit",
    "north face nuptse",
    "arcteryx atom lt",
    "nike tech fleece",
    "timberland premium 6-inch wheat",
    "ralph lauren polo bear",
    "patagonia better sweater",
    "lacoste felpa",
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
    "moncler piumino",
    "lacoste polo",
]


rotazione_idx = 0


# ================================================================
# PERSISTENZA
# ================================================================

gia_visti = set()


def carica_visti():
    global gia_visti

    try:
        if not VISTI_FILE.exists():
            gia_visti = set()
            return

        with open(VISTI_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            gia_visti = set(str(x) for x in data)
        else:
            gia_visti = set()

        log.info(
            "Caricati %s annunci gia' visti",
            len(gia_visti)
        )

    except Exception as exc:
        log.warning(
            "Errore caricamento visti: %s",
            exc
        )
        gia_visti = set()


def salva_visti():
    try:
        ultimi = list(gia_visti)[-10000:]

        temp_file = VISTI_FILE.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                ultimi,
                f,
                ensure_ascii=True
            )

        os.replace(temp_file, VISTI_FILE)

    except Exception as exc:
        log.warning(
            "Errore salvataggio visti: %s",
            exc
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
            exc
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
                ensure_ascii=True
            )

        os.replace(temp_file, PREF_FILE)

    except Exception as exc:
        log.warning(
            "Errore salvataggio preferenze: %s",
            exc
        )


# ================================================================
# ULTIMO AFFARE
# ================================================================

ultimo_affare = None


# ================================================================
# HTTP SESSION
# ================================================================

def get_session():
    global vinted_session
    global last_session_refresh

    now = time.time()

    with session_lock:
        if (
            vinted_session is None
            or now - last_session_refresh > 300
        ):
            try:
                nuova = requests.Session()

                ua = random.choice(USER_AGENTS)

                # Header che simulano un browser reale â senza questi
                # Vinted riconosce il bot e restituisce 403/503 su tutte le query
                nuova.headers.update({
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                })

                # Visita la homepage prima per ottenere i cookie di sessione â
                # senza questo le richieste API vengono bloccate (403/503)
                try:
                    nuova.get(
                        "https://www.vinted.it",
                        timeout=15,
                        allow_redirects=True
                    )
                    time.sleep(random.uniform(1.0, 2.0))
                except Exception:
                    pass

                # Ora switcha agli header API
                nuova.headers.update({
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.vinted.it/",
                    "X-Requested-With": "XMLHttpRequest",
                })

                vinted_session = nuova
                last_session_refresh = now

                log.info("Sessione HTTP inizializzata con cookie")

            except Exception as exc:
                log.error(
                    "Errore creazione sessione: %s",
                    exc
                )

    return vinted_session


# ================================================================
# HTTP GET
# ================================================================

async def vinted_get(session, url, headers):
    """
    GET con retry limitato.
    Non tenta di aggirare CAPTCHA, blocchi o sistemi anti-abuso.
    """

    delays = [1.5, 3.0, 6.0]

    for tentativo in range(3):

        try:
            response = await asyncio.to_thread(
                session.get,
                url,
                headers=headers,
                timeout=12
            )

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                stats["rate_limit"] += 1

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = delays[min(tentativo, len(delays) - 1)]

                delay = min(max(delay, 2), 30)

                log.warning(
                    "Rate limit ricevuto. Attendo %.1fs",
                    delay
                )

                await asyncio.sleep(delay)
                continue

            if response.status_code in (500, 502, 503, 504):
                stats["errori_http"] += 1

                delay = delays[
                    min(tentativo, len(delays) - 1)
                ]

                await asyncio.sleep(delay)
                continue

            stats["errori_http"] += 1

            log.warning(
                "HTTP %s su Vinted (url: %s)",
                response.status_code,
                url[:80]
            )

            return None

        except requests.RequestException as exc:
            stats["errori_http"] += 1

            log.warning(
                "Errore HTTP tentativo %s: %s",
                tentativo + 1,
                exc
            )

            await asyncio.sleep(
                delays[min(tentativo, len(delays) - 1)]
            )

    return None


# ================================================================
# MATCH MODELLO
# ================================================================

_KW_RE_CACHE = {}


def _kw_match(keyword, tl):
    key = keyword
    rx = _KW_RE_CACHE.get(key)
    if rx is None:
        rx = re.compile(r"\b" + re.escape(key) + r"\b", re.I)
        _KW_RE_CACHE[key] = rx
    return rx.search(tl) is not None


def match_modello(modello, testo):
    tl = normalizza(testo)

    for esclusione in modello.get("escludi_se", []):
        if _kw_match(normalizza(esclusione), tl):
            return None

    for keyword in modello.get("keywords", []):
        if _kw_match(normalizza(keyword), tl):

            richiesti = modello.get("richiedi_secondo")

            if richiesti:
                if not any(
                    _kw_match(normalizza(r), tl)
                    for r in richiesti
                ):
                    return None

            return keyword

    return None


# ================================================================
# CONDIZIONE
# ================================================================

def match_parola_intera(keyword, testo):
    return re.search(
        r"\b" + re.escape(normalizza(keyword)) + r"\b",
        normalizza(testo),
        re.I
    ) is not None


def condizione_da_item(item, titolo):
    status = normalizza(
        str(item.get("status", "")).strip()
    )

    if status in CONDIZIONI_API_MAP:
        return CONDIZIONI_API_MAP[status]

    testo = status + " " + normalizza(titolo)

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
        keywords = CONDIZIONI_KEYWORDS.get(
            condizione,
            []
        )

        for keyword in keywords:
            if match_parola_intera(
                keyword,
                testo
            ):
                return condizione

    return ""


# ================================================================
# TAGLIA
# ================================================================

def taglia_da_item(item):
    raw = str(
        item.get("size_title", "") or ""
    )

    token = raw.split("/")[0].strip()

    return token.upper()


# ================================================================
# PROFITTO
# ================================================================

def calcola_profitto(
    modello,
    condizione,
    prezzo
):
    # Il SELL CONSERVATIVO Ã¨ legato al MODELLO, non alla condizione dell'annuncio
    # (il documento originale non prevede nessun moltiplicatore per "nuovo" â lo stesso
    # errore c'era nel primo bot V10 con moltiplicatori inventati senza dati di mercato)
    sell_riferimento = modello["sell_min"]

    profitto = (
        sell_riferimento
        * cfg_runtime["trattativa"]
        - prezzo
    )

    return round(
        profitto,
        2
    ), sell_riferimento


# ================================================================
# SCORING
# ================================================================

def calcola_score(
    modello,
    condizione,
    prezzo,
    profitto,
    cuori,
    taglia,
    seller_rischio,
    freshness
):
    score = 0

    # Profitto
    if profitto >= modello["profit_min"] + 40:
        score += 35
    elif profitto >= modello["profit_min"] + 20:
        score += 28
    elif profitto >= modello["profit_min"]:
        score += 20

    # Prezzo rispetto al buy max
    buy_max = None

    block = modello["condizioni"].get(
        condizione
    )

    if block:
        buy_max = block.get("buy_max")

    if buy_max:
        ratio = prezzo / max(buy_max, 1)

        if ratio <= 0.50:
            score += 20
        elif ratio <= 0.75:
            score += 15
        elif ratio <= 1:
            score += 8

    # Cuori
    cuori = safe_int(cuori)

    if cuori >= 20:
        score += 15
    elif cuori >= 10:
        score += 12
    elif cuori >= 5:
        score += 7
    elif cuori >= 1:
        score += 3

    # Freshness
    if freshness is not None:
        if freshness <= 30:
            score += 15
        elif freshness <= 90:
            score += 12
        elif freshness <= 180:
            score += 8

    # Condizione
    if condizione in (
        "nuovo",
        "nuovo con cartellino",
    ):
        score += 10
    elif condizione == "ottime":
        score += 8
    elif condizione == "buone":
        score += 3

    # Seller rischioso
    if seller_rischio:
        score -= 15

    return max(
        0,
        min(100, score)
    )


# ================================================================
# VALUTAZIONE
# ================================================================

def valuta_item(item):
    titolo = str(
        item.get("title", "") or ""
    )

    descrizione = str(
        item.get("description", "") or ""
    )[:600]

    testo_completo = (
        titolo + " " + descrizione
    )

    tl = normalizza(testo_completo)

    prezzo = safe_float(
        (item.get("price") or {}).get("amount")
    )

    if prezzo <= 0:
        return None

    # ------------------------------------------------------------
    # 1. BAMBINO
    # ------------------------------------------------------------

    taglia = taglia_da_item(item)

    if is_bambino(
        testo_completo,
        taglia
    ):
        stats["bambino"] += 1
        return None

    # ------------------------------------------------------------
    # 2. DIFETTI
    # ------------------------------------------------------------

    difetto, parola_difetto = ha_difetto(
        testo_completo
    )

    if difetto:
        stats["escluso_difetto"] += 1
        return None

    # ------------------------------------------------------------
    # 3. BRAND
    # ------------------------------------------------------------

    brand_field = str(
        item.get("brand_title", "") or ""
    )

    testo_brand = (
        titolo + " " + brand_field
    )

    brands_trovati = []

    for brand, aliases in BRAND_ALIASES.items():
        if any(
            alias_in(alias, testo_brand)
            for alias in aliases
        ):
            brands_trovati.append(brand)

    if not brands_trovati:
        stats["brand_no"] += 1
        return None

    # ------------------------------------------------------------
    # 4. MODELLO
    # ------------------------------------------------------------

    modello_trovato = None
    keyword_matchata = None

    for modello in MODELLI:

        if modello["brand"] not in brands_trovati:
            continue

        keyword = match_modello(
            modello,
            testo_completo
        )

        if keyword is not None:
            modello_trovato = modello
            keyword_matchata = keyword
            break

    if modello_trovato is None:
        stats["modello_no"] += 1
        return None

    # ------------------------------------------------------------
    # 4b. FRESHNESS specifica per QUESTO modello â i modelli rari
    # (Beta AR, Detroit) hanno una finestra piÃ¹ larga (30 min) perchÃ©
    # escono raramente; i modelli comuni usano il default globale (180s)
    # ------------------------------------------------------------

    freshness = None

    cts = (
        item.get("created_at_ts")
        or
        (item.get("photo") or {})
        .get("high_resolution", {})
        .get("timestamp")
    )

    try:
        cts_val = float(cts)

        if cts_val > 1e10:
            cts_val /= 1000

        freshness = max(
            0,
            time.time() - cts_val
        )

    except Exception:
        freshness = None

    if freshness is not None:
        freshness_sec_modello = modello_trovato.get(
            "freshness_sec",
            cfg_runtime["max_secondi_freschezza"]
        )
        if freshness > freshness_sec_modello:
            stats["freshness_no"] += 1
            return None

    # ------------------------------------------------------------
    # 5. STILE
    # ------------------------------------------------------------

    if ha_pattern_stile(
        tl,
        modello_trovato["brand"]
    ):
        stats["escluso_stile"] += 1
        return None

    # ------------------------------------------------------------
    # 6. COLORE
    # ------------------------------------------------------------

    if not colore_ok(
        modello_trovato["id"],
        tl,
        keyword_matchata
    ):
        stats["modello_no"] += 1
        return None

    # ------------------------------------------------------------
    # 7. TAGLIA OBBLIGATORIA
    # ------------------------------------------------------------

    if modello_trovato.get(
        "richiedi_taglia"
    ):
        if (
            not taglia
            or "UNICA" in taglia.upper()
        ):
            stats["modello_no"] += 1
            return None

    # ------------------------------------------------------------
    # 8. SELLER
    # ------------------------------------------------------------

    seller_rischio = seller_rischioso(
        item
    )

    if (
        modello_trovato["brand"]
        in SELLER_RISCHIO_BRANDS
        and seller_rischio
    ):
        stats["seller_rischio"] += 1
        return None

    # ------------------------------------------------------------
    # 9. CONDIZIONE
    # ------------------------------------------------------------

    condizione = condizione_da_item(
        item,
        titolo
    )

    if not condizione:
        stats["condizione_no"] += 1
        return None

    if (
        condizione == "buone"
        and modello_trovato["id"]
        not in BUONE_AMMESSE
    ):
        stats["condizione_no"] += 1
        return None

    if (
        condizione == "discrete"
        and modello_trovato["id"]
        not in DISCRETE_AMMESSE
    ):
        stats["condizione_no"] += 1
        return None

    if condizione == "discrete":

        ecc = modello_trovato.get(
            "discrete_eccezione"
        )

        if not ecc:
            stats["condizione_no"] += 1
            return None

        cond_block = {
            "buy_max": ecc["buy_max"]
        }

        auto_buy_soglia = None

    else:

        cond_block = (
            modello_trovato["condizioni"]
            .get(condizione)
        )

        if (
            cond_block is None
            and condizione == "molto buono"
        ):
            base = (
                modello_trovato["condizioni"]
                .get("ottime")
            )

            if base:
                cond_block = {
                    "buy_max": round(
                        base.get(
                            "buy_max",
                            0
                        ) * 0.90
                    )
                }

        if (
            cond_block is None
            and condizione in (
                "nuovo con cartellino",
                "nuovo senza cartellino",
            )
        ):
            cond_block = (
                modello_trovato["condizioni"]
                .get("nuovo")
            )

        if cond_block is None:
            stats["condizione_no"] += 1
            return None

        auto_buy_soglia = (
            cond_block.get("auto_buy")
        )

    # ------------------------------------------------------------
    # 10. BUY MAX
    # ------------------------------------------------------------

    buy_max = safe_float(
        cond_block.get("buy_max")
    )

    if prezzo > buy_max:
        return None

    # ------------------------------------------------------------
    # 11. TAGLIA
    # ------------------------------------------------------------

    taglie_rifiuta = (
        modello_trovato.get(
            "taglie_rifiuta",
            []
        )
        + TAGLIE_RIFIUTA_GLOBALE
    )

    if taglia.upper() in [
        str(x).upper()
        for x in taglie_rifiuta
    ]:
        stats["taglia_no"] += 1
        return None

    soglia_s = modello_trovato.get(
        "taglia_s_solo_sotto"
    )

    if (
        soglia_s is not None
        and taglia.upper() == "S"
        and prezzo >= soglia_s
    ):
        stats["taglia_no"] += 1
        return None

    # ------------------------------------------------------------
    # 12. PROFITTO
    # ------------------------------------------------------------

    profitto_netto, sell_riferimento = (
        calcola_profitto(
            modello_trovato,
            condizione,
            prezzo
        )
    )

    if (
        profitto_netto
        < modello_trovato["profit_min"]
    ):
        stats["profitto_basso"] += 1
        return None

    # ------------------------------------------------------------
    # 13. TIER
    # ------------------------------------------------------------

    tier = "ALERT"

    if (
        auto_buy_soglia is not None
        and prezzo <= auto_buy_soglia
    ):
        tier = "AUTO-BUY SIGNAL"

    # Stone Island
    if (
        modello_trovato["brand"]
        == "stone island"
        and prezzo < 30
        and si_manca_certilogo(descrizione)
    ):
        tier = "ALERT"

    # Taglie "extra" (es. Timberland 36-38): il documento le vuole SOLO se AUTO-BUY,
    # mai come semplice ALERT â prima questo campo era scritto nei dati ma non
    # controllato da nessuna parte (bug morto), ora blocca davvero
    taglie_extra = modello_trovato.get(
        "taglie_alert_extra", []
    )
    if (
        taglia.upper() in [str(t).upper() for t in taglie_extra]
        and tier != "AUTO-BUY SIGNAL"
    ):
        stats["taglia_no"] += 1
        return None

    # ------------------------------------------------------------
    # 14. FRESHNESS (giÃ  calcolata al punto 4b, riusata qui per lo score)
    # ------------------------------------------------------------

    # ------------------------------------------------------------
    # 15. SCORE
    # ------------------------------------------------------------

    cuori = safe_int(
        item.get("favourite_count", 0)
    )

    score = calcola_score(
        modello_trovato,
        condizione,
        prezzo,
        profitto_netto,
        cuori,
        taglia,
        seller_rischio,
        freshness
    )

    return {
        "modello": modello_trovato,
        "tier": tier,
        "score": score,
        "condizione": condizione,
        "prezzo": prezzo,
        "buy_max": buy_max,
        "auto_buy_soglia": auto_buy_soglia,
        "profitto_netto": profitto_netto,
        "sell_usato": sell_riferimento,
        "taglia": taglia,
        "titolo": titolo,
        "descrizione": descrizione,
        "cuori": cuori,
        "iid": str(item.get("id", "")),
        "url": (
            "https://www.vinted.it/items/"
            + str(item.get("id", ""))
        ),
        "foto": (
            (item.get("photo") or {})
            .get("url", "")
            or ""
        ),
        "seller_rischio": seller_rischio,
        "freshness": freshness,
    }


# ================================================================
# BLACKLIST
# ================================================================

def get_blacklist():
    pref = carica_pref()

    blacklist = []

    for data in pref.values():

        if not isinstance(data, dict):
            continue

        for titolo in data.get(
            "blacklist_titoli",
            []
        ):

            valore = normalizza(
                str(titolo)
            ).strip()

            if len(valore) >= 4:
                blacklist.append(valore)

    return list(set(blacklist))


def titolo_blacklistato(titolo, blacklist):
    tl = normalizza(titolo)

    return any(
        b in tl
        for b in blacklist
    )


# ================================================================
# NOTIFICA DISCORD
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

    freshness_txt = "n.d."

    if res["freshness"] is not None:
        freshness_txt = (
            f"{round(res['freshness'])} sec"
        )

    auto_buy = (
        f"{res['auto_buy_soglia']} EUR"
        if res["auto_buy_soglia"] is not None
        else "n.d."
    )

    extra = ""

    # A questo punto se la taglia Ã¨ tra le "extra" (es. Timberland 36-38) il tier
    # Ã¨ sempre AUTO-BUY (le ALERT su queste taglie sono giÃ  state scartate a monte)
    if str(res["taglia"]) in (
        modello.get(
            "taglie_alert_extra",
            []
        )
    ):
        extra += " | TAGLIA RICERCATA (36-38)"

    if res["seller_rischio"]:
        extra += (
            " | SELLER DA VERIFICARE"
        )

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
        f"{modello['sell_min']}-"
        f"{modello['sell_max']} EUR\n"
        f"**Profitto stimato:** "
        f"+{res['profitto_netto']:.2f} EUR\n"
        f"**Profitto minimo:** "
        f"{modello['profit_min']} EUR\n"
        f"**Cuori:** {res['cuori']}\n"
        f"**Freshness:** {freshness_txt}\n\n"
        f"Controlla sempre foto, etichette, "
        f"codici e autenticita' prima di comprare.\n\n"
        f"[VAI ALL'ANNUNCIO]({res['url']})"
    )

    embed = discord.Embed(
        title=titolo_embed,
        description=desc,
        color=colore,
    )

    if res.get("foto"):
        try:
            embed.set_image(
                url=res["foto"]
            )
        except Exception:
            pass

    try:
        await canale_notifiche.send(
            content=ping,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=True,
                roles=True,
                users=True
            )
        )

        return True

    except discord.HTTPException as exc:
        stats["notifiche_fallite"] += 1

        log.error(
            "Errore Discord invio: %s",
            exc
        )

        return False

    except Exception as exc:
        stats["notifiche_fallite"] += 1

        log.error(
            "Errore notifica: %s",
            exc
        )

        return False


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
# SCAN
# ================================================================

nuovi_dal_salvataggio = 0
cicli_dal_salvataggio = 0


async def scansione_query(
    session,
    query,
    blacklist
):
    global ultimo_affare
    global nuovi_dal_salvataggio

    encoded = urllib.parse.quote(
        query
    )

    url = (
        "https://www.vinted.it/api/v2/"
        "catalog/items"
        f"?search_text={encoded}"
        "&order=newest_first"
        "&per_page=20"
    )

    headers = {
        "User-Agent": random.choice(
            USER_AGENTS
        ),
        "Accept": "application/json",
        "Referer": "https://www.vinted.it/",
    }

    response = await vinted_get(
        session,
        url,
        headers
    )

    if response is None:
        return

    try:
        data = response.json()
    except ValueError:
        log.warning(
            "Risposta non JSON per query %s â primi 200 char: %s",
            query,
            response.text[:200].replace('\n', ' ')
        )
        return

    items = data.get(
        "items",
        []
    )

    if not isinstance(items, list):
        return

    for item in items:

        if not isinstance(item, dict):
            continue

        iid = str(
            item.get("id", "")
        )

        if not iid:
            continue

        if iid in gia_visti:
            stats["duplicati"] += 1
            continue

        gia_visti.add(iid)
        stats["scaricati"] += 1

        # --------------------------------------------------------
        # FRESHNESS
        # --------------------------------------------------------

        cts = (
            item.get("created_at_ts")
            or
            (item.get("photo") or {})
            .get("high_resolution", {})
            .get("timestamp")
        )

        freshness = None

        try:
            cts_val = float(cts)

            if cts_val > 1e10:
                cts_val /= 1000

            freshness = (
                time.time() - cts_val
            )

            if (
                freshness
                > FRESHNESS_CEILING
            ):
                continue

        except Exception:
            stats[
                "freshness_sconosciuto"
            ] += 1

        # --------------------------------------------------------
        # BLACKLIST
        # --------------------------------------------------------

        titolo = str(
            item.get(
                "title",
                ""
            ) or ""
        )

        if titolo_blacklistato(
            titolo,
            blacklist
        ):
            continue

        # --------------------------------------------------------
        # VALUTAZIONE
        # --------------------------------------------------------

        risultato = valuta_item(
            item
        )

        if not risultato:
            continue

        # --------------------------------------------------------
        # NOTIFICA
        # --------------------------------------------------------

        ultimo_affare = {
            "titolo": risultato["titolo"],
            "id": iid,
            "prezzo": risultato["prezzo"],
        }

        if (
            risultato["tier"]
            == "AUTO-BUY SIGNAL"
        ):
            stats["auto_buy"] += 1
        else:
            stats["alert"] += 1

        await invia_notifica(
            risultato
        )

        nuovi_dal_salvataggio += 1

        # Piccola pausa tra notifiche
        await asyncio.sleep(
            0.5
        )


# ================================================================
# LOOP PRINCIPALE
# ================================================================

@tasks.loop(seconds=10)
async def controllo_vinted():
    global rotazione_idx
    global cicli_dal_salvataggio
    global nuovi_dal_salvataggio

    # Adeguamento intervallo runtime: se !set scan_interval ha cambiato il valore,
    # aggiorniamo il loop (change_interval prende effetto dal ciclo successivo)
    try:
        nuovo_intervallo = int(cfg_runtime["scan_interval"])
        if controllo_vinted.seconds != nuovo_intervallo:
            controllo_vinted.change_interval(seconds=nuovo_intervallo)
    except Exception:
        pass

    if canale_notifiche is None:
        return

    session = get_session()

    blacklist = get_blacklist()

    secondarie = [
        QUERY_SECONDARIE[
            (rotazione_idx + i)
            % len(QUERY_SECONDARIE)
        ]
        for i in range(2)
    ]

    rotazione_idx = (
        rotazione_idx + 2
    ) % len(QUERY_SECONDARIE)

    queries = (
        QUERY_FISSE
        + secondarie
    )

    log.info(
        "Nuovo ciclo: %s query",
        len(queries)
    )

    for query in queries:

        try:
            await scansione_query(
                session,
                query,
                blacklist
            )

        except Exception as exc:
            log.exception(
                "Errore query '%s': %s",
                query,
                exc
            )

        # Evita raffiche di richieste
        await asyncio.sleep(
            random.uniform(
                1.0,
                1.8
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
        "Ciclo completato | visti=%s",
        len(gia_visti)
    )


# ================================================================
# ERROR HANDLER LOOP
# ================================================================

@controllo_vinted.error
async def controllo_vinted_error(error):
    log.exception(
        "Errore nel loop scanner: %s",
        error
    )

    await asyncio.sleep(10)

    if not controllo_vinted.is_running():
        controllo_vinted.restart()


# ================================================================
# REPORT
# ================================================================

@tasks.loop(minutes=10)
async def report_periodico():

    if canale_notifiche is None:
        return

    try:
        r = (
            "DEBUG 10 min\n"
            "Scaricati: {scaricati}\n"
            "ALERT: {alert}\n"
            "AUTO-BUY: {auto_buy}\n"
            "Brand no: {brand_no}\n"
            "Modello no: {modello_no}\n"
            "Difetti: {escluso_difetto}\n"
            "Stile: {escluso_stile}\n"
            "Condizione no: {condizione_no}\n"
            "Taglia no: {taglia_no}\n"
            "Bambino: {bambino}\n"
            "Seller rischio: {seller_rischio}\n"
            "Profitto basso: {profitto_basso}\n"
            "Freshness sconosciuto: "
            "{freshness_sconosciuto}\n"
            "Freshness scaduta (per-modello): "
            "{freshness_no}\n"
            "Duplicati: {duplicati}\n"
            "Rate limit: {rate_limit}\n"
            "Errori HTTP: {errori_http}\n"
            "Notifiche fallite: "
            "{notifiche_fallite}\n"
            "Visti totali: "
            f"{len(gia_visti)}"
        ).format(**stats)

        await canale_notifiche.send(
            f"```text\n{r}\n```"
        )

        stats.clear()
        stats.update(
            nuove_stats()
        )

    except Exception as exc:
        log.warning(
            "Errore report: %s",
            exc
        )


# ================================================================
# STATS TESTUALE
# ================================================================

def riga_stats():
    s = stats

    return (
        f"Scaricati: {s['scaricati']} | "
        f"ALERT: {s['alert']} | "
        f"AUTO-BUY: {s['auto_buy']}\n"
        f"Brand no: {s['brand_no']} | "
        f"Modello no: {s['modello_no']} | "
        f"Difetti: {s['escluso_difetto']}\n"
        f"Stile: {s['escluso_stile']} | "
        f"Condizione: {s['condizione_no']} | "
        f"Taglia: {s['taglia_no']}\n"
        f"Bambino: {s['bambino']} | "
        f"Seller rischio: {s['seller_rischio']}\n"
        f"Profitto basso: {s['profitto_basso']} | "
        f"Rate limit: {s['rate_limit']}\n"
        f"Freshness sconosciuto: "
        f"{s['freshness_sconosciuto']}\n"
        f"Visti: {len(gia_visti)}"
    )


# ================================================================
# DISCORD EVENTS
# ================================================================

@bot.event
async def on_ready():
    global canale_notifiche

    log.info(
        "Bot online: %s",
        bot.user
    )

    log.info(
        "Modelli configurati: %s",
        len(MODELLI)
    )

    canale_notifiche = trova_canale()

    if canale_notifiche:
        log.info(
            "Canale notifiche: #%s",
            getattr(
                canale_notifiche,
                "name",
                "n.d."
            )
        )
    else:
        log.warning(
            "Nessun canale notifiche trovato"
        )

    if not controllo_vinted.is_running():
        controllo_vinted.start()

    if not report_periodico.is_running():
        report_periodico.start()


# ================================================================
# COMMANDS
# ================================================================

@bot.command()
async def ping(ctx):
    await ctx.send(
        "Pong. Bot attivo."
    )


@bot.command(name="stats")
async def cmd_stats(ctx):
    await ctx.send(
        riga_stats()
    )


@bot.command()
async def config(ctx):
    await ctx.send(
        "Configurazione:\n"
        f"trattativa = "
        f"{cfg_runtime['trattativa']}\n"
        f"freshness = "
        f"{cfg_runtime['max_secondi_freschezza']} sec\n"
        f"scan interval = "
        f"{cfg_runtime['scan_interval']} sec\n"
        f"modelli = "
        f"{len(MODELLI)}"
    )


@bot.command(name="set")
async def cmd_set(
    ctx,
    chiave: str = "",
    valore: str = ""
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
            "Uso: !set "
            "<chiave> <valore>"
        )
        return

    try:

        if chiave == "trattativa":
            nuovo_valore = float(
                valore
            )

            if not 0.5 <= nuovo_valore <= 1:
                raise ValueError

        else:
            nuovo_valore = int(
                valore
            )

            if nuovo_valore < 1:
                raise ValueError

        cfg_runtime[chiave] = nuovo_valore

        await ctx.send(
            f"OK: {chiave} = "
            f"{nuovo_valore}"
        )

    except ValueError:
        await ctx.send(
            "Valore non valido."
        )


@bot.command()
async def modelli(ctx):

    righe = []

    for modello in MODELLI:
        righe.append(
            f"- {modello['nome']} | "
            f"SELL "
            f"{modello['sell_min']}-"
            f"{modello['sell_max']} EUR | "
            f"MIN +"
            f"{modello['profit_min']} EUR"
        )

    testo = (
        "Modelli attivi "
        f"({len(MODELLI)}):\n"
        + "\n".join(righe)
    )

    # Discord limite 2000 caratteri
    if len(testo) <= 1900:
        await ctx.send(testo)
        return

    blocco = "Modelli attivi:\n"

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
        f"Prezzo: "
        f"{ultimo_affare['prezzo']} EUR\n"
        f"ID: {ultimo_affare['id']}"
    )


@bot.command()
async def resetstats(ctx):

    stats.clear()
    stats.update(
        nuove_stats()
    )

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
        "`!resetstats` - reset statistiche"
    )


# ================================================================
# APPRENDIMENTO BLACKLIST
# ================================================================

@bot.event
async def on_message(message):

    global ultimo_affare

    if message.author == bot.user:
        return

    msg_norm = normalizza(
        message.content
    )

    segnali_negativi = [
        "non e un affare",
        "bidonata",
        "bidone",
    ]

    if any(
        x in msg_norm
        for x in segnali_negativi
    ):

        if ultimo_affare:

            pref = carica_pref()

            uid = str(
                message.author.id
            )

            if uid not in pref:
                pref[uid] = {
                    "blacklist_titoli": []
                }

            lista = pref[uid].setdefault(
                "blacklist_titoli",
                []
            )

            titolo = normalizza(
                ultimo_affare.get(
                    "titolo",
                    ""
                )
            )[:100]

            if (
                titolo
                and titolo not in lista
            ):
                lista.append(titolo)

            # massimo 200 titoli per utente
            pref[uid][
                "blacklist_titoli"
            ] = lista[-200:]

            salva_pref(pref)

            await message.channel.send(
                "Blacklistato: "
                + ultimo_affare.get(
                    "titolo",
                    ""
                )[:80]
            )

    await bot.process_commands(
        message
    )


# ================================================================
# FLASK HEALTH CHECK
# ================================================================

app = Flask(__name__)


@app.route("/")
def home():
    return (
        "Vinted Resell Bot V5 online",
        200
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "bot_ready": bot.is_ready(),
        "models": len(MODELLI),
        "seen_items": len(gia_visti),
        "scan_interval": cfg_runtime[
            "scan_interval"
        ],
    }), 200


def avvia_flask():
    try:
        port = int(
            os.getenv(
                "PORT",
                "10000"
            )
        )

        app.run(
            host="0.0.0.0",
            port=port
        )

    except Exception as exc:
        log.error(
            "Flask terminato: %s",
            exc
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
        daemon=True
    ).start()

    log.info(
        "Avvio Vinted Resell Bot V5..."
    )

    bot.run(TOKEN)


if __name__ == "__main__":
    main()

