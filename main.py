# 🔥 BOT V30.1 FIXATO - 4 CAT OTTIMIZZATE + JEANS SOLO DOVE MARGINE + FIX TOTALI
import discord, asyncio, requests, json, os, re, time, threading, urllib.parse
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

VISTI_FILE="gia_visti.json"; PREF_FILE="preferenze_utenti.json"
gia_visti=set(); vinted_session=None; last_session_refresh=0; ultimo_affare=None
USER_AGENTS=["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36","Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"]

# V30.1 - 7 brand, felpa/maglione/giubbotto per tutti, jeans SOLO per 3 con margine reale
regole = [
  # POLO - NO JEANS (stanno fermi 2 mesi)
  {"brand":"polo ralph lauren","cat":"maglione","models":["cable knit","bear","quarter zip","cricket","knit","pony","maglione"],"buy_max":23,"sell_min":35,"sell_max":45},
  {"brand":"polo ralph lauren","cat":"felpa","models":["bear","big pony","crest","rl 67","knit","quarter zip","felpa"],"buy_max":23,"sell_min":35,"sell_max":45},
  {"brand":"polo ralph lauren","cat":"giubbotto","models":["harrington","windbreaker","overshirt","puffer","corduroy","polo","ralph","jacket","giubbotto","giacca"],"buy_max":40,"sell_min":65,"sell_max":85},
  # TOMMY - NO JEANS
  {"brand":"tommy hilfiger","cat":"maglione","models":["flag","crest","tommy jeans","spellout","maglione"],"buy_max":18,"sell_min":28,"sell_max":38},
  {"brand":"tommy hilfiger","cat":"felpa","models":["flag","crest","tommy jeans","spellout","big flag","felpa"],"buy_max":18,"sell_min":28,"sell_max":38},
  {"brand":"tommy hilfiger","cat":"giubbotto","models":["sailing","coach","puffer","flag","harrington","giubbotto","giacca"],"buy_max":35,"sell_min":55,"sell_max":75},
  # CARHARTT - CON JEANS (dove fai soldi)
  {"brand":"carhartt","cat":"felpa","models":["chase","og active","american script","script","active hoodie","felpa"],"buy_max":28,"sell_min":45,"sell_max":60},
  {"brand":"carhartt","cat":"giubbotto","models":["detroit","michigan","og active jacket","detroit jacket","michigan coat","active jacket","giubbotto"],"buy_max":40,"sell_min":75,"sell_max":95},
  {"brand":"carhartt","cat":"jeans","models":["double knee","single knee","work pant","double front","pant","jeans","cargo"],"buy_max":35,"sell_min":65,"sell_max":85},
  # NORTH FACE - NO JEANS
  {"brand":"north face","cat":"felpa","models":["denali","fleece","retro","1995","1990 mountain","felpa"],"buy_max":28,"sell_min":50,"sell_max":70},
  {"brand":"north face","cat":"giubbotto","models":["nuptse","1996","1990 mountain","denali","gore-tex","mountain jacket","puffer","giubbotto"],"buy_max":50,"sell_min":80,"sell_max":105},
  # LEVI'S - CON JEANS (501/505/511/512 chino)
  {"brand":"levi's","cat":"giubbotto","models":["trucker","type 3","sherpa","denim jacket","type iii","giubbotto"],"buy_max":26,"sell_min":45,"sell_max":65},
  {"brand":"levi's","cat":"jeans","models":["501","505","511","512","chino","jeans","pantaloni lunghi","501 jeans","505 jeans"],"buy_max":22,"sell_min":45,"sell_max":65},
  # NIKE - NO JEANS
  {"brand":"nike","cat":"felpa","models":["center swoosh","big swoosh","spellout","90s","vintage","windrunner","track jacket","windbreaker","felpa"],"buy_max":22,"sell_min":35,"sell_max":48},
  # STONE ISLAND - CON JEANS (cargo/jeans)
  {"brand":"stone island","cat":"felpa","models":["patch","crest","ghost","crewneck","hoodie","felpa"],"buy_max":40,"sell_min":70,"sell_max":95},
  {"brand":"stone island","cat":"maglione","models":["knit","crewneck","patch","ghost","maglione"],"buy_max":40,"sell_min":70,"sell_max":90},
  {"brand":"stone island","cat":"giubbotto","models":["jacket","parka","puffer","ghost","membrana","nylon","overshirt","giubbotto"],"buy_max":85,"sell_min":130,"sell_max":170},
  {"brand":"stone island","cat":"jeans","models":["cargo","jeans","denim","pantaloni lunghi","cargo pants","jeans lunghi"],"buy_max":35,"sell_min":65,"sell_max":85},
]

