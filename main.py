# 🔥 VINTED SNIPER BOT V7.0 FINAL — UNICO FAIL + RICERCATO + PROFIT TRACKER + MULTI-PIATTAFORMA — FIXED UTF-8
#
# COSA FA:
# 1. Scansiona Vinted 24/7, ti allerta solo se netto >= 16€ (UNICO FAIL) 💧💥🔴🟣
# 2. RICERCATO: anche 1 solo annuncio con 15+ like → ti allerta 🔥
# 3. SELL-THROUGH RATE: conta venduti vs attivi = sa se vende veloce ⚡
# 4. MULTI-PIATTAFORMA: confronta prezzi anche su eBay (opzionale, gratis)
# 5. PROFIT TRACKER:!comprato link prezzo →!rivendi link →!venduto prezzo →!portafoglio
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

def analizza_mercato_v7(titolo, brand_input, use_cache=True):
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
            prezzi=[]; likes=[]
            prezzi_venduti=[]; count_venduti=0; count_attivi=0
            for it in r.json().get("items",[]):
                t=it.get("title","").lower()
                if parole_set and not any(p in t for p in parole_set):
                    continue
                p=it.get("price",{}).get("amount")
                lk=it.get("favourite_count",0)
                is_sold=it.get("is_sold",False)
                try:
                    if p and 3<float(p)<500:
                        fp=float(p)
                        if is_sold:
                            prezzi_venduti.append(fp)
                            count_venduti+=1
                        else:
                            prezzi.append(fp)
                            likes.append(int(lk))
                            count_attivi+=1
                except:
                    pass
            max_like=max(likes) if likes else 0
            is_ricercato=max_like>=15
            if len(prezzi)>=4 or (is_ricercato and len(prezzi)>=1):
                prezzi=pulisci_prezzi(prezzi)
                if len(prezzi)>=1:
                    med=median(prezzi)
                    media_val=mean(prezzi)
                    try:
                        dev=stdev(prezzi) if len(prezzi)>=2 else 0
                    except:
                        dev=0
                    confidence=100
                    if dev>media_val*0.5:
                        confidence-=20
                    if len(prezzi)<6:
                        confidence-=15
                    if is_ricercato:
                        confidence+=15
                    total=count_attivi+count_venduti
                    sell_through=round((count_venduti/total)*100,1) if total>0 else 0
                    if sell_through>=60: sell_label="⚡ Vende subito"
                    elif sell_through>=30: sell_label="🟢 Normale"
                    elif sell_through>0: sell_label="🟡 Lento"
                    else: sell_label="❓ N/D"
                    result={
                        "valore":round(med,2),
                        "media":round(media_val,2),
                        "min":round(min(prezzi),2),
                        "max":round(max(prezzi),2),
                        "count":len(prezzi),
                        "max_like":max_like,
                        "is_ricercato":is_ricercato,
                        "confidence":max(0,min(100,confidence)),
                        "dev":round(dev,2),
                        "venduti":count_venduti,
                        "attivi":count_attivi,
                        "sell_through":sell_through,
                        "sell_label":sell_label,
                    }
                    cache_mercato[key]=(result,time.time())
                    return result
        return None
    except Exception as e:
        print(f"mercato err {e}")
        return None

