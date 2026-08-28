# 🔥 BOT V31.1 - PRIORITA GIUBBOTTO + BLACKLIST + FIX VISTI + FILTRO DANNEGGIATI
import discord, asyncio, requests, json, os, re, time, threading, urllib.parse
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

VISTI_FILE="gia_visti.json"; PREF_FILE="preferenze_utenti.json"
gia_visti=set(); vinted_session=None; last_session_refresh=0; ultimo_affare=None
# DEBUG: contatori per capire dove si fermano gli annunci
stats = {"scaricati":0,"vecchi":0,"blacklist":0,"danneggiato":0,"taglia_no":0,"bambino":0,
         "brand_no":0,"regola_no":0,"netto_basso":0,"segnalati":0}
ultimo_report = 0
USER_AGENTS=["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36","Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"]

# V31.1 - GIUBBOTTI PRIMA, poi felpe senza ghost/denali, poi maglione, poi jeans solo 3 brand
regole = [
  # GIUBBOTTI PRIMA - PRIORITA ASSOLUTA
  {"brand":"polo ralph lauren","cat":"giubbotto","models":["harrington","windbreaker","overshirt","puffer","corduroy","jacket","giubbotto","giacca","parka","piumino","cappotto"],"buy_max":40,"sell_min":65,"sell_max":85},
  {"brand":"tommy hilfiger","cat":"giubbotto","models":["sailing","coach","puffer","flag","harrington","giubbotto","giacca","jacket","parka","piumino"],"buy_max":35,"sell_min":55,"sell_max":75},
  {"brand":"carhartt","cat":"giubbotto","models":["detroit","michigan","og active jacket","detroit jacket","michigan coat","active jacket","giubbotto","giacca","parka"],"buy_max":40,"sell_min":75,"sell_max":95},
  {"brand":"north face","cat":"giubbotto","models":["nuptse","1996","1990 mountain","denali","gore-tex","mountain jacket","puffer","giubbotto","giacca","parka"],"buy_max":50,"sell_min":80,"sell_max":105},
  {"brand":"levi's","cat":"giubbotto","models":["trucker","type 3","sherpa","denim jacket","type iii","giubbotto","giacca","jacket"],"buy_max":26,"sell_min":45,"sell_max":65},
  {"brand":"stone island","cat":"giubbotto","models":["jacket","parka","puffer","ghost","membrana","nylon","overshirt","giubbotto","giacca","piumino","cappotto"],"buy_max":85,"sell_min":130,"sell_max":170},
  # FELPE - riportate parole generiche "felpa"/"hoodie" dove mancavano, tolto solo l'ambiguo "polo"/"ralph"
  {"brand":"polo ralph lauren","cat":"felpa","models":["bear","big pony","crest","rl 67","knit","quarter zip","felpa","hoodie","sweatshirt"],"buy_max":25,"sell_min":35,"sell_max":45},
  {"brand":"tommy hilfiger","cat":"felpa","models":["flag","crest","tommy jeans","spellout","big flag","felpa","hoodie","sweatshirt"],"buy_max":20,"sell_min":28,"sell_max":38},
  {"brand":"carhartt","cat":"felpa","models":["chase","og active","american script","script","active hoodie","felpa","hoodie","sweatshirt"],"buy_max":28,"sell_min":45,"sell_max":60},
  {"brand":"north face","cat":"felpa","models":["fleece","retro","1995","felpa","hoodie","sweatshirt"],"buy_max":28,"sell_min":50,"sell_max":70},
  {"brand":"nike","cat":"felpa","models":["center swoosh","big swoosh","90s","vintage","track jacket","windrunner","felpa","hoodie","sweatshirt"],"buy_max":20,"sell_min":32,"sell_max":48},
  {"brand":"stone island","cat":"felpa","models":["patch","crest","crewneck","hoodie","felpa","sweatshirt"],"buy_max":40,"sell_min":70,"sell_max":95},
  # MAGLIONI - riportata parola generica "maglione"
  {"brand":"polo ralph lauren","cat":"maglione","models":["cable knit","bear","quarter zip","cricket","knit","pony","maglione","sweater"],"buy_max":25,"sell_min":35,"sell_max":45},
  {"brand":"tommy hilfiger","cat":"maglione","models":["flag","crest","tommy jeans","spellout","maglione","sweater"],"buy_max":20,"sell_min":28,"sell_max":38},
  {"brand":"stone island","cat":"maglione","models":["knit","crewneck","patch","maglione","sweater"],"buy_max":40,"sell_min":70,"sell_max":90},
  # JEANS SOLO DOVE FAI SOLDI VERI - Polo/Tommy/Nike/North tolti
  {"brand":"carhartt","cat":"jeans","models":["double knee","single knee","work pant","double front","pant","jeans","cargo"],"buy_max":35,"sell_min":65,"sell_max":85},
  {"brand":"levi's","cat":"jeans","models":["501","505","511","512","chino","jeans","pantaloni lunghi"],"buy_max":22,"sell_min":45,"sell_max":65},
  {"brand":"stone island","cat":"jeans","models":["cargo","jeans","denim","pantaloni lunghi","cargo pants"],"buy_max":35,"sell_min":65,"sell_max":85},
]

