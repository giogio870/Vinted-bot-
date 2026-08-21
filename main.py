# 🔥 BOT V27 RESET TOTALE - SOLO APPENA USCITI 2 MIN + 15€ MARGINE
import discord, asyncio, requests, json, os, re, time, random, threading
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

VISTI_FILE="gia_visti.json"; PREF_FILE="preferenze_utenti.json"; LEARNING_FILE="learning.json"; CONFIG_FILE="config.json"
gia_visti=set(); vinted_session=None; last_session_refresh=0; ultimo_affare=None
USER_AGENTS=["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36","Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"]

regole = [
  {"brand":"polo ralph lauren","cat":"maglione","models":["cable knit","bear","quarter zip","cricket","knit","pony"],"buy_max":23,"sell_min":35,"sell_max":45},
  {"brand":"polo ralph lauren","cat":"felpa","models":["bear","big pony","crest","rl 67","knit","quarter zip"],"buy_max":23,"sell_min":35,"sell_max":45},
  {"brand":"polo ralph lauren","cat":"giubbotto","models":["harrington","windbreaker","overshirt","puffer","corduroy"],"buy_max":40,"sell_min":65,"sell_max":85},
  {"brand":"polo ralph lauren","cat":"t-shirt","models":["bear","big pony"],"buy_max":12,"sell_min":22,"sell_max":32},
  {"brand":"tommy hilfiger","cat":"maglione","models":["flag","crest","tommy jeans","spellout"],"buy_max":18,"sell_min":28,"sell_max":38},
  {"brand":"tommy hilfiger","cat":"felpa","models":["flag","crest","tommy jeans","spellout","big flag"],"buy_max":18,"sell_min":28,"sell_max":38},
  {"brand":"tommy hilfiger","cat":"giubbotto","models":["sailing","coach","puffer","flag","harrington"],"buy_max":35,"sell_min":55,"sell_max":75},
  {"brand":"carhartt","cat":"felpa","models":["chase","og active","american script","script","active hoodie"],"buy_max":28,"sell_min":45,"sell_max":60},
  {"brand":"carhartt","cat":"giubbotto","models":["detroit","michigan","og active jacket","detroit jacket","michigan coat","active jacket"],"buy_max":40,"sell_min":75,"sell_max":95},
  {"brand":"north face","cat":"felpa","models":["denali","fleece","retro","1995","1990 mountain"],"buy_max":28,"sell_min":50,"sell_max":70},
  {"brand":"north face","cat":"giubbotto","models":["nuptse","1996","1990 mountain","denali","gore-tex","mountain jacket","puffer"],"buy_max":50,"sell_min":80,"sell_max":105},
  {"brand":"levi's","cat":"giubbotto","models":["trucker","type 3","sherpa","denim jacket","type iii"],"buy_max":28,"sell_min":45,"sell_max":65},
  {"brand":"nike","cat":"felpa","models":["center swoosh","big swoosh","spellout","90s","vintage","windrunner","track jacket","windbreaker"],"buy_max":22,"sell_min":35,"sell_max":48},
  {"brand":"stone island","cat":"felpa","models":["patch","crest","ghost","crewneck","hoodie"],"buy_max":40,"sell_min":70,"sell_max":95},
  {"brand":"stone island","cat":"maglione","models":["knit","crewneck","patch","ghost"],"buy_max":40,"sell_min":70,"sell_max":90},
  {"brand":"stone island","cat":"giubbotto","models":["jacket","parka","puffer","ghost","membrana","nylon","overshirt"],"buy_max":85,"sell_min":130,"sell_max":170},
]

TAGLIE_OK = ["S","M","L","XL","S/M","M/L","L/XL"]
COND_OK = ["nuovo con etichette","nuovo senza etichette","nuovo","ottime","molto buono","very good","ottimo","eccellente","excellent","buone","buono","good","discrete"]
BANNED_KEYWORDS = ["shorts","bermuda","vaquero","elite","pantaloncini","jeans corto","sneaker tee","y2k tee","bikini","costume","intimo","boxer","gonna","vestito"]
BAMBINO_PATTERN = re.compile(r'(\b\d{1,2}\s*anni\b|\b\d{1,2}Y\b|\b\d{3}cm\b|kinder|junior|\b12A\b|\b14A\b|152|164|128|140)', re.I)

app=Flask(__name__)
@app.route("/")
def home(): return "Bot V27 RESET 2MIN 15€ MARGINE"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def carica_config(): return {"spedizione":5,"max_secondi_freschezza":120,"margine_minimo":15}
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
def carica_learning():
    if os.path.exists(LEARNING_FILE):
        try:
            with open(LEARNING_FILE,"r") as f: return json.load(f)
        except: return []
    return []
def salva_learning(l):
    with open(LEARNING_FILE,"w") as f: json.dump(l[-200:],f,indent=2)
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
    st=s.strip().upper()
    return st in TAGLIE_OK or st in ["S","M","L","XL"]
