# 🔥 BOT V26 - SOLO AFFARI VELOCI + CERVELLO + CHAT 🧠 - FINALE FIX ultimo_affare
import discord, asyncio, requests, json, os, re, time, random, threading, datetime
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE="filtri.json"; CONFIG_FILE="config.json"; CHAT_FILE="chat_storico.json"; VISTI_FILE="gia_visti.json"
PREF_FILE="preferenze_utenti.json"; LEARNING_FILE="learning.json"
gia_visti=set(); vinted_session=None; last_session_refresh=0; ultimo_affare=None
USER_AGENTS=["Mozilla/5.0"]

# V26 REGOLE REALI - SOLO AFFARI VELOCI
regole = [
  {"brand":"polo ralph lauren","cat":"maglione","models":["cable knit","bear","quarter zip","cricket","knit","pony"],"colori_no":["giallo fluo","rosa fluo","fluo","neon"],"colori_ok":["navy","beige","bianco","nero","burgundy","verde","grigio"],"buy_max":20,"sell_min":30,"sell_max":40},
  {"brand":"polo ralph lauren","cat":"felpa","models":["bear","big pony","crest","rl 67","knit","quarter zip"],"colori_no":["fluo"],"colori_ok":["navy","nero","grigio","bianco","beige","burgundy"],"buy_max":20,"sell_min":30,"sell_max":40},
  {"brand":"polo ralph lauren","cat":"giubbotto","models":["harrington","windbreaker","overshirt","puffer","corduroy"],"colori_no":["fluo"],"colori_ok":["navy","beige","nero","verde"],"buy_max":35,"sell_min":60,"sell_max":80},
  {"brand":"polo ralph lauren","cat":"t-shirt","models":["bear","big pony"],"colori_no":["fluo"],"colori_ok":["bianco","nero","navy"],"buy_max":10,"sell_min":18,"sell_max":28},
  {"brand":"tommy hilfiger","cat":"maglione","models":["flag","crest","tommy jeans","spellout"],"colori_no":["fluo"],"colori_ok":["navy","rosso","bianco","grigio","beige","blu","azul oscuro"],"buy_max":15,"sell_min":25,"sell_max":35},
  {"brand":"tommy hilfiger","cat":"felpa","models":["flag","crest","tommy jeans","spellout","big flag"],"colori_no":["fluo"],"colori_ok":["navy","grigio","nero","bianco","royal","azul"],"buy_max":15,"sell_min":25,"sell_max":35},
  {"brand":"tommy hilfiger","cat":"giubbotto","models":["sailing","coach","puffer","flag","harrington"],"colori_no":["fluo"],"colori_ok":["navy","nero","rosso","blu"],"buy_max":30,"sell_min":50,"sell_max":70},
  {"brand":"carhartt","cat":"felpa","models":["chase","og active","american script","script","active hoodie"],"colori_no":["fluo","rosa chiaro"],"colori_ok":["nero","hamilton brown","marrone","navy","grigio","verde"],"buy_max":25,"sell_min":40,"sell_max":55},
  {"brand":"carhartt","cat":"giubbotto","models":["detroit","michigan","og active jacket","detroit jacket","michigan coat","active jacket"],"colori_no":["fluo"],"colori_ok":["hamilton brown","marrone","nero","verde","camo","blu"],"buy_max":35,"sell_min":70,"sell_max":90},
  {"brand":"north face","cat":"felpa","models":["denali","fleece","retro","1995","1990 mountain"],"colori_no":["fluo"],"colori_ok":["nero","beige","khaki","giallo","blu","rosso"],"buy_max":25,"sell_min":45,"sell_max":65},
  {"brand":"north face","cat":"giubbotto","models":["nuptse","1996","1990 mountain","denali","gore-tex","mountain jacket","puffer"],"colori_no":["fluo"],"colori_ok":["nero","beige","giallo","blu"],"buy_max":45,"sell_min":75,"sell_max":100},
  {"brand":"levi's","cat":"giubbotto","models":["trucker","type 3","sherpa","denim jacket","type iii"],"colori_no":["fluo"],"colori_ok":["denim","blu","nero","chiaro"],"buy_max":25,"sell_min":40,"sell_max":60},
  {"brand":"nike","cat":"felpa","models":["center swoosh","big swoosh","spellout","90s","vintage","windrunner","track jacket","windbreaker"],"colori_no":["fluo"],"colori_ok":["grigio","nero","navy","bianco","blu"],"buy_max":18,"sell_min":30,"sell_max":40},
]