BRAND_ALIASES = {
  "polo ralph lauren": ["ralph lauren","polo ralph lauren","raulph lauren","ralf lauren","floren","raulph","ralf","raulpppfloren","polo ralph"],
  "tommy hilfiger": ["tommy hilfiger","tommy hillfiger","tommi hilfiger"],
  "carhartt": ["carhartt","carharrt","carrhartt","carhart"],
  "north face": ["north face","nort face","northface","the north face","tnf"],
  "levi's": ["levi's","levis","levi s","levis 501"],
  "nike": ["nike","nikke"],
  "stone island": ["stone island","stoneisland","ston island","stone islan"],
}

TAGLIE_OK = ["S","M","L","XL","S/M","M/L","L/XL","S - M","M - L","50","52","32","34","M / IT 50","L - Uomo","L - Uomo / IT 52"]
BAMBINO_PATTERN = re.compile(r'(\b\d{1,2}\s*anni\b|\b\d{1,2}Y\b|\b\d{3}cm\b|kinder|junior|\b12A\b|\b14A\b|152|164|128|140)', re.I)
COLORI_TOP = ["bianco","nero","grigio","blu navy","navy","black","white","grey","gray"]
GIUBBOTTO_KEYWORDS = ["giubbotto","giacca","jacket","parka","puffer","piumino","cappotto"]

# FIX 1 NUOVO: filtro capi danneggiati (mancava dalla V10, mai riaggiunto in V30/V31)
DANNEGGIATO = ["rotto","rotta","buco","bucato","macchia","macchiato","strappato","strappata",
               "difettato","difettoso","danneggiato","rovinato","sfilacciato","scucito",
               "cerniera rotta","zip rotta","logoro","consumato","ingiallito"]

app=Flask(__name__)
@app.route("/")
def home(): return "Bot V31.1 - PRIORITA GIUBBOTTO + BLACKLIST + FIX VISTI + FILTRO DANNEGGIATI"
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
def is_danneggiato(tl): return any(x in tl for x in DANNEGGIATO)  # FIX 1 NUOVO
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
def is_giubbotto_prioritario(titolo):
    tl=titolo.lower()
    return any(k in tl for k in GIUBBOTTO_KEYWORDS)

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V31.1 online {bot.user} | {len(regole)} regole | PRIORITA GIUBBOTTO + FILTRO DANNEGGIATI")
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

