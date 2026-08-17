# 🔥 VINTED SNIPER BOT V25 - ANTI-BIDONATA 4 CORREZIONI
import discord, asyncio, requests, json, os, re, time, random, threading, datetime
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE="filtri.json"; CONFIG_FILE="config.json"; CHAT_FILE="chat_storico.json"; VISTI_FILE="gia_visti.json"
PREF_FILE="preferenze_utenti.json"
gia_visti=set(); vinted_session=None; last_session_refresh=0
USER_AGENTS=["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"]

regole = [
  {"brand": "polo ralph lauren", "cat": "maglione", "models": ["cable knit", "bear", "quarter zip", "cricket", "pony"], "colori_no": ["giallo fluo", "rosa fluo", "arancio fluo", "verde fluo", "fluo"], "colori_ok": ["navy", "blu navy", "beige", "crema", "bianco", "nero", "burgundy", "verde", "grigio"], "buy_max": 25, "sell_min": 40, "sell_max": 55, "basta_brand": False},
  {"brand": "polo ralph lauren", "cat": "felpa", "models": ["bear", "big pony", "crest", "rl 67", "knit"], "colori_no": ["giallo fluo", "rosa fluo", "fluo"], "colori_ok": ["navy", "nero", "grigio", "bianco", "beige", "burgundy"], "buy_max": 25, "sell_min": 40, "sell_max": 55, "basta_brand": False},
  {"brand": "polo ralph lauren", "cat": "giubbotto", "models": ["harrington", "windbreaker", "overshirt", "puffer", "corduroy"], "colori_no": ["fluo"], "colori_ok": ["navy", "beige", "nero", "verde"], "buy_max": 40, "sell_min": 75, "sell_max": 100, "basta_brand": False},
  {"brand": "polo ralph lauren", "cat": "t-shirt", "models": ["bear", "big pony"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero", "navy"], "buy_max": 5, "sell_min": 10, "sell_max": 16, "basta_brand": False, "big_logo_only": True},
  {"brand": "tommy hilfiger", "cat": "maglione", "models": ["flag", "crest", "tommy jeans", "spellout"], "colori_no": ["fluo"], "colori_ok": ["navy", "rosso", "bianco", "grigio", "beige", "blu"], "buy_max": 20, "sell_min": 35, "sell_max": 50, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "felpa", "models": ["flag", "crest", "tommy jeans", "spellout", "big flag"], "colori_no": ["fluo"], "colori_ok": ["navy", "grigio", "nero", "bianco", "royal"], "buy_max": 20, "sell_min": 35, "sell_max": 50, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "giubbotto", "models": ["sailing", "coach", "puffer", "flag"], "colori_no": ["fluo"], "colori_ok": ["navy", "nero", "rosso", "blu"], "buy_max": 35, "sell_min": 60, "sell_max": 85, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "t-shirt", "models": ["big flag"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero", "navy"], "buy_max": 5, "sell_min": 10, "sell_max": 16, "basta_brand": False, "big_logo_only": True},
  {"brand": "carhartt", "cat": "felpa", "models": ["chase", "og active", "american script", "script"], "colori_no": ["rosa fluo", "giallo fluo", "fluo", "rosa chiaro"], "colori_ok": ["nero", "hamilton brown", "marrone", "navy", "grigio", "verde", "olive"], "buy_max": 30, "sell_min": 50, "sell_max": 70, "basta_brand": False},
  {"brand": "carhartt", "cat": "giubbotto", "models": ["og active jacket", "detroit jacket", "michigan coat", "detroit", "michigan", "active jacket"], "colori_no": ["fluo"], "colori_ok": ["hamilton brown", "marrone", "nero", "verde", "camo", "blu"], "buy_max": 40, "sell_min": 80, "sell_max": 110, "basta_brand": False},
  {"brand": "carhartt", "cat": "maglione", "models": ["chase", "script"], "colori_no": ["fluo"], "colori_ok": ["nero", "grigio", "navy"], "buy_max": 25, "sell_min": 40, "sell_max": 55, "basta_brand": False},
  {"brand": "north face", "cat": "felpa", "models": ["denali", "retro", "1995", "1990 mountain", "fleece"], "colori_no": ["fluo"], "colori_ok": ["nero", "beige", "khaki", "giallo", "blu", "rosso"], "buy_max": 30, "sell_min": 60, "sell_max": 85, "basta_brand": False},
  {"brand": "north face", "cat": "giubbotto", "models": ["nuptse", "1996", "1990 mountain", "denali", "gore-tex", "mountain jacket"], "colori_no": ["fluo"], "colori_ok": ["nero", "beige", "giallo", "blu"], "buy_max": 45, "sell_min": 85, "sell_max": 120, "basta_brand": False},
  {"brand": "levi's", "cat": "giubbotto", "models": ["trucker", "type 3", "sherpa", "denim jacket"], "colori_no": ["fluo"], "colori_ok": ["denim", "blu", "nero", "chiaro"], "buy_max": 30, "sell_min": 50, "sell_max": 75, "basta_brand": False},
  {"brand": "levi's", "cat": "t-shirt", "models": ["batwing big", "big batwing"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero"], "buy_max": 5, "sell_min": 10, "sell_max": 16, "basta_brand": False, "big_logo_only": True},
  {"brand": "levi's", "cat": "shorts", "models": ["505", "501", "short", "bermuda", "denim short"], "colori_no": ["fluo"], "colori_ok": ["denim", "blu", "nero", "chiaro"], "buy_max": 10, "sell_min": 20, "sell_max": 26, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "shorts", "models": ["short", "bermuda", "jeans short", "denim short"], "colori_no": ["fluo"], "colori_ok": ["blu", "nero", "beige", "chiaro"], "buy_max": 10, "sell_min": 20, "sell_max": 26, "basta_brand": False},
  {"brand": "nike", "cat": "felpa", "models": ["center swoosh", "big swoosh", "spellout", "90s", "vintage"], "colori_no": ["fluo"], "colori_ok": ["grigio", "nero", "navy", "bianco", "blu"], "buy_max": 25, "sell_min": 35, "sell_max": 50, "basta_brand": False},
  {"brand": "nike", "cat": "giubbotto", "models": ["windrunner", "track jacket", "puffer"], "colori_no": ["fluo"], "colori_ok": ["nero", "navy", "grigio"], "buy_max": 30, "sell_min": 55, "sell_max": 80, "basta_brand": False},
  {"brand": "nike", "cat": "t-shirt", "models": ["center swoosh", "big swoosh 90s"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero", "grigio"], "buy_max": 5, "sell_min": 10, "sell_max": 16, "basta_brand": False, "big_logo_only": True},
  {"brand": "nike", "cat": "shorts", "models": ["short", "bermuda", "elite", "vaquero", "basket short"], "colori_no": ["fluo"], "colori_ok": ["nero", "blu", "grigio", "bianco"], "buy_max": 10, "sell_min": 18, "sell_max": 26, "basta_brand": False},
]

TAGLIE_OK = ["S","M","L","XL","S/M","M/L","L/XL","S - M","M - L","S - L"]
COND_OK = ["nuovo con etichette","nuovo senza etichette","nuovo","ottime","molto buono","very good","ottimo","eccellente","excellent","buone","buono","good","discrete"]
BAMBINO_PATTERN = re.compile(r'(\b\d{1,2}\s*anni\b|\b\d{1,2}Y\b|\b\d{3}cm\b|kinder|junior|\b12A\b|\b14A\b)', re.I)
SHORTS_KEYWORDS = ["short", "bermuda", "vaquero", "elite"]
BIG_LOGO_TSHIRT = ["big pony", "big flag", "bear", "center swoosh", "big logo", "big swoosh"]

app=Flask(__name__)
@app.route("/")
def home(): return "Bot V25 ANTI-BIDONATA"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def carica_config():
    default={"spedizione":5,"max_secondi_freschezza":120}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE,"r") as f: cfg=json.load(f); default.update(cfg); return default
        except: return default
    return default
def carica_visti():
    global gia_visti
    if os.path.exists(VISTI_FILE):
        try:
            with open(VISTI_FILE,"r") as f: gia_visti=set(json.load(f))
        except: gia_visti=set()
def salva_visti():
    try:
        with open(VISTI_FILE,"w") as f: json.dump(list(gia_visti)[-5000:],f)
    except: pass
def get_session():
    global vinted_session, last_session_refresh
    now=time.time()
    if vinted_session is None or (now-last_session_refresh)>300:
        vinted_session=requests.Session()
        try:
            vinted_session.get("https://www.vinted.it",headers={"User-Agent":USER_AGENTS[0]},timeout=10)
            last_session_refresh=now
        except: pass
    return vinted_session
def condizione_ok(s): return any(c in s.lower() for c in COND_OK) if s else False
def taglia_ok(s):
    if not s: return False
    st=s.strip().upper()
    if st in TAGLIE_OK or st in ["S","M","L","XL"]: return True
    if st in ["XXL","XS","XXS","XXXL"] or "XXL" in st or "XXXL" in st: return False
    return any(x in st for x in ["S","M","L","XL"])
def is_bambino(size_title, titolo, descrizione):
    testo = f"{size_title} {titolo} {descrizione}".lower()
    return bool(BAMBINO_PATTERN.search(testo) or re.search(r'\b1[2-5]\d\s*cm\b', testo))
def is_shorts(titolo, descrizione):
    return any(k in f"{titolo} {descrizione}".lower() for k in SHORTS_KEYWORDS)
def has_big_logo(titolo, descrizione):
    return any(k in f"{titolo} {descrizione}".lower() for k in BIG_LOGO_TSHIRT)

def matches_curated(titolo, brand_title, descrizione, prezzo, size_title, status):
    tlow = (titolo+" "+brand_title).lower()
    dlow = (descrizione or "").lower()
    testo_completo = tlow+" "+dlow
    if not taglia_ok(size_title) or not condizione_ok(status): return None
    bambino = is_bambino(size_title, titolo, descrizione)
    shorts = is_shorts(titolo, descrizione)
    for rule in regole:
        b=rule["brand"]
        if b not in tlow and b.split()[0] not in tlow:
            if not (b=="polo ralph lauren" and "ralph lauren" in tlow):
                if not (b=="north face" and "north face" in tlow):
                    if not (b=="levi's" and "levi" in tlow): continue
        if shorts:
            if rule["cat"]!="shorts": continue
        else:
            if rule["cat"]=="shorts": continue
        if rule["cat"]=="t-shirt":
            if not has_big_logo(titolo, descrizione): continue
        if not rule.get("basta_brand"):
            if not any(m in testo_completo for m in rule["models"]): continue
        if any(cn in testo_completo for cn in rule["colori_no"] if cn): continue
        if prezzo>rule["buy_max"]: continue
        rc=dict(rule)
        if bambino:
            rc["sell_min"]=15; rc["sell_max"]=22; rc["is_bambino"]=True
        else: rc["is_bambino"]=False
        if "cropped" in testo_completo and "xs" in (size_title or "").lower():
            rc["sell_min"]=18; rc["sell_max"]=25
        rc["has_color_ok"]=any(co in testo_completo for co in rule["colori_ok"]) if rule["colori_ok"] else True
        rc["bambino"]=bambino; rc["shorts"]=shorts
        rc["color_source"]="titolo" if any(co in tlow for co in rule["colori_ok"]) else "descrizione" if any(co in dlow for co in rule["colori_ok"]) else "foto"
        return rc
    return None

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V25 ANTI-BIDONATA online {bot.user} | Regole {len(regole)}")
    if not controllo_vinted.is_running(): controllo_vinted.start()
@bot.command()
async def config(ctx):
    await ctx.send(f"V25 ANTI-BIDONATA | Regole {len(regole)} | 4 correzioni attive")

@tasks.loop(seconds=3.5)
async def controllo_vinted():
    global ultimo_affare
    try:
        cfg=carica_config(); sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        max_fresco=cfg.get("max_secondi_freschezza",120)
        brands=list(set([r["brand"] for r in regole]))
        urls=[f"https://www.vinted.it/api/v2/catalog/items?search_text={b.replace(' ','%20')}&order=newest_first&per_page=25" for b in brands][:12]
        for url in urls:
            try:
                r=sess.get(url,headers=headers,timeout=12)
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    cts=item.get("created_at_ts")
                    if cts and time.time()-float(cts)>max_fresco:
                        gia_visti.add(iid); continue
                    gia_visti.add(iid)
                    titolo=item.get("title",""); brand=item.get("brand_title",""); cond=item.get("status",""); size=item.get("size_title","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if prezzo<2 or prezzo>120: continue
                    descrizione=item.get("description","")
                    if not matches_curated(titolo,brand,"",prezzo,size,cond): continue
                    if not descrizione:
                        try:
                            det=sess.get(f"https://www.vinted.it/api/v2/items/{iid}",headers=headers,timeout=8)
                            if det.status_code==200: descrizione=det.json().get("item",{}).get("description","")
                            await asyncio.sleep(0.4)
                        except: descrizione=""
                    rule=matches_curated(titolo,brand,descrizione,prezzo,size,cond)
                    if not rule: continue
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url",""); cuori=item.get("favourite_count",0) or 0
                    try:
                        sec=int(time.time()-float(item.get("created_at_ts",time.time())))
                        pub=f"{sec}s fa" if sec<60 else f"{sec//60}m fa"
                    except: pub="ora"
                    if rule.get("bambino"): emoji="🧒"; sell_txt=f"{rule['sell_min']}-{rule['sell_max']}€ BAMBINO"
                    elif rule.get("shorts"): emoji="🩳"; sell_txt=f"{rule['sell_min']}-{rule['sell_max']}€ SHORTS"
                    else: emoji="🔥"; sell_txt=f"{rule['sell_min']}-{rule['sell_max']}€"
                    color_note=f"🎨 {rule['color_source']}" if rule.get("has_color_ok") else "🎨 verifica foto"
                    titolo_embed=f"{emoji} {rule['brand'].upper()} {rule['cat'].upper()} | {titolo[:40]} | {prezzo}€ -> {sell_txt}"
                    desc=f"🔥 **V25 ANTI-BIDONATA** 🔥\n{titolo}\n\nBrand: {brand}\nModello: {rule['cat']} | {'BAMBINO' if rule.get('bambino') else 'SHORTS' if rule.get('shorts') else 'ok'}\nTaglia: {size} {'🧒 BAMBINO' if rule.get('bambino') else '✅'}\nCond: {cond}\n{color_note}\n⏱️ {pub} | ❤️ {cuori}\n💰 BUY max {rule['buy_max']}€ | Prezzo: {prezzo}€\n💸 SELL {sell_txt}\n[🚀 PRENDI]({link})"
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        emb=discord.Embed(title=titolo_embed,description=desc,color=0x00ff88 if rule.get("bambino") or rule.get("shorts") else 0x9b59b6)
                        if foto: emb.set_image(url=foto)
                        ping="" if (rule.get("bambino") or rule.get("shorts") or rule["sell_max"]<=26) else "@here 🔥"
                        await canale.send(content=ping,embed=emb)
                if len(gia_visti)%30==0: salva_visti()
                await asyncio.sleep(0.5)
            except: continue
        salva_visti()
    except Exception as e: print(f"Errore {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        bot.run(tok)
