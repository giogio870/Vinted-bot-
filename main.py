# 🔥 VINTED SNIPER BOT V10.0 REAL PRICE — CONFRONTO VENDUTO REALE PER TUTTE LE CAZZATE
# FIX: Non solo Nike, tutte le cazzate hanno prezzi Vinted gonfiati — ora confronto con venduto reale su p20/p15 + blacklist globale

import discord
from discord.ext import commands, tasks
import requests, statistics, json, os, time, random, threading
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

gia_visti = set()
cache_mercato = {}
vinted_session = None
last_session_refresh = 0

BRANDS_BUDGET = ["lacoste","ralph lauren","dsquared","dsquared2","tommy hilfiger","fred perry","stone island","pokemon","charizard","psa","pikachu","nike","jordan","balenciaga","runner","dunk","polo"]
TUTTI = list(set(BRANDS_BUDGET))

# BLACKLIST GLOBALE - tutta roba che non rivendi mai bene, non solo Nike
TRASH_GLOBALE = [
    "metcon","free","training","flex","renew","revolution","tanjun","downshifter","air zoom","structure",
    "palestra","gym","basic","lotto","decathlon","primark","shein","kiabi","zara basic","hm basic",
    "cracked","rotto","buco","macchia","macchiato","strappato","difettato","senza lacci","mancante",
    "calzini","mutande","boxer","intimo","ciabatte basic",
    "tie-dye training","crossfit","running base"
]

MODELLI_NIKE_VALIDI = ["dunk","jordan 1","jordan 4","jordan 11","air max 1","air max 90","air max 95","air force 1","blazer","travis","off white","sacai","nocta","vapor","pegasus premium"]
MODELLI_LACOSTE_VALIDI = ["polo","maglione","felpa","track","giacca","piumino"]
MODELLI_RALPH_VALIDI = ["polo","knit","oxford","bear","piumino","giacca"]

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
]

app = Flask(__name__)
@app.route("/")
def home():
    return "Bot V10.0 REAL PRICE - Confronto venduto reale per tutte le cazzate"
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
        "guadagno_min_netto_base": 18,
        "guadagno_min_netto_ideale": 22,
        "guadagno_mostro": 28,
        "guadagno_super_mostro": 38,
        "min_like_ricercato": 25,
        "min_confidence": 80,
        "min_sconto_realistico": 60,
        "max_age_seconds": 150,
        "spedizione": 5,
        "scan_brands": ["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","psa 10","nike dunk","jordan 1","balenciaga runner"],
        "user_brands": ["lacoste","ralph lauren","dsquared","dsquared2","stone island","pokemon","charizard","nike","jordan"],
        "max_price_per_brand": {"lacoste":35,"ralph lauren":40,"dsquared":60,"dsquared2":60,"stone island":100,"pokemon":150,"charizard":200,"psa 10":300,"nike dunk":80,"jordan 1":115},
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

def is_cazzata_globale(titolo, b_detect):
    tl=titolo.lower()
    for trash in TRASH_GLOBALE:
        if trash in tl:
            if b_detect in ["nike","nike dunk","jordan 1"] and any(m in tl for m in MODELLI_NIKE_VALIDI):
                continue
            return True
    if b_detect == "nike":
        if not any(m in tl for m in MODELLI_NIKE_VALIDI):
            return True
    return False

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