def cerca_ebay(query, max_results=5):
    if not EBAY_APP_ID:
        return None
    try:
        url = f"https://svcs.ebay.com/services/search/FindingService/v1"
        params = {
            "OPERATION-NAME": "findItemsByKeywords",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": EBAY_APP_ID,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "keywords": query,
            "pagination.entriesPerPage": str(max_results),
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code!= 200:
            return None
        data = r.json()
        items = data.get("findItemsByKeywordsResponse",[{}])[0].get("searchResult",[{}])[0].get("item",[])
        if not items:
            return None
        prezzi = []
        for it in items:
            prezzo = float(it.get("sellingStatus",[{}])[0].get("currentPrice",[{}])[0].get("__value__",0))
            if prezzo > 0:
                prezzi.append(prezzo)
        if not prezzi:
            return None
        return {
            "min": round(min(prezzi),2),
            "max": round(max(prezzi),2),
            "media": round(mean(prezzi),2),
            "count": len(prezzi),
        }
    except:
        return None

def analizza_foto_pil(foto_url):
    try:
        r=requests.get(foto_url,timeout=10)
        if r.status_code!=200: return None
        img=Image.open(io.BytesIO(r.content)).convert("RGB")
    except:
        return None
    result={}
    w,h=img.size
    result["risoluzione"]=f"{w}x{h}"
    result["alta_ris"]=w>=800 and h>=800
    result["bassa_ris"]=w<400 or h<400
    try:
        gray=img.convert("L")
        px=gray.load()
        edges=0; count=0
        step_w=max(1,w//100); step_h=max(1,h//100)
        for y in range(0,h-1,step_h):
            for x in range(0,w-1,step_w):
                try:
                    diff=abs(px[x,y]-px[x+1,y])+abs(px[x,y]-px[x,y+1])
                    edges+=diff; count+=1
                except:
                    pass
        edge_score=edges/max(count,1)
        result["blurry"]=edge_score<3.0
    except:
        result["blurry"]=False
    stat=ImageStat.Stat(img)
    brightness=mean(stat.mean)
    result["luminosita"]=round(brightness,1)
    result["troppo_buia"]=brightness<50
    result["troppo_luminosa"]=brightness>220
    score=50
    if result["alta_ris"]: score+=20
    elif result["bassa_ris"]: score-=15
    if not result["blurry"]: score+=15
    else: score-=20
    if 50<=brightness<=220: score+=10
    elif result["troppo_buia"]: score-=10
    elif result["troppo_luminosa"]: score-=5
    result["qualita_foto"]=max(0,min(100,score))
    problems=[]
    if result["blurry"]: problems.append("sfocata")
    if result["troppo_buia"]: problems.append("buia")
    if result["troppo_luminosa"]: problems.append("sovraesposta")
    if result["bassa_ris"]: problems.append("bassa ris")
    result["problemi"]=problems
    result["verdetto"]="✅ Buona" if not problems else "⚠️ "+", ".join(problems)
    return result

def migliora_foto(img_bytes):
    img=Image.open(io.BytesIO(img_bytes))
    img=ImageEnhance.Contrast(img).enhance(1.25)
    img=ImageEnhance.Brightness(img).enhance(1.12)
    img=ImageEnhance.Sharpness(img).enhance(1.35)
    img=ImageEnhance.Color(img).enhance(1.1)
    buf=io.BytesIO()
    img.save(buf,format="JPEG",quality=95)
    buf.seek(0)
    return buf

def genera_descrizione_vinted(titolo, brand, condizioni="Ottime condizioni", taglia=""):
    titolo_pulito=titolo.strip()
    taglie_str=f"\n📏 Taglia: {taglia}" if taglia else ""
    descrizione=f"""{titolo_pulito}

✅ {condizioni}
🏷️ {brand.title() if brand else 'Brand'}{taglie_str}
📦 Spedizione entro 24h
⚡ Acquisto protetto Vinted
💬 Per info o foto aggiuntive scrivimi pure!

#{titolo_pulito.replace(' ', ' #')}/#{brand.replace(' ', ' #') if brand else ''}"""
    return descrizione

@bot.command()
async def comprato(ctx, link:str, prezzo:float):
    p = carica_portafoglio()
    item_id = link.split("/")[-1].split("?")[0] if "/" in link else link
    titolo = ""
    brand = ""
    try:
        sess = get_session()
        r = sess.get(f"https://www.vinted.it/api/v2/items/{item_id}", headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            titolo = data.get("title","")
            brand = data.get("brand_title","")
    except:
        pass
    if not titolo:
        titolo = f"Item {item_id}"
    p["items"].append({
        "id": item_id,
        "link": link,
        "titolo": titolo,
        "brand": brand,
        "prezzo_acquisto": prezzo,
        "prezzo_vendita": None,
        "stato": "comprato",
        "data_acquisto": datetime.datetime.now().isoformat(),
        "data_vendita": None,
        "profit_reale": None,
    })
    p["totale_investito"] = round(p["totale_investito"] + prezzo, 2)
    salva_portafoglio(p)
    embed = discord.Embed(title="✅ Acquisto Registrato", color=0x00ff88)
    embed.add_field(name="📦 Articolo", value=titolo[:80])
    embed.add_field(name="💸 Prezzo", value=f"{prezzo}€")
    embed.add_field(name="🔗 Link", value=f"[Vedi]({link})")
    embed.add_field(name="💡 Prossimo step", value=f"Usa `!rivendi {link}` quando vuoi rivenderlo", inline=False)
    embed.set_footer(text=f"Portafoglio: investito {p['totale_investito']}€ | {len(p['items'])} articoli")
    await ctx.send(embed=embed)

@bot.command()
async def rivendi(ctx, link:str):
    p = carica_portafoglio()
    item_id = link.split("/")[-1].split("?")[0] if "/" in link else link
    item = None
    for it in p["items"]:
        if it["id"] == item_id and it["stato"] == "comprato":
            item = it
            break
    titolo = item["titolo"] if item else ""
    brand = item["brand"] if item else ""
    prezzo_acquisto = item["prezzo_acquisto"] if item else 0
    if not titolo:
        try:
            sess = get_session()
            r = sess.get(f"https://www.vinted.it/api/v2/items/{item_id}", headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                titolo = data.get("title","")
                brand = data.get("brand_title","")
        except:
            pass
    if not titolo:
        await ctx.send("❌ Non trovo l'articolo. Assicurati che il link sia corretto.")
        return
    mercato = analizza_mercato_v7(titolo, brand or detect_brand(titolo))
    embed = discord.Embed(title=f"🛍️ Assistente Rivendita", description=f"**{titolo[:60]}**", color=0x9b59b6)
    if mercato:
        valore = mercato["valore"]
        cfg = carica_config()
        sp = cfg.get("spedizione", 5)
        prezzo_ottimale = round(valore * 0.90, 2)
        prezzo_veloce = round(valore * 0.75, 2)
        prezzo_massimo = valore
        if prezzo_acquisto > 0:
            netto_ottimale = round(prezzo_ottimale - prezzo_acquisto - sp, 2)
            netto_veloce = round(prezzo_veloce - prezzo_acquisto - sp, 2)
            roi = round((netto_ottimale / prezzo_acquisto) * 100, 1)
        else:
            netto_ottimale = 0; netto_veloce = 0; roi = 0
        embed.add_field(name="💰 Mercato", value=f"Mediana: {valore}€\nRange: {mercato['min']}-{mercato['max']}€\n📊 {mercato['count']} comparabili (conf {mercato['confidence']}%)")
        embed.add_field(name="🎯 Prezzi suggeriti", value=f"📈 Massimo: {prezzo_massimo}€\n✅ Ottimale: {prezzo_ottimale}€\n⚡ Veloce: {prezzo_veloce}€")
        if prezzo_acquisto > 0:
            embed.add_field(name="💵 Profit stimato", value=f"Ottimale: +{netto_ottimale}€ (ROI {roi}%)\nVeloce: +{netto_veloce}€\nSpedizione: -{sp}€")
        if mercato.get("sell_through",0) > 0:
            embed.add_field(name="📊 Sell-through", value=f"{mercato['sell_through']}% — {mercato['sell_label']}")
        if mercato.get("is_ricercato"):
            embed.add_field(name="🔥 Ricercato", value=f"{mercato['max_like']} like → vende veloce!")
        ebay = cerca_ebay(titolo)
        if ebay:
            embed.add_field(name="🏷️ eBay", value=f"Min: {ebay['min']}€ | Max: {ebay['max']}€ | Media: {ebay['media']}€ su {ebay['count']}")
    descrizione = genera_descrizione_vinted(titolo, brand or detect_brand(titolo))
    embed.add_field(name="📝 Descrizione pronta", value=f"```\n{descrizione[:1000]}\n```", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def venduto(ctx, prezzo:float):
    p = carica_portafoglio()
    item = None
    for it in reversed(p["items"]):
        if it["stato"] == "comprato":
            item = it
            break
    if not item:
        await ctx.send("❌ Nessun articolo da vendere. Usa `!comprato link prezzo` prima.")
        return
    prezzo_acquisto = item["prezzo_acquisto"]
    sp = carica_config().get("spedizione", 5)
    profit = round(prezzo - prezzo_acquisto - sp, 2)
    roi = round((profit / prezzo_acquisto) * 100, 1) if prezzo_acquisto > 0 else 0
    item["prezzo_vendita"] = prezzo
    item["stato"] = "venduto"
    item["data_vendita"] = datetime.datetime.now().isoformat()
    item["profit_reale"] = profit
    p["totale_guadagnato"] = round(p["totale_guadagnato"] + prezzo, 2)
    p["profit_reale"] = round(p["profit_reale"] + profit, 2)
    salva_portafoglio(p)
    if profit >= 0:
        emoji = "💰"; color = 0x00ff88; txt = f"Guadagno: +{profit}€"
    else:
        emoji = "📉"; color = 0xff0000; txt = f"Perdita: {profit}€"
    embed = discord.Embed(title=f"✅ {emoji} Vendita Registrata", color=color)
    embed.add_field(name="📦 Articolo", value=item["titolo"][:80])
    embed.add_field(name="💸 Acquisto", value=f"{prezzo_acquisto}€")
    embed.add_field(name="💰 Vendita", value=f"{prezzo}€")
    embed.add_field(name="📦 Spedizione", value=f"-{sp}€")
    embed.add_field(name="💵 Profit REALE", value=f"**{txt}**")
    embed.add_field(name="📊 ROI", value=f"{roi}%")
    embed.set_footer(text=f"Portafoglio: investito {p['totale_investito']}€ | guadagno {p['totale_guadagnato']}€ | profit {p['profit_reale']}€")
    await ctx.send(embed=embed)

@bot.command()
async def portafoglio(ctx):
    p = carica_portafoglio()
    items = p.get("items", [])
    if not items:
        await ctx.send("📭 Portafoglio vuoto. Usa `!comprato link prezzo` per iniziare.")
        return
    comprati = [it for it in items if it["stato"] == "comprato"]
    venduti = [it for it in items if it["stato"] == "venduto"]
    profit_reale = p.get("profit_reale", 0)
    embed = discord.Embed(title="📊 Portafoglio", color=0x0099ff)
    embed.add_field(name="💰 Investito", value=f"{p.get('totale_investito',0)}€")
    embed.add_field(name="💸 Guadagnato", value=f"{p.get('totale_guadagnato',0)}€")
    embed.add_field(name="💵 Profit REALE", value=f"**{'+' if profit_reale>=0 else ''}{profit_reale}€**")
    embed.add_field(name="📦 Comprati (da vendere)", value=str(len(comprati)))
    embed.add_field(name="✅ Venduti", value=str(len(venduti)))
    embed.add_field(name="📊 Totale articoli", value=str(len(items)))
    if comprati:
        txt = ""
        for it in comprati[-5:]:
            txt += f"• {it['titolo'][:30]} — {it['prezzo_acquisto']}€\n"
        if len(comprati) > 5:
            txt += f"... e altri {len(comprati)-5}"
        embed.add_field(name="🛍️ Da vendere", value=txt, inline=False)
    if venduti:
        best = max(venduti, key=lambda x: x.get("profit_reale",0) or 0)
        worst = min(venduti, key=lambda x: x.get("profit_reale",0) or 0)
        embed.add_field(name="🏆 Best deal", value=f"{best['titolo'][:30]} → +{best.get('profit_reale',0)}€")
        if worst.get("profit_reale",0) < 0:
            embed.add_field(name="📉 Peggior deal", value=f"{worst['titolo'][:30]} → {worst.get('profit_reale',0)}€")
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    carica_visti()
    ai = "✅ eBay ON" if EBAY_APP_ID else "⚠️ eBay OFF (no EBAY_APP_ID)"
    print(f"🔥 Bot V7.0 FINAL online come {bot.user} | {ai} | 24H ALERT")
    print(f"📊 Portafoglio: {len(carica_portafoglio().get('items',[]))} articoli")
    if not controllo_vinted.is_running():
        controllo_vinted.start()

@bot.command()
async def prezzo(ctx,*,nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("!prezzo lacoste polo")
        return
    b=detect_brand(nome_oggetto)
    m=analizza_mercato_v7(nome_oggetto,b)
    if m:
        netto=m["valore"]-5
        ric=f" 🔥 RICERCATO {m['max_like']} like" if m.get("is_ricercato") else ""
        st=f" | {m['sell_label']}" if m.get("sell_through",0)>0 else ""
        await ctx.send(f"💰 {nome_oggetto} → {m['valore']}€ (conf {m['confidence']}%, {m['count']} comp{st}) netto ~{round(netto,1)}€{ric} {'✅ PASSA' if netto>=16 else '❌ FAIL'}")
    else:
        await ctx.send("Non trovo mercato")

@bot.command()
async def vendi(ctx,*,nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("!vendi lacoste polo")
        return
    b=detect_brand(nome_oggetto)
    m=analizza_mercato_v7(nome_oggetto,b)
    if m:
        embed=discord.Embed(title=f"📦 {nome_oggetto.title()[:50]}",color=0x00ff88)
        t=f"Mediana: {m['valore']}€\nRange: {m['min']}-{m['max']}€\n📊 {m['count']} comp (conf {m['confidence']}%)"
        if m.get("sell_through",0)>0: t+=f"\n📈 Sell-through: {m['sell_through']}% — {m['sell_label']}"
        if m.get("is_ricercato"): t+=f"\n🔥 RICERCATO {m['max_like']} like"
        t+=f"\n🎯 Vendi a: {round(m['valore']*0.90,2)}€\n⚡ Veloce: {round(m['valore']*0.75,2)}€\n📈 Max: {m['valore']}€"
        embed.add_field(name="💰 Mercato",value=t)
        ebay=cerca_ebay(nome_oggetto)
        if ebay:
            embed.add_field(name="🏷️ eBay",value=f"Min: {ebay['min']}€ | Max: {ebay['max']}€ | Media: {ebay['media']}€")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Non trovo mercato")

@bot.command()
async def migliora(ctx):
    if not ctx.message.attachments:
        await ctx.send("📷 Mandami una foto con `!migliora` per ottimizzarla per Vinted")
        return
    try:
        foto_url=ctx.message.attachments[0].url
        r=requests.get(foto_url,timeout=15)
        buf=migliora_foto(r.content)
        analisi=analizza_foto_pil(foto_url)
        embed=discord.Embed(title="📷 Foto Migliorata",color=0x00ff88)
        if analisi:
            embed.add_field(name="📊 Analisi",value=f"{analisi['verdetto']} ({analisi['qualita_foto']}/100)")
            embed.add_field(name="📐 Risoluzione",value=analisi["risoluzione"])
        embed.set_footer(text="Foto ottimizzata per Vinted")
        await ctx.send(file=discord.File(buf,filename="migliorata.jpg"),embed=embed)
    except Exception as e:
        await ctx.send(f"Errore: {e}")

@bot.command()
async def descrizione(ctx,*,nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("Usa: `!descrizione lacoste polo maglione verde taglia M`")
        return
    b=detect_brand(nome_oggetto)
    d=genera_descrizione_vinted(nome_oggetto, b or detect_brand(nome_oggetto))
    embed=discord.Embed(title="📝 Descrizione Pronta", description=f"```\n{d}\n```", color=0x00ff88)
    await ctx.send(embed=embed)

@bot.command()
async def foto(ctx):
    if not ctx.message.attachments:
        await ctx.send("Mandami una foto con!foto")
        return
    foto_url=ctx.message.attachments[0].url
    await ctx.send("🤖 Analizzo...")
    r=analizza_foto_pil(foto_url)
    if r:
        embed=discord.Embed(title="📸 Analisi Foto",color=0x0099ff)
        embed.add_field(name="Qualità",value=f"{r['verdetto']} ({r['qualita_foto']}/100)")
        embed.add_field(name="Risoluzione",value=r["risoluzione"])
        embed.add_field(name="Luminosità",value=str(r["luminosita"]))
        if r["problemi"]:
            embed.add_field(name="Problemi",value=", ".join(r["problemi"]),inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Non riesco ad analizzare")

@bot.command()
async def stats(ctx):
    cfg=carica_config()
    p=carica_portafoglio()
    await ctx.send(f"📊 V7.0 FINAL\n🔥 Visti: {len(gia_visti)}\n📦 Cache: {len(cache_mercato)}\n💼 Portafoglio: {len(p.get('items',[]))} articoli | Profit: {p.get('profit_reale',0)}€\n⚙️ Min netto: {cfg['guadagno_min_netto_base']}€\n❤️ Ricercato: {cfg['min_like_ricercato']}+ like\n🏷️ eBay: {'ON' if EBAY_APP_ID else 'OFF'}")

@bot.command()
async def config(ctx):
    cfg=carica_config()
    await ctx.send(f"⚙️ V7.0 FINAL: Min {cfg['guadagno_min_netto_base']}€ | Ricercato {cfg['min_like_ricercato']}+ like | eBay {'ON' if EBAY_APP_ID else 'OFF'} | Visti {len(gia_visti)}")

@bot.command()
async def stop(ctx):
    if controllo_vinted.is_running(): controllo_vinted.stop(); await ctx.send("⏹️ Fermata")
    else: await ctx.send("⏹️ Già ferma")

@bot.command()
async def resume(ctx):
    if not controllo_vinted.is_running(): controllo_vinted.start(); await ctx.send("▶️ Ripresa")
    else: await ctx.send("▶️ Già attiva")

@bot.command()
async def profit(ctx,*,arg=""):
    if not arg: await ctx.send("Usa:!profit 15 40"); return
    p=arg.split()
    if len(p)>=2:
        try:
            pa,pv=float(p[0]),float(p[1])
            sp=carica_config().get("spedizione",5)
            netto=round(pv-pa-sp,2)
            roi=round((netto/pa)*100,1) if pa>0 else 0
            await ctx.send(f"💸 {pa}€ → {pv}€ (sped: {sp}€)\n💵 Netto: +{netto}€\n📊 ROI: {roi}%\n{'✅ PASSA' if netto>=16 else '❌ FAIL'}")
        except: await ctx.send("❌ Numeri non validi")
    else: await ctx.send("❌ Usa:!profit 15 40")

@bot.event
async def on_message(message):
    if message.author==bot.user: return
    if len(message.attachments)>0:
        last_photo_per_user[message.author.id]=message.attachments[0].url
    await bot.process_commands(message)

@tasks.loop(seconds=1.2)
async def controllo_vinted():
    try:
        cfg=carica_config()
        sess=get_session()
        headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
        urls=[]
        for brand in cfg.get("user_brands",[])+cfg.get("scan_brands",[]):
            b_q=brand.replace(" ","%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={b_q}&order=newest_first&per_page=25")
        urls.append("https://www.vinted.it/api/v2/catalog/items?order=newest_first&per_page=40")
        urls=list(dict.fromkeys(urls))[:12]
        for url in urls:
            try:
                r=sess.get(url,headers=headers,timeout=12)
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    gia_visti.add(iid)
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
                    mercato=analizza_mercato_v7(titolo,brand)
                    if not mercato: continue
                    if not mercato.get("is_ricercato") and mercato.get("confidence",0) < cfg.get("min_confidence",50): continue
                    valore=mercato["valore"]
                    diff=valore-prezzo
                    netto=diff-cfg["spedizione"]
                    sconto=(diff/valore*100) if valore>0 else 0
                    roi=(diff/prezzo*100) if prezzo>0 else 0
                    if netto < cfg["guadagno_min_netto_base"]: continue
                    if sconto>75 and b_detect in ["stone island","balenciaga runner","psa 10"]: continue
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
                        titolo_embed=f"{emoji} {label} — {round(netto)}€ NETTI{ric_tag}: {titolo[:40]}"
                        desc=f"**Brand:** {brand} ({b_detect})\n"
                        desc+=f"**Acquisto:** {prezzo}€ | Mercato: {valore}€ (conf {mercato['confidence']}%)"
                        if mercato.get("is_ricercato"): desc+=f" 🔥 {mercato['max_like']} like"
                        desc+=f"\n**NETTO: +{round(netto)}€** | Sconto {round(sconto)}% ROI {round(roi)}%"
                        if mercato.get("sell_through",0)>0:
                            desc+=f"\n📊 Sell-through: {mercato['sell_through']}% — {mercato['sell_label']}"
                        desc+=f"\n[👉 PRENDI!]({link})"
                        embed=discord.Embed(title=titolo_embed,description=desc,color=colore)
                        if foto: embed.set_image(url=foto)
                        embed.add_field(name="📈 Comparabili",value=f"{mercato['count']} attivi, {mercato.get('venduti',0)} venduti (conf {mercato['confidence']}%)")
                        if mercato.get("sell_through",0)>0:
                            embed.add_field(name="📊 Sell-through",value=f"{mercato['sell_through']}% {mercato['sell_label']}")
                        if mercato.get("is_ricercato"):
                            embed.add_field(name="🔥 Ricercato",value=f"{mercato['max_like']} like")
                        embed.add_field(name="🏷️ Brand",value=b_detect.title() or brand)
                        if cfg.get("enable_ebay") and EBAY_APP_ID:
                            ebay=cerca_ebay(titolo[:50])
                            if ebay:
                                embed.add_field(name="🏷️ eBay",value=f"Min {ebay['min']}€ | Max {ebay['max']}€ | Media {ebay['media']}€")
                        embed.set_footer(text=f"V7.0 FINAL | Netto≥{cfg['guadagno_min_netto_base']}€ | 24H | {datetime.datetime.now().strftime('%H:%M:%S')}")
                        if livello=="super_mostro": content="@everyone 🟣 30€+!"
                        elif livello=="mostro": content="@here 🔴 22€+!"
                        elif mercato.get("is_ricercato"): content="@here 🔥 RICERCATO!"
                        else: content=""
                        await canale.send(content=content,embed=embed)
                if len(gia_visti)%20==0: salva_visti()
                await discord.utils.sleep_until(datetime.datetime.now()+datetime.timedelta(milliseconds=300))
            except Exception as e_inner:
                print(f"scan err {e_inner}")
                continue
        salva_visti()
    except Exception as e:
        print(f"Errore V7.0: {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        print("🔥 Avvio Vinted SniperBot V7.0 FINAL — UNICO FAIL + RICERCATO + PROFIT TRACKER + MULTI-PIATTAFORMA")
        bot.run(tok)
    else:
        print("❌ DISCORD_TOKEN non impostato!")