def is_banned(t): return any(k in t.lower() for k in BANNED_KEYWORDS)
def is_bambino(s,t,d): return bool(BAMBINO_PATTERN.search(f"{s} {t} {d}".lower()))
def is_tshirt_base(t,d,r):
    if r["cat"]=="t-shirt": return not ("bear" in f"{t} {d}".lower() or "big pony" in f"{t} {d}".lower())
    return False

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V27 RESET online {bot.user} | {len(regole)} regole | 120s | margine 15€")
    if not controllo_vinted.is_running(): controllo_vinted.start()

@bot.event
async def on_message(message):
    global ultimo_affare
    if message.author==bot.user: return
    if message.content.startswith("!"):
        await bot.process_commands(message); return
    if "non è un affare" in message.content.lower() or "bidonata" in message.content.lower():
        if ultimo_affare:
            pref=carica_pref(); uid=str(message.author.id)
            if uid not in pref: pref[uid]={"blacklist_titoli":[]}
            pref[uid]["blacklist_titoli"].append(ultimo_affare.get("titolo","").lower()[:80])
            salva_pref(pref)
            await message.channel.send(f"🧠 Blacklistato: {ultimo_affare.get('titolo')[:50]}")
            return

@bot.command()
async def reset(ctx):
    pref=carica_pref(); uid=str(ctx.author.id)
    if uid in pref: del pref[uid]; salva_pref(pref)
    await ctx.send("✅ Reset fatto.")

@tasks.loop(seconds=2.5)
async def controllo_vinted():
    global ultimo_affare
    try:
        sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        pref=carica_pref()
        for url in [f"https://www.vinted.it/api/v2/catalog/items?search_text={b.replace(' ','%20')}&order=newest_first&per_page=25" for b in list(set([r['brand'] for r in regole]))][:14]:
            try:
                r=sess.get(url,headers=headers,timeout=10)
                if r.status_code==429: await asyncio.sleep(5); continue
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    gia_visti.add(iid)
                    cts=item.get("created_at_ts")
                    try:
                        if not cts or (time.time()-float(cts))>120: continue
                    except: continue
                    titolo=item.get("title",""); brand=item.get("brand_title",""); size=item.get("size_title",""); cond=item.get("status","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if not taglia_ok(size): continue
                    descrizione=item.get("description","") or ""
                    if is_banned(f"{titolo} {descrizione}") or is_bambino(size,titolo,descrizione): continue
                    tlow=(titolo+" "+brand).lower()
                    if any(bt in tlow for data in pref.values() for bt in data.get("blacklist_titoli",[])): continue
                    # match regola
                    rule=None
                    testo=(titolo+" "+brand+" "+descrizione).lower()
                    for rg in regole:
                        if rg["brand"] not in tlow and rg["brand"].split()[0] not in tlow:
                            if not ("ralph lauren" in tlow and "polo ralph" in rg["brand"]):
                                if not ("levi" in tlow and "levi's" in rg["brand"]):
                                    if not ("stone island" in tlow and "stone island" in rg["brand"]): continue
                        if rg["cat"]=="t-shirt" and is_tshirt_base(titolo,descrizione,rg): continue
                        if not any(m in testo for m in rg["models"]): continue
                        if prezzo>rg["buy_max"]: continue
                        rule=rg; break
                    if not rule: continue
                    # MARGINE 15€
                    netto = rule["sell_min"] - prezzo - 5
                    if netto < 15: continue
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url","")
                    sec=int(time.time()-float(cts)) if cts else 0
                    ultimo_affare = {"titolo": titolo, "id": iid, "prezzo": prezzo}
                    emoji="🟣🔥" if rule["sell_max"]>=80 else "🔴🔥" if rule["sell_max"]>=50 else "💥🔥"
                    titolo_embed=f"{emoji} {rule['brand'].upper()} {rule['cat'].upper()} | {titolo[:40]} | {prezzo}€ -> {rule['sell_min']}-{rule['sell_max']}€ ({round(netto)}€ NETTI)"
                    desc=(f"⚡ **APPENA USCITO {sec}s FA - MARGINE {round(netto)}€** ⚡\n{titolo}\n\nBrand: {brand}\nTaglia: {size} ✅\nCond: {cond}\n⏱️ {sec}s fa\n💰 BUY {prezzo}€ (max {rule['buy_max']}€)\n💸 SELL REALE {rule['sell_min']}-{rule['sell_max']}€\nNETTO +{round(netto)}€ MINIMO\n[🚀 PRENDI SUBITO]({link})")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        emb=discord.Embed(title=titolo_embed,description=desc,color=0x9b59b6 if netto>=25 else 0xff0000)
                        if foto: emb.set_image(url=foto)
                        await canale.send(content=f"@here ⚡ {sec}s fa | +{round(netto)}€ NETTI" if netto>=18 else "",embed=emb)
                await asyncio.sleep(0.35)
            except Exception as e:
                print(f"scan err {e}"); continue
        salva_visti()
    except Exception as e:
        print(f"Errore scan {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio V27 RESET TOTALE - 120s 15€ margine")
        bot.run(tok)