@tasks.loop(seconds=6)
async def controllo_vinted():
    global ultimo_affare
    try:
        sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        # BLACKLIST GLOBALE all'inizio
        pref=carica_pref()
        blacklist_globale=[]
        for data in pref.values():
            blacklist_globale.extend([b.lower() for b in data.get("blacklist_titoli",[]) if b and len(b)>=4])
        blacklist_globale=list(set(blacklist_globale))

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
                    gia_visti.add(iid) # fix visti: subito dopo check, prima del try timestamp
                    stats["scaricati"]+=1  # DEBUG
                    cts = item.get("created_at_ts") or item.get("created_at") or item.get("photo",{}).get("created_at_ts") or item.get("photo",{}).get("high_resolution",{}).get("timestamp")
                    try:
                        cts = float(cts)
                        if cts > 1e10: cts = cts/1000
                        if time.time() - cts > 150:
                            stats["vecchi"]+=1  # DEBUG
                            continue
                    except:
                        pass  # timestamp mancante/campo cambiato: non scartiamo più, teniamo l'annuncio (order=newest_first + gia_visti ci proteggono già dai duplicati/vecchi)
                    titolo=item.get("title",""); brand=item.get("brand_title",""); size=item.get("size_title","")
                    descrizione=item.get("description","") or ""
                    tl=(titolo+" "+descrizione).lower()
                    # BLACKLIST CHECK
                    if blacklist_globale and any(b in titolo.lower() for b in blacklist_globale):
                        stats["blacklist"]+=1  # DEBUG
                        continue
                    # FIX 1 NUOVO: scarta capi danneggiati
                    if is_danneggiato(tl):
                        stats["danneggiato"]+=1  # DEBUG
                        continue
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if not taglia_ok(size):
                        stats["taglia_no"]+=1  # DEBUG
                        continue
                    if is_bambino(size,titolo,descrizione):
                        stats["bambino"]+=1  # DEBUG
                        continue
                    if any(x in tl for x in ["shorts","bermuda","pantaloncini","t-shirt","magliettina","costume","intimo","bikini","canotta"]):
                        if not any(k in tl for k in ["felpa","maglione","giubbotto","giacca","jacket","parka","puffer","jeans","cargo","chino","501","505","double knee","single knee","work pant"]):
                            continue
                    brands_trovati = match_brand(titolo+" "+brand+" "+descrizione)
                    if not brands_trovati:
                        stats["brand_no"]+=1  # DEBUG
                        continue
                    # PRIORITA GIUBBOTTO
                    priorita_giubbotto = is_giubbotto_prioritario(titolo)
                    rule=None
                    regole_ordinate = sorted(regole, key=lambda r: (0 if r["cat"]=="giubbotto" else 1)) if priorita_giubbotto else regole
                    for rg in regole_ordinate:
                        if rg["brand"] not in brands_trovati: continue
                        if priorita_giubbotto and rg["cat"]!="giubbotto": continue
                        if not any(m in (titolo+" "+brand+" "+descrizione).lower() for m in rg["models"]): continue
                        if prezzo>rg["buy_max"]: continue
                        rule=rg; break
                    if not rule and priorita_giubbotto:
                        for rg in regole:
                            if rg["brand"] not in brands_trovati: continue
                            if not any(m in (titolo+" "+brand+" "+descrizione).lower() for m in rg["models"]): continue
                            if prezzo>rg["buy_max"]: continue
                            rule=rg; break
                    if not rule:
                        stats["regola_no"]+=1  # DEBUG (brand giusto ma modello/prezzo fuori soglia)
                        continue
                    netto = rule["sell_min"] - prezzo - 5
                    if netto < 10:
                        stats["netto_basso"]+=1  # DEBUG
                        continue
                    stats["segnalati"]+=1  # DEBUG
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url","")
                    sec=int(time.time()-float(cts)) if cts and isinstance(cts,(int,float)) else 0
                    ultimo_affare = {"titolo": titolo, "id": iid, "prezzo": prezzo}
                    col_score=colore_score(titolo)
                    # NB: repliche - il bot non le riconosce dal testo, controllare sempre le foto a occhio prima di comprare
                    titolo_embed=f"{'🧥' if rule['cat']=='giubbotto' else '⚪⚫' if col_score>0 else '🔥'} {rule['brand'].upper()} {rule['cat'].upper()} | {titolo[:40]} | {prezzo}€ -> {rule['sell_min']}-{rule['sell_max']}€ (+{round(netto)}€)"
                    desc=(f"⚡ **{sec}s FA - +{round(netto)}€ {'🎯 COLORE TOP' if col_score>0 else ''}** ⚡\n{titolo}\n\nBrand: {brand} ({brands_trovati[0]})\nCat: {rule['cat']} ✅ {'PRIORITA GIUBBOTTO' if priorita_giubbotto else ''}\nTaglia: {size}\n⏱️ {sec}s\n💰 BUY {prezzo}€ (max {rule['buy_max']}€)\n💸 SELL {rule['sell_min']}-{rule['sell_max']}€\n⚠️ Controlla le foto reali prima di comprare (rischio repliche)\n[🚀 PRENDI]({link})")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        emb=discord.Embed(title=titolo_embed,description=desc,color=0x9b59b6 if rule['cat']=='giubbotto' else (0xff0000 if netto>=25 else 0x00ff88))
                        if foto: emb.set_image(url=foto)
                        ping=f"@here 🧥 GIUBBOTTO {sec}s | +{round(netto)}€" if rule['cat']=='giubbotto' else f"@here ⚡ {rule['cat']} {sec}s | +{round(netto)}€ {'🎯 COLORE TOP' if col_score>0 else ''}" if netto>=18 or col_score>0 else ""
                        await canale.send(content=ping,embed=emb)
                await asyncio.sleep(0.8)
            except Exception as e:
                print(f"err {e}"); continue
        salva_visti()
        # DEBUG: manda un report ogni 10 minuti su Discord con i contatori
        global ultimo_report
        if time.time() - ultimo_report > 600:
            ultimo_report = time.time()
            canale=None
            for g in bot.guilds:
                for ch in g.text_channels:
                    if ch.permissions_for(g.me).send_messages: canale=ch; break
                if canale: break
            if canale:
                r = (f"🧪 **DEBUG 10 min** — scaricati:{stats['scaricati']} vecchi:{stats['vecchi']} "
                     f"blacklist:{stats['blacklist']} danneggiato:{stats['danneggiato']} taglia_no:{stats['taglia_no']} "
                     f"bambino:{stats['bambino']} brand_no:{stats['brand_no']} regola_no:{stats['regola_no']} "
                     f"netto_basso:{stats['netto_basso']} segnalati:{stats['segnalati']}")
                await canale.send(r)
                for k in stats: stats[k]=0  # DEBUG: azzero per la prossima finestra di 10 min
    except Exception as e:
        print(e)

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio V31.1 - PRIORITA GIUBBOTTO + BLACKLIST + FIX VISTI + FILTRO DANNEGGIATI")
        bot.run(tok)