TAGLIE_OK = ["S","M","L","XL","S/M","M/L","L/XL","S - M","M - L"]
COND_OK = ["nuovo con etichette","nuovo senza etichette","nuovo","ottime","molto buono","very good","ottimo","eccellente","excellent","buone","buono","good","discrete"]
BANNED_KEYWORDS = ["short","bermuda","vaquero","elite","pantaloncini","jeans corto","sneaker tee","y2k tee","bikini","costume","intimo","boxer","gonna","vestito"]
BAMBINO_PATTERN = re.compile(r'(\b\d{1,2}\s*anni\b|\b\d{1,2}Y\b|\b\d{3}cm\b|kinder|junior|\b12A\b|\b14A\b|152|164|128|140)', re.I)

app=Flask(__name__)
@app.route("/")
def home(): return "Bot V26 AFFARI VELOCI + CERVELLO"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def carica_config():
    default={"spedizione":5,"max_secondi_freschezza":60}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE,"r") as f: cfg=json.load(f); default.update(cfg); return default
        except: return default
    return default
def salva_config(cfg):
    with open(CONFIG_FILE,"w") as f: json.dump(cfg,f,indent=2)
def carica_chat():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE,"r") as f: return json.load(f)
        except: return {}
    return {}
def salva_chat(ch):
    with open(CHAT_FILE,"w") as f: json.dump(ch,f,indent=2)
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
def condizione_ok(s): return any(c in s.lower() for c in COND_OK) if s else False
def taglia_ok(s):
    if not s: return False
    st=s.strip().upper()
    if st in TAGLIE_OK or st in ["S","M","L","XL"]: return True
    if st in ["XXL","XS","XXS","XXXL"] or "XXL" in st or "XXXL" in st: return False
    return any(x in st for x in ["S","M","L","XL"])
def is_banned(titolo, descrizione): return any(k in f"{titolo} {descrizione}".lower() for k in BANNED_KEYWORDS)
def is_bambino(size_title, titolo, descrizione): return bool(BAMBINO_PATTERN.search(f"{size_title} {titolo} {descrizione}".lower()))
def is_tshirt_base(titolo, descrizione, rule):
    if rule["cat"]=="t-shirt":
        testo=f"{titolo} {descrizione}".lower()
        return not ("bear" in testo or "big pony" in testo)
    return False
def matches_curated(titolo, brand_title, descrizione, prezzo, size_title, status, fav_count, created_ts):
    tlow=(titolo+" "+brand_title).lower()
    dlow=(descrizione or "").lower()
    testo_completo=tlow+" "+dlow
    if is_banned(titolo, descrizione): return None
    if is_bambino(size_title, titolo, descrizione): return None
    if not taglia_ok(size_title) or not condizione_ok(status): return None
    try:
        if not created_ts or (time.time()-float(created_ts))>60: return None
    except: return None
    if fav_count and int(fav_count)>0: return None
    for rule in regole:
        b=rule["brand"]
        if b not in tlow and b.split()[0] not in tlow:
            if not (b=="polo ralph lauren" and "ralph lauren" in tlow):
                if not (b=="north face" and "north face" in tlow):
                    if not (b=="levi's" and "levi" in tlow): continue
        if rule["cat"]=="t-shirt" and is_tshirt_base(titolo, descrizione, rule): continue
        if not any(m in testo_completo for m in rule["models"]): continue
        if any(cn in testo_completo for cn in rule["colori_no"] if cn): continue
        if prezzo>rule["buy_max"]: continue
        rc=dict(rule)
        rc["has_color_ok"]=any(co in testo_completo for co in rule["colori_ok"]) if rule["colori_ok"] else True
        rc["color_source"]="titolo" if any(co in tlow for co in rule["colori_ok"]) else "descrizione" if any(co in dlow for co in rule["colori_ok"]) else "foto"
        return rc
    return None

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V26 AFFARI VELOCI + CERVELLO online {bot.user} | Regole {len(regole)} | 60s 0like")
    if not controllo_vinted.is_running(): controllo_vinted.start()