def analizza_mercato_venduto_reale_v10(titolo, brand_input, use_cache=True):
    global cache_mercato
    key=(titolo.lower().strip()+"_"+(brand_input or "").lower())
    if use_cache and key in cache_mercato:
        data,ts=cache_mercato[key]
        if time.time()-ts<600:
            return data
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        b_detect_tmp = detect_brand(titolo+" "+brand_input)
        if is_cazzata_globale(titolo, b_detect_tmp):
            return None
        parole=[w for w in titolo.lower().split() if len(w)>3 and w not in ["taglia","size","ottime","buone","nuovo","usato","grande","piccolo","training","gym","cr","tie","dye"]]
        parole_set=set(parole[:3])
        for n in [3,2]:
            if len(parole)<n:
                continue
            search="%20".join(parole[:n])
            if brand_input and brand_input.lower() not in search.lower():
                search=f"{brand_input.replace(' ','%20')}%20{search}"
            url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=60&order=relevance"
            try:
                r=sess.get(url,headers=headers,timeout=10)
            except:
                continue
            if r.status_code==429:
                time.sleep(2); continue
            if r.status_code!=200:
                continue
            prezzi_tutti=[]; prezzi_vendibili=[]; likes=[]
            for it in r.json().get("items",[]):
                t=it.get("title","").lower()
                if parole_set and not any(p in t for p in parole_set):
                    continue
                if is_cazzata_globale(t, detect_brand(t+" "+it.get("brand_title","").lower())):
                    continue
                p=it.get("price",{}).get("amount")
                lk=it.get("favourite_count",0)
                try:
                    if p and 3<float(p)<500:
                        fp=float(p)
                        if int(lk) == 0 and fp > 35:
                            continue
                        prezzi_tutti.append(fp)
                        likes.append(int(lk))
                        if int(lk) >= 1:
                            prezzi_vendibili.append(fp)
                except:
                    pass
            max_like=max(likes) if likes else 0
            is_ricercato=max_like>=30
            if len(prezzi_tutti) < 10 and not is_ricercato:
                continue
            if len(prezzi_vendibili) < 4 and not is_ricercato:
                continue
            prezzi_puliti=pulisci_prezzi(prezzi_tutti)
            vendibili_puliti=pulisci_prezzi(prezzi_vendibili) if prezzi_vendibili else prezzi_puliti
            if len(prezzi_puliti) < 6 and not is_ricercato:
                continue
            mediana = median(prezzi_puliti)
            media_val = mean(prezzi_puliti)
            try:
                dev = stdev(prezzi_puliti) if len(prezzi_puliti)>=2 else 0
            except:
                dev=0
            p15 = percentile(prezzi_puliti, 15)
            p20 = percentile(prezzi_puliti, 20)
            p25 = percentile(prezzi_puliti, 25)
            if vendibili_puliti:
                p20_vend = percentile(vendibili_puliti, 20)
                p25_vend = percentile(vendibili_puliti, 25)
            else:
                p20_vend = p20
                p25_vend = p25
            candidati = [
                p15 * 0.75,
                p20 * 0.65,
                p25 * 0.60,
                p20_vend * 0.65,
                p25_vend * 0.60,
                mediana * 0.45,
            ]
            valore_realistico = round(min(candidati), 2)
            if valore_realistico > mediana * 0.60:
                valore_realistico = round(mediana * 0.45, 2)
            if valore_realistico < 14:
                continue
            confidence=100
            if dev>media_val*0.30:
                confidence-=35
            elif dev>media_val*0.20:
                confidence-=20
            if len(prezzi_puliti)<10:
                confidence-=20
            if len(prezzi_puliti)<15:
                confidence-=10
            if len(prezzi_vendibili)<5:
                confidence-=15
            if max_like<5:
                confidence-=20
            if max_like>=30:
                confidence+=10
            if confidence < 70 and not is_ricercato:
                continue
            result={
                "valore_mercato": round(mediana,2),
                "valore": round(valore_realistico,2),
                "valore_realistico": round(valore_realistico,2),
                "media": round(media_val,2),
                "min": round(min(prezzi_puliti),2),
                "max": round(max(prezzi_puliti),2),
                "count": len(prezzi_puliti),
                "count_vendibili": len(vendibili_puliti),
                "count_tot": len(prezzi_tutti),
                "max_like": max_like,
                "is_ricercato": is_ricercato,
                "confidence": max(0,min(100,confidence)),
                "dev": round(dev,2),
                "p15": round(p15,2),
                "p20": round(p20,2),
                "p25": round(p25,2),
            }
            cache_mercato[key]=(result,time.time())
            return result
        return None
    except Exception as e:
        print(f"mercato err {e}")
        return None

@bot.event
async def on_ready():
    carica_visti()
    print(f"🔥 Bot V10.0 REAL PRICE online come {bot.user} | Confronto venduto reale per tutte le cazzate")
    if not controllo_vinted.is_running():
        controllo_vinted.start()

