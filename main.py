# 🔥 VINTED SNIPER BOT V8.0 REALISTIC FAIL — DOPPIO FAIL + RIVENDITA REALE USATO + SOLO APPENA USCITI
# FIX DEL PROBLEMA: 20 annunci in 5 min, 3 buoni presi subito, 17 falsi per confronto prezzo medio
# ORA CONFRONTA CON PREZZO DI RIVENDITA REALISTICO USATO, NON LISTINO MEDIO

import discord
from discord.ext import commands, tasks
import requests, statistics, json, os, io, re, time, random, threading
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
    return "Bot V8.0 REALISTIC FAIL - Solo appena usciti + rivendita reale usato"
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
        "min_confidence": 70,
        "min_sconto_realistico": 38,
        "max_age_seconds": 300,
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
            json.dump(list(gia_visti)[-5000:],f)
    except:
        pass

def carica_portafoglio():
    if os.path.exists(PORTAFOGLIO_FILE):
        try:
            with open(PORTAFOGLIO_FILE,"r") as f:
                return json.load(f)
        except:
            pass
    return {"items": [], "totale_investito": 0, "totale_guadagnato": 0, "profit_reale": 0}

def salva_portafoglio(p):
    with open(PORTAFOGLIO_FILE,"w") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)

def detect_brand(text):
    tl=text.lower()
    if "islan" in tl or "stone" in tl: return "stone island"
    if "dsq" in tl or "dsquared" in tl: return "dsquared2"
    if "ralph" in tl: return "ralph lauren"
    if "lacoste" in tl: return "lacoste"
    if "charizard" in tl: return "charizard"
    if "psa" in tl: return "psa 10"
    if "pokemon" in tl or "pikachu" in tl: return "pokemon"
    if "jordan" in tl: return "jordan 1"
    if "dunk" in tl: return "nike dunk"
    for b in sorted(TUTTI,key=len,reverse=True):
        if b in tl:
            return b
    return ""

def is_conosciuto(titolo,brand):
    t=(titolo+" "+brand).lower()
    return any(x in t for x in BRANDS_BUDGET)