@bot.event
async def on_message(message):
    global ultimo_affare
    if message.author==bot.user: return
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    contenuto=message.content.lower()
    uid=str(message.author.id)
    chat=carica_chat()
    pref=carica_pref()
    learning=carica_learning()
    if any(x in contenuto for x in ["non è un affare","non e un affare","bidonata","non vale","fa schifo"]):
        if ultimo_affare:
            titolo=ultimo_affare.get("titolo","").lower()
            if uid not in pref: pref[uid]={"blacklist_titoli":[],"disliked":[],"brands":[],"sizes":[]}
            if titolo and titolo not in pref[uid]["blacklist_titoli"]:
                pref[uid]["blacklist_titoli"].append(titolo[:80])
            salva_pref(pref)
            learning.append({"titolo":ultimo_affare.get("titolo"),"motivo":"non è un affare","time":time.time()})
            salva_learning(learning)
            await message.channel.send(f"🧠 Capito {message.author.mention}, blacklist: `{ultimo_affare.get('titolo')[:50]}`. Non te lo mando più.")
            return
    if "config" in contenuto or "impostazioni" in contenuto:
        cfg=carica_config()
        await message.channel.send(f"⚙️ V26: max_freschezza {cfg.get('max_secondi_freschezza')}s, regole {len(regole)}, solo 0-60s 0 like, no shorts/t-shirt base")
        return
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        if uid not in chat: chat[uid]=[]
        chat[uid].append({"role":"user","content":message.content,"time":time.time()})
        salva_chat(chat)
        if "ciao" in contenuto:
            await message.channel.send(f"Ciao {message.author.mention}! Sono V26 AFFARI VELOCI 🧠 - mando solo pezzi 0-60s 0 like. Shorts e t-shirt base tolte.")
        elif "quanto" in contenuto or "guadagno" in contenuto:
            await message.channel.send(f"💰 Prezzi reali V26: Polo maglione/felpa buy 20€ -> sell 30-40€, Tommy flag 15€ -> 25-35€, Carhartt Detroit 35€ -> 70-90€, Nuptse 45€ -> 75-100€.")
        else:
            await message.channel.send(f"🧠 Ricevuto {message.author.mention}. V26 {len(regole)} regole, solo maglione/felpa/giubbotto, no shorts/t-shirt base, max 60s 0 like. Se bidonata scrivi 'non è un affare'.")
        return

@bot.command()
async def config(ctx):
    cfg=carica_config()
    await ctx.send(f"V26 AFFARI VELOCI + CERVELLO | Regole {len(regole)} | {cfg.get('max_secondi_freschezza')}s max | 0 like | No shorts/t-shirt base | Visti {len(gia_visti)}")
@bot.command()
async def filtri(ctx):
    pref=carica_pref()
    uid=str(ctx.author.id)
    data=pref.get(uid,{"brands":[],"sizes":[],"blacklist_titoli":[]})
    await ctx.send(f"📋 Filtri: brands {data.get('brands',[])} | sizes {data.get('sizes',[])} | blacklist {len(data.get('blacklist_titoli',[]))} titoli")
@bot.command()
async def reset(ctx):
    pref=carica_pref()
    uid=str(ctx.author.id)
    if uid in pref:
        del pref[uid]
        salva_pref(pref)
    await ctx.send("✅ Filtri resettati, blacklist pulita.")