BRAND_ALIASES = {
  "polo ralph lauren": ["ralph lauren","polo ralph lauren","raulph lauren","ralf lauren","floren","raulph","ralf","raulpppfloren","polo ralph"],
  "tommy hilfiger": ["tommy hilfiger","tommy hillfiger","tommi hilfiger"],
  "carhartt": ["carhartt","carharrt","carrhartt","carhart"],
  "north face": ["north face","nort face","northface","the north face","tnf"],
  "levi's": ["levi's","levis","levi s","levi s jeans","levis 501"],
  "nike": ["nike","nikke"],
  "stone island": ["stone island","stoneisland","ston island","stone islan"],
}

TAGLIE_OK = ["S","M","L","XL","S/M","M/L","L/XL","S - M","M - L","50","52","32","34","M / IT 50","L - Uomo","L - Uomo / IT 52"]
BANNED = ["shorts","bermuda","pantaloncini","t-shirt","magliettina","costume","intimo","bikini","canotta","top","gonna","vestito","polo come maglietta"]
BAMBINO_PATTERN = re.compile(r'(\b\d{1,2}\s*anni\b|\b\d{1,2}Y\b|\b\d{3}cm\b|kinder|junior|\b12A\b|\b14A\b|152|164|128|140)', re.I)
COLORI_TOP = ["bianco","nero","grigio","blu navy","navy","black","white","grey","gray"]

app=Flask(__name__)
@app.route("/")
def home(): return "Bot V30.1 FIXATO - 4 cat ottimizzate jeans solo Levi/Carhartt/Stone"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

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
def carica_pref():
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE,"r") as f: return json.load(f)
        except: return {}
    return {}
def salva_pref(p):
    with open(PREF_FILE,"w") as f: json.dump(p,f,indent=2)
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

def taglia_ok(s):
    if not s: return False
    su = f" {s.upper()} "
    for t in TAGLIE_OK:
        if f" {t} " in su or su.strip() == t:
            return True
    for t in ["S","M","L","XL"]:
        if f" {t} " in su or f" {t}/" in su or f"/{t} " in su or f" {t}-" in su or f"-{t} " in su:
            return True
    return False

def is_bambino(s,t,d): return bool(BAMBINO_PATTERN.search(f"{s} {t} {d}".lower()))
def match_brand(testo):
    tl=testo.lower().replace("ppp","pp")
    trovati=[]
    for brand_ufficiale, alias_list in BRAND_ALIASES.items():
        for alias in alias_list:
            if alias in tl or alias.replace(" ","") in tl.replace(" ",""):
                trovati.append(brand_ufficiale)
                break
    return trovati
def colore_score(titolo):
    return sum(1 for c in COLORI_TOP if c in titolo.lower())

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V30.1 online {bot.user} | {len(regole)} regole | 4 cat ottimizzate")
    if not controllo_vinted.is_running(): controllo_vinted.start()