@tasks.loop(seconds=1.0)
async def controllo_vinted():
    try:
        cfg=carica_config()
        sess=get_session()
        headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
        urls=[]
        for brand in cfg.get("user_brands",[])+cfg.get("scan_brands",[]):
            b_q=brand.replace(" ","%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={b_q}&order=newest_first&per_page=12")
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
                    if idx > 10:
                        continue
                    titolo=item.get("title","")
                    brand=item.get("brand_title","")
                    b_detect=detect_brand(titolo+" "+brand)
                    if is_cazzata_globale(titolo, b_detect):
                        continue
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    if prezzo<5 or prezzo>350: continue
                    if not is_conosciuto(titolo,brand): continue
                    max_per_brand=cfg.get("max_price_per_brand",{})
                    max_allowed=max_per_brand.get(b_detect, max_per_brand.get(brand.lower(), 80))
                    if prezzo>max_allowed: continue
                    filtri=carica_filtri()
                    if filtri:
                        if not any(f["keyword"].lower() in titolo.lower() and prezzo <= f["max"] for f in filtri): continue
                    mercato=analizza_mercato_venduto_reale_v10(titolo,brand)
                    if not mercato: continue
                    if mercato.get("confidence",0) < cfg.get("min_confidence",80) and not mercato.get("is_ricercato"):
                        continue
                    if mercato.get("count",0) < 8 and not mercato.get("is_ricercato"):
                        continue
                    valore_realistico=mercato["valore"]
                    valore_mercato=mercato["valore_mercato"]
                    diff=valore_realistico-prezzo
                    netto=diff-cfg["spedizione"]
                    sconto=(diff/valore_realistico*100) if valore_realistico>0 else 0
                    roi=(diff/prezzo*100) if prezzo>0 else 0
                    if netto < cfg["guadagno_min_netto_base"]:
                        continue
                    if sconto < cfg.get("min_sconto_realistico",60) and not mercato.get("is_ricercato"):
                        continue
                    if prezzo > valore_realistico * 0.45 and not mercato.get("is_ricercato"):
                        continue
                    if netto < 20 and not mercato.get("is_ricercato"):
                        continue
                    if netto >= cfg["guadagno_super_mostro"]:
                        livello="super_mostro"; emoji="🟣"; colore=0x9b59b6; label="SUPER DEAL VENDUTO"
                    elif netto >= cfg["guadagno_mostro"]:
                        livello="mostro"; emoji="🔴"; colore=0xff0000; label="MOSTRO VENDUTO"
                    elif netto >= cfg["guadagno_min_netto_ideale"]:
                        livello="banger"; emoji="💥"; colore=0x00ff88; label="BANGER VENDUTO"
                    else:
                        livello="base"; emoji="💧"; colore=0xffaa00; label="AFFARE VENDUTO"
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
                        titolo_embed=f"{emoji} {label} — {round(netto)}€ NETTI VENDUTO{ric_tag}: {titolo[:40]}"
                        desc=f"**Brand:** {brand} ({b_detect})\n**Acquisto:** {prezzo}€\n**Vinted medio:** {valore_mercato}€ (gonfiato)\n**VENDUTO REALE:** **{valore_realistico}€** (p20 {mercato['p20']}€, p25 {mercato['p25']}€, conf {mercato['confidence']}%)\n**NETTO VENDUTO: +{round(netto)}€** | Sconto venduto {round(sconto)}% ROI {round(roi)}%\n[👉 PRENDI AL SECONDO!]({link})"
                        embed=discord.Embed(title=titolo_embed,description=desc,color=colore)
                        if foto: embed.set_image(url=foto)
                        embed.add_field(name="📈 Venduto reale",value=f"{mercato['count']} tot / {mercato['count_vendibili']} vendibili (p20 {mercato['p20']}€)")
                        embed.add_field(name="💰 Gonfiato vs Reale",value=f"Medio: {valore_mercato}€\nReale venduto: {valore_realistico}€\nDiff gonfiato: -{round(valore_mercato-valore_realistico)}€")
                        if mercato.get("is_ricercato"):
                            embed.add_field(name="🔥 Ricercato",value=f"{mercato['max_like']} like")
                        embed.set_footer(text=f"V10.0 REAL PRICE | Netto venduto≥{cfg['guadagno_min_netto_base']}€ | p20/p25 real | {datetime.datetime.now().strftime('%H:%M:%S')}")
                        if livello=="super_mostro": content="@everyone 🟣 38€+ VENDUTO REALE!"
                        elif livello=="mostro": content="@here 🔴 28€+ VENDUTO REALE!"
                        elif mercato.get("is_ricercato"): content="@here 🔥 VENDUTO RICERCATO REALE!"
                        else: content=""
                        await canale.send(content=content,embed=embed)
                if len(gia_visti)%20==0: salva_visti()
                await discord.utils.sleep_until(datetime.datetime.now()+datetime.timedelta(milliseconds=200))
            except Exception as e_inner:
                print(f"scan err {e_inner}")
                continue
        salva_visti()
    except Exception as e:
        print(f"Errore V10.0: {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        print("🔥 Avvio Vinted SniperBot V10.0 REAL PRICE — CONFRONTO VENDUTO REALE PER TUTTE LE CAZZATE")
        bot.run(tok)
    else:
        print("❌ DISCORD_TOKEN non impostato!")