@tasks.loop(seconds=2.5)
async def controllo_vinted():
    global ultimo_affare
    try:
        cfg=carica_config(); sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        max_fresco=cfg.get("max_secondi_freschezza",60)
        pref=carica_pref()
        active_brands=set(); active_sizes=set()
        for data in pref.values():
            for b in data.get("brands",[]): active_brands.add(b.lower())
            for s in data.get("sizes",[]): active_sizes.add(s.lower())
        brands=list(set([r["brand"] for r in regole]))
        search_brands=list(active_brands) if active_brands else brands
        urls=[f"https://www.vinted.it/api/v2/catalog/items?search_text={b.replace(' ','%20')}&order=newest_first&per_page=20" for b in search_brands][:12]
        for url in urls:
            try:
                r=sess.get(url,headers=headers,timeout=10)
                if r.status_code==429: await asyncio.sleep(5); continue
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    gia_visti.add(iid)
                    cts=item.get("created_at_ts"); fav=item.get("favourite_count",0) or 0
                    try:
                        if not cts or (time.time()-float(cts))>max_fresco: continue
                    except: continue
                    if fav>0: continue
                    titolo=item.get("title",""); brand=item.get("brand_title",""); cond=item.get("status",""); size=item.get("size_title","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if prezzo<2 or prezzo>100: continue
                    if active_sizes:
                        sl=(size or "").lower()
                        if sl and not any(s in sl or sl in s for s in active_sizes): continue
                    if active_brands:
                        if not any(ab in (titolo+" "+brand).lower() for ab in active_brands): continue
                    tlow=titolo.lower()
                    is_blacklisted=False
                    for data in pref.values():
                        for bt in data.get("blacklist_titoli",[]):
                            if bt and len(bt)>=5 and bt in tlow:
                                is_blacklisted=True; break
                        if is_blacklisted: break
                    if is_blacklisted: continue
                    descrizione=item.get("description","")
                    rule=matches_curated(titolo,brand,descrizione,prezzo,size,cond,fav,cts)
                    if not rule:
                        if not descrizione:
                            try:
                                det=sess.get(f"https://www.vinted.it/api/v2/items/{iid}",headers=headers,timeout=7)
                                if det.status_code==200:
                                    descrizione=det.json().get("item",{}).get("description","")
                                    await asyncio.sleep(0.3)
                                    rule=matches_curated(titolo,brand,descrizione,prezzo,size,cond,fav,cts)
                            except: pass
                        if not rule: continue
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url","")
                    sec=int(time.time()-float(cts)) if cts else 0
                    # FIX RICHIESTO: ultimo_affare semplice
                    ultimo_affare = {"titolo": titolo, "id": iid, "prezzo": prezzo}
                    sell_ok=rule["sell_min"]>=30
                    emoji="🟣🔥" if rule["sell_max"]>=75 else "🔴🔥" if rule["sell_max"]>=50 else "💥🔥"
                    titolo_embed=f"{emoji} {rule['brand'].upper()} {rule['cat'].upper()} | {titolo[:45]} | {prezzo}€ -> {rule['sell_min']}-{rule['sell_max']}€"
                    color_note=f"🎨 {rule['color_source']}" if rule.get("has_color_ok") else "🎨 verifica foto"
                    desc=(f"⚡ **AFFARE VELOCE 0-60s 0 LIKE + CERVELLO** ⚡\n{titolo}\n\nBrand: {brand} ({rule['brand']})\nModello: {rule['cat']}\nTaglia: {size} ✅\nCond: {cond}\n{color_note} | OK {', '.join(rule['colori_ok'][:3])}\n⏱️ {sec}s fa | ❤️ {fav} (0 like)\n💰 BUY max {rule['buy_max']}€ | Prezzo: {prezzo}€\n💸 SELL REALE {rule['sell_min']}-{rule['sell_max']}€\n[🚀 PRENDI SUBITO - 60s]({link})")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        emb=discord.Embed(title=titolo_embed,description=desc,color=0x9b59b6 if rule["sell_max"]>=70 else 0xff0000)
                        if foto: emb.set_image(url=foto)
                        ping="@here ⚡ AFFARE VELOCE" if sell_ok else ""
                        await canale.send(content=ping,embed=emb)
                if len(gia_visti)%30==0: salva_visti()
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"scan err {e}"); continue
        salva_visti()
    except Exception as e:
        print(f"Errore scan: {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio V26 AFFARI VELOCI + CERVELLO + CHAT - ultimo_affare fix")
        bot.run(tok)
    else:
        print("❌ DISCORD_TOKEN mancante")
