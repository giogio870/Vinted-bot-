# 🔥 VINTED SNIPER BOT V7.0 FINAL — UNICO FAIL + RICERCATO + PROFIT TRACKER + MULTI-PIATTAFORMA — FIXED UTF-8
#
# COSA FA:
# 1. Scansiona Vinted 24/7, ti allerta solo se netto >= 16€ (UNICO FAIL) 💧💥🔴🟣
# 2. RICERCATO: anche 1 solo annuncio con 15+ like → ti allerta 🔥
# 3. SELL-THROUGH RATE: conta venduti vs attivi = sa se vende veloce ⚡
# 4. MULTI-PIATTAFORMA: confronta prezzi anche su eBay (opzionale, gratis)
# 5. PROFIT TRACKER: !comprato link prezzo → !rivendi link → !venduto prezzo → !portafoglio
# 6. 24H ALERT: non si ferma mai
#
# Deploy: env vars DISCORD_TOKEN (obbligatorio) + EBAY_APP_ID (opzionale)
# pip install discord.py requests Pillow flask

import discord
from discord.ext import commands, tasks
import requests, statistics, json, os, io, re, time, random, threading, hashlib
from PIL import Image, ImageEnhance, ImageStat
import datetime
from statistics import median, mean, stdev
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.dm_messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE = "filtri.json"
CONFIG_FILE = "config.json"
VISTI_FILE = "gia_visti.json"
PORTAFOGLIO_FILE = "portafoglio.json"

gia_visti = set()
cache_mercato = {}
vinted_session = None
last_session_refresh = 0
last_photo_per_user = {}

BRANDS_BUDGET = ["lacoste","ralph lauren","dsquared","dsquared2","tommy hilfiger","fred perry","stone island","pokemon","charizard","psa","pikachu","nike","jordan","balenciaga","runner","dunk","polo"]
TUTTI = list(set(BRANDS_BUDGET))

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
]

app = Flask(__name__)
@app.route("/")
def home():
    return "Bot V7.0 FINAL — UNICO FAIL + RICERCATO + PROFIT TRACKER + MULTI-PIATTAFORMA — 24H ALERT"
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
threading.Thread(target=run_flask, daemon=True).start()

def get_session():
    global vinted_session, last_session_refresh
    now = time.time()
    if vinted_session is None or (now - last_session_refresh) > 600:
        vinted_session = requests.Session()
        try:
            vinted_session.get("https://www.vinted.it", headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
            last_session_refresh = now
        except:
            pass
    return vinted_session

def carica_config():
    default = {
        "guadagno_min_netto_base": 16,
        "guadagno_min_netto_ideale": 18,
        "guadagno_mostro": 22,
        "guadagno_super_mostro": 30,
        "min_like_ricercato": 15,
        "min_confidence": 50,
        "spedizione": 5,
        "scan_brands": ["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","psa 10","nike dunk","jordan 1","balenciaga runner"],
        "user_brands": ["lacoste","ralph lauren","dsquared","dsquared2","stone island","pokemon","charizard","nike","jordan"],
        "max_price_per_brand": {"lacoste":35,"ralph lauren":40,"dsquared":60,"dsquared2":60,"stone island":100,"pokemon":150,"charizard":200,"psa 10":300,"nike dunk":80,"jordan 1":100},
        "enable_ebay": True,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE,"r") as f:
                cfg=json.load(f)
                default.update(cfg)
                return default
        except:
            return default
    return default

def carica_filtri():
    if os.path.exists(FILTRI_FILE):
        try:
            with open(FILTRI_FILE,"r") as f:
                return json.load(f)
        except:
            return []
    return []

def carica_visti():
    global gia_visti
    if os.path.exists(VISTI_FILE):
        try:
            with open(VISTI_FILE,"r") as f:
                gia_visti=set(json.load(f))
        except:
            gia_visti=set()

def salva_visti():
    try:
        with open(VISTI_FILE,"w") as f:
            json
