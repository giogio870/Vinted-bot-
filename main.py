# 🔥 VINTED SNIPER BOT V24 - CURATED PERFECT + BASTA_BRAND + S + DESC
import discord, asyncio, requests, json, os, re, time, random, threading, datetime
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE="filtri.json"; CONFIG_FILE="config.json"; CHAT_FILE="chat_storico.json"; VISTI_FILE="gia_visti.json"
PREF_FILE="preferenze_utenti.json"
gia_visti=set(); vinted_session=None; last_session_refresh=0; ultimo_affare=None
USER_AGENTS=["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"]

# ================= REGOLE FINALI - TUE =================
regole = [
  {"brand": "polo ralph lauren", "cat": "maglione", "models": ["cable knit", "bear", "quarter zip", "cricket", "pony"], "colori_no": ["giallo fluo", "rosa fluo", "arancio fluo", "verde fluo", "fluo"], "colori_ok": ["navy", "blu navy", "beige", "crema", "bianco", "nero", "burgundy", "verde", "grigio"], "buy_max": 25, "sell_min": 50, "sell_max": 70, "basta_brand": False},
  {"brand": "polo ralph lauren", "cat": "felpa", "models": ["bear", "big pony", "crest", "rl 67", "knit"], "colori_no": ["giallo fluo", "rosa fluo", "fluo"], "colori_ok": ["navy", "nero", "grigio", "bianco", "beige", "burgundy"], "buy_max": 25, "sell_min": 45, "sell_max": 65, "basta_brand": False},
  {"brand": "polo ralph lauren", "cat": "giubbotto", "models": ["harrington", "windbreaker", "overshirt", "puffer", "corduroy"], "colori_no": ["fluo"], "colori_ok": ["navy", "beige", "nero", "verde"], "buy_max": 40, "sell_min": 75, "sell_max": 100, "basta_brand": False},
  {"brand": "polo ralph lauren", "cat": "t-shirt", "models": ["bear", "pony"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero", "navy"], "buy_max": 12, "sell_min": 25, "sell_max": 35, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "maglione", "models": ["flag", "crest", "tommy jeans", "spellout"], "colori_no": ["fluo"], "colori_ok": ["navy", "rosso", "bianco", "grigio", "beige", "blu"], "buy_max": 20, "sell_min": 40, "sell_max": 55, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "felpa", "models": ["flag", "crest", "tommy jeans", "spellout", "big flag"], "colori_no": ["fluo"], "colori_ok": ["navy", "grigio", "nero", "bianco", "royal"], "buy_max": 20, "sell_min": 40, "sell_max": 55, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "giubbotto", "models": ["sailing", "coach", "puffer", "flag"], "colori_no": ["fluo"], "colori_ok": ["navy", "nero", "rosso", "blu"], "buy_max": 35, "sell_min": 65, "sell_max": 90, "basta_brand": False},
  {"brand": "tommy hilfiger", "cat": "t-shirt", "models": ["flag", "tommy jeans"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero", "navy"], "buy_max": 10, "sell_min": 25, "sell_max": 35, "basta_brand": True},
  {"brand": "carhartt", "cat": "felpa", "models": ["chase", "og active", "american script", "script"], "colori_no": ["rosa fluo", "giallo fluo", "fluo", "rosa chiaro"], "colori_ok": ["nero", "hamilton brown", "marrone", "navy", "grigio", "verde", "olive"], "buy_max": 30, "sell_min": 55, "sell_max": 75, "basta_brand": False},
  {"brand": "carhartt", "cat": "giubbotto", "models": ["og active jacket", "detroit jacket", "michigan coat", "detroit", "michigan", "active jacket"], "colori_no": ["fluo"], "colori_ok": ["hamilton brown", "marrone", "nero", "verde", "camo", "blu"], "buy_max": 40, "sell_min": 80, "sell_max": 110, "basta_brand": False},
  {"brand": "carhartt", "cat": "maglione", "models": ["chase", "script"], "colori_no": ["fluo"], "colori_ok": ["nero", "grigio", "navy"], "buy_max": 25, "sell_min": 45, "sell_max": 60, "basta_brand": False},
  {"brand": "north face", "cat": "felpa", "models": ["denali", "retro", "1995", "1990 mountain", "fleece"], "colori_no": ["fluo"], "colori_ok": ["nero", "beige", "khaki", "giallo", "blu", "rosso"], "buy_max": 35, "sell_min": 70, "sell_max": 95, "basta_brand": False},
  {"brand": "north face", "cat": "giubbotto", "models": ["nuptse", "1996", "1990 mountain", "denali", "gore-tex", "mountain jacket"], "colori_no": ["fluo"], "colori_ok": ["nero", "beige", "giallo", "blu"], "buy_max": 45, "sell_min": 85, "sell_max": 120, "basta_brand": False},
  {"brand": "levi's", "cat": "giubbotto", "models": ["trucker", "type 3", "sherpa", "denim jacket"], "colori_no": ["fluo"], "colori_ok": ["denim", "blu", "nero", "chiaro"], "buy_max": 30, "sell_min": 55, "sell_max": 80, "basta_brand": False},
  {"brand": "levi's", "cat": "t-shirt", "models": ["batwing", "red tab"], "colori_no": ["fluo"], "colori_ok": ["bianco", "nero"], "buy_max": 8, "sell_min": 22, "sell_max": 30, "basta_brand": True},
  {"brand": "nike", "cat": "felpa", "models": ["center swoosh", "swoosh", "spellout", "windrunner", "big swoosh", "90s", "vintage"], "colori_no": ["fluo"], "colori_ok": ["grigio", "nero", "navy", "bianco", "blu"], "buy_max": 25, "sell_min": 45, "sell_max": 65, "basta_brand": False},
  {"brand": "nike", "cat": "giubbotto", "models": ["windrunner", "track jacket", "puffer", "swoosh"], "colori_no": ["fluo"], "colori_ok": ["nero", "navy", "grigio"], "buy_max": 30, "sell_min": 60, "sell_max": 85, "basta_brand": False},
]

TAGLIE_OK = ["S","M","L","XL","S/M","M/L","L/XL","S - M","M - L","S - L"]
COND_OK = ["nuovo con etichette","nuovo senza etichette","nuovo","ottime","molto buono","very good","ottimo","eccellente","excellent","buone","buono","good","discrete"]

app=Flask(__name__)
@app.route("/")
def home(): return "Bot V24 PERFECT"
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
def condizione_ok(status):
    s=status.lower().strip()
    if not s: return False
    return any(c in s for c in COND_OK)
def taglia_ok(size_title):
    if not size_title: return False
    st=size_title.strip().upper()
    if st in TAGLIE_OK: return True
    if st in ["S","M","L","XL"]: return True
    if st in ["XXL","XS","XXS","XXXL"]: return False
    if "XXL" in st or "XXXL" in st: return False
    if any(x in st for x in ["S","M","L","XL"]): return True
    return False

def matches_curated(titolo, brand_title, descrizione, prezzo, size_title, status):
    tlow = (titolo+" "+brand_title).lower()
    dlow = (descrizione or "").lower()
    testo_completo = tlow + " " + dlow
    if not taglia_ok(size_title): return None
    if not condizione_ok(status): return None
    for rule in regole:
        b = rule["brand"]
        if b not in tlow and b.split()[0] not in tlow:
            if not (b=="polo ralph lauren" and "ralph lauren" in tlow):
                if not (b=="north face" and "north face" in tlow):
                    if not (b=="levi's" and "levi" in tlow):
                        continue
        # MODELLO OBBLIGATORIO a meno che basta_brand=True
        if not rule.get("basta_brand"):
            if not any(m in testo_completo for m in rule["models"]):
                continue
        # Se basta_brand=True, salta il check modello (basta brand+logo)
        # Colori NO -> scarta subito ovunque
        if any(cn in testo_completo for cn in rule["colori_no"] if cn):
            continue
        # Prezzo > buy_max -> scarta
        if prezzo > rule["buy_max"]:
            continue
        # Colore OK: se non trovato, manda lo stesso con nota
        has_color_ok = any(co in testo_completo for co in rule["colori_ok"]) if rule["colori_ok"] else True
        rc = dict(rule)
        rc["has_color_ok"] = has_color_ok
        rc["color_source"] = "titolo" if any(co in tlow for co in rule["colori_ok"]) else "descrizione" if any(co in dlow for co in rule["colori_ok"]) else "foto"
        return rc
    return None

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V24 PERFECT online {bot.user} | Regole {len(regole)}")
    if not controllo_vinted.is_running(): controllo_vinted.start()

@bot.command()
async def config(ctx):
    await ctx.send(f"V24 PERFECT | Regole {len(regole)} | S/M/L/XL | Titolo+Desc")

@tasks.loop(seconds=3.5)
async def controllo_vinted():
    global ultimo_affare
    try:
        cfg=carica_config(); sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        max_fresco=cfg.get("max_secondi_freschezza",120)
        brands = list(set([r["brand"] for r in regole]))
        urls=[]
        for brand in brands:
            bq=brand.replace(" ","%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={bq}&order=newest_first&per_page=25")
        urls=list(dict.fromkeys(urls))[:12]
        for url in urls:
            try:
                r=sess.get(url,headers=headers,timeout=12)
                if r.status_code==429: await asyncio.sleep(5); continue
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    cts=item.get("created_at_ts")
                    if cts:
                        try:
                            if time.time()-float(cts) > max_fresco:
                                gia_visti.add(iid); continue
                        except: pass
                    gia_visti.add(iid)
                    titolo=item.get("title",""); brand=item.get("brand_title",""); cond=item.get("status",""); size=item.get("size_title","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if prezzo<3 or prezzo>100: continue
                    descrizione = item.get("description","")
                    rule_temp = matches_curated(titolo, brand, "", prezzo, size, cond)
                    if not rule_temp: continue
                    # Se manca colore OK, fetch descrizione vera
                    if not descrizione:
                        try:
                            det = sess.get(f"https://www.vinted.it/api/v2/items/{iid}", headers=headers, timeout=8)
                            if det.status_code==200:
                                descrizione = det.json().get("item",{}).get("description","")
                                await asyncio.sleep(0.4)
                        except:
                            descrizione = ""
                    rule = matches_curated(titolo, brand, descrizione, prezzo, size, cond)
                    if not rule: continue
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url",""); cuori=item.get("favourite_count",0) or 0
                    try:
                        sec=int(time.time()-float(item.get("created_at_ts",time.time())))
                        pub=f"{sec}s fa" if sec<60 else f"{sec//60}m fa"
                    except: pub="ora"
                    ultimo_affare={"id":iid,"titolo":titolo,"brand":brand,"size":size,"prezzo":prezzo,"rule":rule,"link":link}
                    emoji="🟣🔥" if rule["sell_max"]>=80 else "🔴🔥" if rule["sell_max"]>=60 else "💥🔥"
                    color_note = f"🎨 {rule['color_source']}" if rule.get("has_color_ok") else "🎨 Colore non specificato - verifica foto"
                    titolo_embed=f"{emoji} {rule['brand'].upper()} {rule['cat'].upper()} | {titolo[:40]} | {prezzo}€ -> {rule['sell_min']}-{rule['sell_max']}€"
                    desc=(f"🔥 **CURATED PERFECT** 🔥\n{titolo}\n\n🏷️ Brand: {brand} ({rule['brand']})\n📦 Modello: {rule['cat']} | {'basta brand' if rule.get('basta_brand') else 'modello obbligatorio'}\n📏 Taglia: {size} ✅ S/M/L/XL\n✨ Cond: {cond}\n{color_note} | OK {', '.join(rule['colori_ok'][:3])}\n⏱️ {pub} | ❤️ {cuori}\n💰 BUY max {rule['buy_max']}€ | Prezzo: {prezzo}€\n💸 SELL {rule['sell_min']}-{rule['sell_max']}€\n[🚀 PRENDI SUBITO]({link})")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        emb=discord.Embed(title=titolo_embed,description=desc,color=0x9b59b6 if rule["sell_max"]>=80 else 0xff0000)
                        if foto: emb.set_image(url=foto)
                        await canale.send(content="@here 🔥 CURATED" if rule["sell_max"]>=80 else "",embed=emb)
                if len(gia_visti)%30==0: salva_visti()
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"scan err {e}"); continue
        salva_visti()
    except Exception as e:
        print(f"Errore scan: {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("Avvio V24 PERFECT")
        bot.run(tok)