@bot.event
async def on_message(message):
    global ultimo_affare
    if message.author==bot.user: return
    if "non è un affare" in message.content.lower() or "bidonata" in message.content.lower():
        if ultimo_affare:
            pref=carica_pref(); uid=str(message.author.id)
            if uid not in pref: pref[uid]={"blacklist_titoli":[]}
            pref[uid]["blacklist_titoli"].append(ultimo_affare.get("titolo","").lower()[:80])
            salva_pref(pref)
            await message.channel.send(f"🧠 Blacklistato: {ultimo_affare.get('titolo')[:50]}")
            return

@tasks.loop(seconds=2.5)
async def controllo_vinted():
    global ultimo_affare
    try:
        sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        search_terms = ["polo ralph lauren","tommy hilfiger","carhartt","north face","levi","nike","stone island"]
        for term in search_terms:
            q=urllib.parse.quote(term)
            url=f"https://www.vinted.it/api/v2/catalog/items?search_text={q}&order=newest_first&per_page=25"
            try:
                r=sess.get(url,headers=headers,timeout=10)
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    cts = item.get("created_at_ts") or item.get("created_at") or item.get("photo",{}).get("created_at_ts")
                    try:
                        cts = float(cts)
                        if cts > 1e10: cts = cts/1000
                        if time.time() - cts > 150:
                            gia_visti.add(iid)
                            continue
                    except:
                        continue
                    gia_visti.add(iid)
                    titolo=item.get("title",""); brand=item.get("brand_title",""); size=item.get("size_title","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    descrizione=item.get("description","") or ""
                    if not taglia_ok(size): continue
                    if is_bambino(size,titolo,descrizione): continue
                    tl=(titolo+" "+descrizione).lower()
                    if any(x in tl for x in ["shorts","bermuda","pantaloncini","t-shirt","magliettina","costume","intimo","bikini","canotta"]):
                        if not any(k in tl for k in ["felpa","maglione","giubbotto","giacca","jeans","cargo","chino","501","505","double knee","single knee","work pant"]):
                            continue
                    brands_trovati = match_brand(titolo+" "+brand+" "+descrizione)
                    if not brands_trovati: continue
                    rule=None
                    for rg in regole:
                        if rg["brand"] not in brands_trovati: continue
                        if not any(m in (titolo+" "+brand+" "+descrizione).lower() for m in rg["models"]): continue
                        if prezzo>rg["buy_max"]: continue
                        rule=rg; break
                    if not rule: continue
                    netto = rule["sell_min"] - prezzo - 5
                    if netto < 15: continue
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url","")
                    sec=int(time.time()-float(cts)) if cts else 0
                    ultimo_affare = {"titolo": titolo, "id": iid, "prezzo": prezzo}
                    col_score=colore_score(titolo)
                    titolo_embed=f"{'⚪⚫' if col_score>0 else '🔥'} {rule['brand'].upper()} {rule['cat'].upper()} | {titolo[:40]} | {prezzo}€ -> {rule['sell_min']}-{rule['sell_max']}€ (+{round(netto)}€)"
                    desc=(f"⚡ **{sec}s FA - +{round(netto)}€ {'🎯 COLORE TOP' if col_score>0 else ''}** ⚡\n{titolo}\n\nBrand: {brand} ({brands_trovati[0]})\nCat: {rule['cat']} ✅\nTaglia: {size}\n⏱️ {sec}s\n💰 BUY {prezzo}€ (max {rule['buy_max']}€)\n💸 SELL {rule['sell_min']}-{rule['sell_max']}€\n[🚀 PRENDI]({link})")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        emb=discord.Embed(title=titolo_embed,description=desc,color=0x9b59b6 if netto>=25 else 0xff0000)
                        if foto: emb.set_image(url=foto)
                        ping=f"@here ⚡ {rule['cat']} {sec}s | +{round(netto)}€ {'🎯 COLORE TOP' if col_score>0 else ''}" if netto>=18 or col_score>0 else ""
                        await canale.send(content=ping,embed=emb)
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"err {e}"); continue
        salva_visti()
    except Exception as e:
        print(e)

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio V30.1 FIXATO - jeans solo Levi/Carhartt/Stone + fix totali")
        bot.run(tok)