def pulisci_prezzi(prezzi):
    if len(prezzi)<4:
        return prezzi
    s=sorted(prezzi)
    q1=s[len(s)//4]
    q3=s[(len(s)*3)//4]
    iqr=q3-q1
    low=q1-1.5*iqr
    high=q3+1.5*iqr
    f=[p for p in s if low<=p<=high and 3<=p<=500]
    return f if len(f)>=3 else s

def percentile(data, perc):
    # perc 0-100
    if not data:
        return 0
    s=sorted(data)
    k = (len(s)-1) * (perc/100)
    f = int(k)
    c = min(f+1, len(s)-1)
    if f==c:
        return s[int(k)]
    d0 = s[f] * (c - k)
    d1 = s[c] * (k - f)
    return d0 + d1

def analizza_mercato_realistico_v8(titolo, brand_input, use_cache=True):
    global cache_mercato
    key=(titolo.lower().strip()+"_"+(brand_input or "").lower())
    if use_cache and key in cache_mercato:
        data,ts=cache_mercato[key]
        if time.time()-ts<600:
            return data
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        parole=[w for w in titolo.lower().split() if len(w)>3 and w not in ["taglia","size","ottime","buone","nuovo","usato","grande","piccolo"]]
        parole_set=set(parole[:3])
        for n in [3,2]:
            if len(parole)<n:
                continue
            search="%20".join(parole[:n])
            if brand_input and brand_input.lower() not in search.lower():
                search=f"{brand_input.replace(' ','%20')}%20{search}"
            url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=40&order=relevance"
            try:
                r=sess.get(url,headers=headers,timeout=10)
            except:
                continue
            if r.status_code==429:
                time.sleep(2); continue
            if r.status_code!=200:
                continue
            prezzi=[]; likes=[]; prezzi_con_like=[]
            count_venduti=0; count_attivi=0
            for it in r.json().get("items",[]):
                t=it.get("title","").lower()
                if parole_set and not any(p in t for p in parole_set):
                    continue
                # FILTRO BRAND REALE - deve contenere brand
                b_detect = detect_brand(t+" "+it.get("brand_title","").lower())
                if brand_input and brand_input.lower() not in t and b_detect != brand_input.lower():
                    # se cerco lacoste ma trovo altro, scarta
                    if brand_input.lower() in ["lacoste","ralph lauren","dsquared2","stone island"]:
                        if brand_input.lower() not in t:
                            continue
                p=it.get("price",{}).get("amount")
                lk=it.get("favourite_count",0)
                try:
                    if p and 3<float(p)<500:
                        fp=float(p)
                        prezzi.append(fp)
                        likes.append(int(lk))
                        if int(lk) >= 1:
                            prezzi_con_like.append(fp)
                        count_attivi+=1
                except:
                    pass
            max_like=max(likes) if likes else 0
            is_ricercato=max_like>=15
            # SERVONO ALMENO 6 comparabili per essere affidabile
            if len(prezzi) < 6 and not is_ricercato:
                continue
            if len(prezzi) >= 1:
                prezzi_puliti=pulisci_prezzi(prezzi)
                if len(prezzi_puliti) < 4 and not is_ricercato:
                    continue
                # MERCATO MEDIO (listino gonfiato)
                mediana = median(prezzi_puliti)
                media_val = mean(prezzi_puliti)
                try:
                    dev = stdev(prezzi_puliti) if len(prezzi_puliti)>=2 else 0
                except:
                    dev=0
                # RIVENDITA REALISTICA USATO - 40° percentile, non mediana!
                # Perché su Vinted il prezzo medio è gonfiato da chi non vende mai
                # Il prezzo a cui vende REALMENTE usato è più basso
                if prezzi_con_like and len(prezzi_con_like) >= 3:
                    # Se abbiamo prezzi con like, usiamo quelli = vendono davvero
                    realistico = median(pulisci_prezzi(prezzi_con_like))
                    # Ma ancora più realistico: 10% sotto
                    valore_realistico = round(realistico * 0.90, 2)
                else:
                    # Altrimenti 40° percentile del mercato = prezzo reale usato
                    p40 = percentile(prezzi_puliti, 40)
                    valore_realistico = round(p40 * 0.95, 2)

                # Se realistico è troppo vicino a mediana, mercato instabile
                if valore_realistico > mediana * 0.95:
                    valore_realistico = round(mediana * 0.85, 2)

                # CONFIDENCE
                confidence=100
                if dev>media_val*0.40:
                    confidence-=30
                elif dev>media_val*0.30:
                    confidence-=15
                if len(prezzi_puliti)<6:
                    confidence-=20
                elif len(prezzi_puliti)<8:
                    confidence-=10
                if max_like>=15:
                    confidence+=15
                if max_like>=30:
                    confidence+=10

                # FAIL: se confidence troppo bassa, mercato inaffidabile
                if confidence < 60 and not is_ricercato:
                    continue

                result={
                    "valore_mercato": round(mediana,2),
                    "valore": round(valore_realistico,2),  # QUESTO E' QUELLO REALISTICO USATO
                    "valore_realistico": round(valore_realistico,2),
                    "media": round(media_val,2),
                    "min": round(min(prezzi_puliti),2),
                    "max": round(max(prezzi_puliti),2),
                    "count": len(prezzi_puliti),
                    "count_tot": len(prezzi),
                    "max_like": max_like,
                    "is_ricercato": is_ricercato,
                    "confidence": max(0,min(100,confidence)),
                    "dev": round(dev,2),
                }
                cache_mercato[key]=(result,time.time())
                return result
        return None
    except Exception as e:
        print(f"mercato err {e}")
        return None

def is_appena_uscito(item):
    # Vinted da timestamp, se non c'è usiamo id come proxy (id alti = nuovi)
    # Controlla created_at
    try:
        # Prova vari campi possibili
        ts = item.get("created_at_ts") or item.get("created_at") or item.get("updated_at_ts")
        if ts:
            # ts può essere in secondi o ISO
            if isinstance(ts, (int, float)):
                age = time.time() - float(ts)
            else:
                # ISO string
                try:
                    dt = datetime.datetime.fromisoformat(str(ts).replace("Z","+00:00"))
                    age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds()
                except:
                    age = 0
            return age
        return 0  # se non troviamo timestamp, consideralo nuovo (verrà filtrato da gia_visti)
    except:
        return 0

# --- COMANDI BASE PORTAFOGLIO ETC ---
@bot.command()
async def prezzo(ctx,*,nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("!prezzo lacoste polo")
        return
    b=detect_brand(nome_oggetto)
    m=analizza_mercato_realistico_v8(nome_oggetto,b)
    if m:
        netto=m["valore"]-5
        ric=f" 🔥 RICERCATO {m['max_like']} like" if m.get("is_ricercato") else ""
        await ctx.send(f"💰 {nome_oggetto} → Mercato {m['valore_mercato']}€ | Reale usato {m['valore']}€ (conf {m['confidence']}%, {m['count']} comp) netto reale ~{round(netto,1)}€{ric} {'✅ PASSA' if netto>=16 else '❌ FAIL'}")
    else:
        await ctx.send("Non trovo mercato realistico affidabile ❌")

@bot.event
async def on_ready():
    carica_visti()
    print(f"🔥 Bot V8.0 REALISTIC online come {bot.user} | Solo appena usciti + rivendita reale")
    if not controllo_vinted.is_running():
        controllo_vinted.start()

@tasks.loop(seconds=1.0)
async def controllo_vinted():
    try:
        cfg=carica_config()
        sess=get_session()
        headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
        urls=[]
        # SOLO newest_first, per_page 20 = solo roba appena uscita al secondo
        for brand in cfg.get("user_brands",[])+cfg.get("scan_brands",[]):
            b_q=brand.replace(" ","%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={b_q}&order=newest_first&per_page=20")
        urls=list(dict.fromkeys(urls))[:10]
        for url in urls:
            try:
                r=sess.get(url,headers=headers,timeout=12)
                if r.status_code!=200: continue
                items = r.json().get("items",[])
                for idx, item in enumerate(items):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    gia_visti.add(iid)

                    # FAIL APPENA USCITO: solo primi 15 risultati = veramente nuovi al secondo
                    # Se è oltre posizione 15 in newest_first, è già vecchio
                    if idx > 15:
                        continue

                    # FAIL ETÀ: se ha timestamp e ha più di 5 min, scarta (non è appena uscito)
                    age = is_appena_uscito(item)
                    if age > cfg.get("max_age_seconds", 300) and age != 0:
                        continue

                    titolo=item.get("title","")
                    titolo_low=titolo.lower()
                    brand=item.get("brand_title","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if prezzo<5 or prezzo>350: continue
                    if not is_conosciuto(titolo,brand): continue
                    b_detect=detect_brand(titolo+" "+brand)
                    max_per_brand=cfg.get("max_price_per_brand",{})
                    max_allowed=max_per_brand.get(b_detect, max_per_brand.get(brand.lower(), 80))
                    if prezzo>max_allowed: continue

                    filtri=carica_filtri()
                    if filtri:
                        if not any(f["keyword"].lower() in titolo_low and prezzo <= f["max"] for f in filtri): continue

                    # ANALISI MERCATO REALISTICO
                    mercato=analizza_mercato_realistico_v8(titolo,brand)
                    if not mercato: continue

                    # DOPPIO FAIL 1: confidence bassa = mercato inaffidabile = scarta
                    if mercato.get("confidence",0) < cfg.get("min_confidence",70) and not mercato.get("is_ricercato"):
                        continue

                    # DOPPIO FAIL 2: pochi comparabili
                    if mercato.get("count",0) < 5 and not mercato.get("is_ricercato"):
                        continue

                    valore_realistico=mercato["valore"]  # QUESTO E' PREZZO REALE USATO
                    valore_mercato=mercato["valore_mercato"]
                    diff=valore_realistico-prezzo
                    netto=diff-cfg["spedizione"]
                    sconto=(diff/valore_realistico*100) if valore_realistico>0 else 0
                    roi=(diff/prezzo*100) if prezzo>0 else 0

                    # UNICO FAIL ORIGINALE: netto <16
                    if netto < cfg["guadagno_min_netto_base"]:
                        continue

                    # NUOVO FAIL REALISTICO: sconto minimo 38% su prezzo reale usato
                    if sconto < cfg.get("min_sconto_realistico",38) and not mercato.get("is_ricercato"):
                        continue

                    # NUOVO FAIL: se prezzo è troppo vicino a realistico (meno di 35% margine)
                    if prezzo > valore_realistico * 0.62 and not mercato.get("is_ricercato"):
                        continue

                    # Anti-fake
                    if sconto>75 and b_detect in ["stone island","balenciaga runner","psa 10"]:
                        continue

                    # LIVELLI
                    if netto >= cfg["guadagno_super_mostro"]:
                        livello="super_mostro"; emoji="🟣"; colore=0x9b59b6; label="SUPER DEAL"
                    elif netto >= cfg["guadagno_mostro"]:
                        livello="mostro"; emoji="🔴"; colore=0xff0000; label="MOSTRO"
                    elif netto >= cfg["guadagno_min_netto_ideale"]:
                        livello="banger"; emoji="💥"; colore=0x00ff88; label="BANGER"
                    else:
                        livello="base"; emoji="💧"; colore=0xffaa00; label="AFFARE"

                    link=f"https://www.vinted.it/items/{iid}"
                    foto=item.get("photo",{}).get("url","") if item.get("photo") else ""
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages:
                                canale=ch; break
                        if canale: break
                    if canale:
                        ric_tag=" 🔥 RICERCATO" if mercato.get("is_ricercato") else ""
                        titolo_embed=f"{emoji} {label} — {round(netto)}€ NETTI REALI{ric_tag}: {titolo[:40]}"
                        desc=f"**Brand:** {brand} ({b_detect})\n"
                        desc+=f"**Acquisto:** {prezzo}€\n"
                        desc+=f"**Mercato medio:** {valore_mercato}€ (gonfiato)\n"
                        desc+=f"**Reale usato:** **{valore_realistico}€** (conf {mercato['confidence']}%)"
                        if mercato.get("is_ricercato"): desc+=f" 🔥 {mercato['max_like']} like"
                        desc+=f"\n**NETTO REALE: +{round(netto)}€** | Sconto reale {round(sconto)}% ROI {round(roi)}%"
                        desc+=f"\n[👉 PRENDI AL SECONDO!]({link})"
                        embed=discord.Embed(title=titolo_embed,description=desc,color=colore)
                        if foto: embed.set_image(url=foto)
                        embed.add_field(name="📈 Comparabili reali",value=f"{mercato['count']} con like / {mercato['count_tot']} tot (conf {mercato['confidence']}%)")
                        embed.add_field(name="💰 Realistico vs Medio",value=f"Medio: {valore_mercato}€\nReale: {valore_realistico}€")
                        if mercato.get("is_ricercato"):
                            embed.add_field(name="🔥 Ricercato",value=f"{mercato['max_like']} like")
                        embed.set_footer(text=f"V8.0 REALISTIC | Netto reale≥{cfg['guadagno_min_netto_base']}€ | Solo appena usciti | {datetime.datetime.now().strftime('%H:%M:%S')}")
                        if livello=="super_mostro": content="@everyone 🟣 30€+ REALI!"
                        elif livello=="mostro": content="@here 🔴 22€+ REALI!"
                        elif mercato.get("is_ricercato"): content="@here 🔥 RICERCATO REALE!"
                        else: content=""
                        await canale.send(content=content,embed=embed)
                if len(gia_visti)%20==0: salva_visti()
                await discord.utils.sleep_until(datetime.datetime.now()+datetime.timedelta(milliseconds=200))
            except Exception as e_inner:
                print(f"scan err {e_inner}")
                continue
        salva_visti()
    except Exception as e:
        print(f"Errore V8.0: {e}")

from flask import Flask
app=Flask(__name__)
@app.route("/")
def home():
    return "Bot V8.0 REALISTIC FAIL - Solo appena usciti + rivendita reale usato"
def run_flask():
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
import threading
threading.Thread(target=run_flask,daemon=True).start()

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        print("🔥 Avvio Vinted SniperBot V8.0 REALISTIC FAIL — DOPPIO FAIL + RIVENDITA REALE USATO + SOLO APPENA USCITI")
        bot.run(tok)
    else:
        print("❌ DISCORD_TOKEN non impostato!")
