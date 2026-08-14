import discord
from discord.ext import commands, tasks
import requests, statistics, json, os, io, re, time, random
from PIL import Image, ImageEnhance
import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE = "filtri.json"
CONFIG_FILE = "config.json"
CHAT_FILE = "chat_storico.json"
VISTI_FILE = "gia_visti.json"

gia_visti = set()
last_photo_per_user = {}
cache_mercato = {}
vinted_session = None
last_session_refresh = 0

BRANDS_BUDGET = ["lacoste","ralph lauren","dsquared","dsquared2","tommy hilfiger","fred perry","stone island","pokemon","charizard","psa","pikachu","nike","jordan","balenciaga","runner","dunk","polo"]
TUTTI = list(set(BRANDS_BUDGET))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
]

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
        "sconto_min": 40,
        "roi_min": 45,
        "unico_fail": "netto < 16",
        "spedizione": 5,
        "autobuy": False,
        "autobuy_min_netto": 22,
        "scan_brands": ["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","psa 10","nike dunk","jordan 1","balenciaga runner"],
        "user_brands": ["lacoste","ralph lauren","dsquared","dsquared2","stone island","pokemon","charizard","nike","jordan"],
        "max_price_per_brand": {"lacoste":35,"ralph lauren":40,"dsquared":60,"dsquared2":60,"stone island":100,"pokemon":150,"charizard":200,"psa 10":300,"nike dunk":80,"jordan 1":100}
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

def salva_config(cfg):
    with open(CONFIG_FILE,"w") as f:
        json.dump(cfg,f,indent=2)

def carica_filtri():
    if os.path.exists(FILTRI_FILE):
        try:
            with open(FILTRI_FILE,"r") as f:
                return json.load(f)
        except:
            return []
    return []

def salva_filtri(f):
    with open(FILTRI_FILE,"w") as f2:
        json.dump(f,f2,indent=2)

def carica_chat():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE,"r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def salva_chat(ch):
    with open(CHAT_FILE,"w") as f:
        json.dump(ch,f,indent=2)

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
    if "islan" in tl or "stone" in tl:
        return "stone island"
    if "dsq" in tl or "dsquared" in tl:
        return "dsquared2"
    if "ralph" in tl:
        return "ralph lauren"
    if "lacoste" in tl:
        return "lacoste"
    if "charizard" in tl:
        return "charizard"
    if "psa" in tl:
        return "psa 10"
    if "pokemon" in tl or "pikachu" in tl:
        return "pokemon"
    if "jordan" in tl:
        return "jordan 1"
    if "dunk" in tl:
        return "nike dunk"
    for b in sorted(TUTTI,key=len,reverse=True):
        if b in tl:
            return b
    return ""

def is_conosciuto(titolo,brand):
    t=(titolo+" "+brand).lower()
    return any(x in t for x in ["lacoste","ralph","dsquared","stone","pokemon","charizard","psa","pikachu","nike","jordan","balenciaga","runner","dunk","polo"])

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

def analizza_mercato_vendita(titolo,use_cache=True):
    global cache_mercato
    key=titolo.lower().strip()
    if use_cache and key in cache_mercato:
        data,ts=cache_mercato[key]
        if time.time()-ts<600:
            return data
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        for n in [4,3,2]:
            terms=titolo.split()
            if len(terms)<n:
                continue
            search="%20".join(terms[:n])
            url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=40&order=relevance"
            r=sess.get(url,headers=headers,timeout=10)
            if r.status_code==429:
                time.sleep(2)
                continue
            prezzi=[]
            for it in r.json().get("items",[]):
                p=it.get("price",{}).get("amount")
                try:
                    if p and float(p)>0:
                        prezzi.append(float(p))
                except:
                    pass
            if len(prezzi)>=4:
                prezzi=pulisci_prezzi(prezzi)
                result={"valore":round(statistics.median(prezzi),2),"media":round(statistics.mean(prezzi),2),"min":round(min(prezzi),2),"max":round(max(prezzi),2),"count":len(prezzi)}
                cache_mercato[key]=(result,time.time())
                return result
        return None
    except:
        return None

def analizza_mostro(titolo,brand_input):
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        search="%20".join(titolo.split()[:3])
        url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=35"
        r=sess.get(url,headers=headers,timeout=10)
        prezzi=[]
        for it in r.json().get("items",[]):
            p=it.get("price",{}).get("amount")
            try:
                if p and float(p)>0:
                    prezzi.append(float(p))
            except:
                pass
        if len(prezzi)<3:
            search2="%20".join(titolo.split()[:2])
            url2=f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=35"
            r2=sess.get(url2,headers=headers,timeout=10)
            prezzi2=[float(i.get("price",{}).get("amount")) for i in r2.json().get("items",[]) if i.get("price",{}).get("amount")]
            if len(prezzi2)>len(prezzi):
                prezzi=prezzi2
        if len(prezzi)==0:
            return None
        prezzi=pulisci_prezzi(prezzi)
        if not prezzi:
            return None
        result={"valore":round(statistics.median(prezzi),2),"media":round(statistics.mean(prezzi),2),"min":round(min(prezzi),2),"max":round(max(prezzi),2),"count":len(prezzi),"confidenza_alta":len(prezzi)>=6}
        return result
    except:
        return None

def genera_descrizione_vendita(nome,brand_detected=""):
    brand=brand_detected or detect_brand(nome)
    merc=analizza_mercato_vendita(nome)
    if merc:
        veloce=round(merc["valore"]*0.90,2)
        maxp=round(merc["valore"]*1.08,2)
    else:
        veloce=maxp=None
    titolo=nome.title()
    if brand and brand.lower() not in nome.lower():
        titolo=f"{brand.title()} {titolo}"
    desc=f"🔥 {titolo} 🔥\n✅ Brand {brand.title() if brand else 'Originale'} 9/10\n📦 Spedizione 24h tracciata"
    return {"titolo_seo":titolo,"descrizione":desc,"prezzo_veloce":veloce,"prezzo_massimo":maxp,"mercato":merc,"brand":brand}

def studia_confronto(lista):
    ris=[]
    for ogg in lista:
        m=analizza_mercato_vendita(ogg)
        if m:
            ris.append({"nome":ogg,"mercato":m})
    ris=sorted(ris,key=lambda x: x["mercato"]["valore"] if x["mercato"] else 0, reverse=True)
    return ris

def risposta_chat_infinita(user_id,messaggio,ha_foto=False):
    msg_lower=messaggio.lower().strip()
    storico=carica_chat()
    user_history=storico.get(str(user_id),[])
    if messaggio.strip():
        user_history.append({"role":"user","content":messaggio,"time":str(datetime.datetime.now())})
    cfg=carica_config()
    brand_det=detect_brand(messaggio)

    if ha_foto:
        nome=messaggio.strip() or "oggetto in foto"
        if len(nome)<5 or any(k in msg_lower for k in ["usa quella","quella foto","vedi l'immagine","già mandata"]):
            for h in reversed(user_history[:-1]):
                txt=h.get("content","")
                if len(txt)>5:
                    nome=txt
                    brand_det=detect_brand(txt) or brand_det
                    break
            if len(nome)<5:
                nome="Lacoste polo"
                brand_det="lacoste"
        result=genera_descrizione_vendita(nome,brand_det)
        merc=result.get("mercato")
        if merc:
            netto=merc["valore"]-25
            risposta=f"📸 **{result['titolo_seo']}**\n💰 Vale **{merc['valore']}€** ({merc['min']}-{merc['max']}€ su {merc['count']})\n⚡ Veloce: {result['prezzo_veloce']}€ | Netto ~{round(netto,1)}€ {'✅ PASSA' if netto>=16 else '❌ UNICO FAIL <16€'}\n\nVuoi descrizione? `!vendi {nome}`"
        else:
            risposta=f"📸 Foto {nome} ricevuta! Dimmi taglia e ti dico prezzo!"

    elif any(x in msg_lower for x in ["non trovo","sta a cerca","stai cercando","cerchi","sniper","offert"]):
        risposta=f"""✅ **STO A CERCA BENE - V29 UNICO FAIL MODE** 🔥

**UNICO FAIL:** solo se netto < **{cfg['guadagno_min_netto_base']}€** → lo scarto, tutto il resto passa! Così non spamma ma trova fino a 30€!

🔄 Loop 1.5s su {len(cfg['user_brands'])} brand: {', '.join(cfg['user_brands'])}
👀 Visti: {len(gia_visti)}
💰 Min {cfg['guadagno_min_netto_base']}€ (unico fail) fino a {cfg['guadagno_super_mostro']}€ super mostro"""

    elif any(x in msg_lower for x in ["secondo te","come è meglio","quale è meglio","consigliami","quale conviene"]):
        all_text=" ".join([h.get("content","") for h in user_history[-6:]]) + " " + messaggio
        oggetti=[]
        for b in ["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","nike dunk","jordan 1"]:
            if b in all_text.lower() and b not in oggetti:
                oggetti.append(b)
        if len(oggetti)<2:
            oggetti=["lacoste polo","ralph lauren polo","dsquared2 t-shirt","pokemon charizard"]
        risultati=studia_confronto(oggetti[:4])
        txt="🧠 **STUDIO V29 UNICO FAIL:**\n\n"
        for i,r in enumerate(risultati):
            if r["mercato"]:
                txt+=f"**{i+1}. {r['nome'].title()}** → {r['mercato']['valore']}€ netto ~{round(r['mercato']['valore']-25,1)}€ {'✅' if r['mercato']['valore']-25>=16 else '❌ FAIL'}\n"
        if risultati:
            txt+=f"\n👉 **VINCITORE: {risultati[0]['nome'].title()}** - Margine fino a 30€!"
        risposta=txt

    elif any(x in msg_lower for x in ["filtr","guadagno","config","unico fail","fail"]):
        risposta=f"""⚙️ **V29 UNICO FAIL - FINALE:**
• **UNICO FAIL:** netto < {cfg['guadagno_min_netto_base']}€ → scartato, tutto il resto passa!
• Min {cfg['guadagno_min_netto_base']}€ | Ideale {cfg['guadagno_min_netto_ideale']}€ | Mostro {cfg['guadagno_mostro']}€ | Super {cfg['guadagno_super_mostro']}€ (fino a 30€)
• Brand: {', '.join(cfg['user_brands'])}
• Visti: {len(gia_visti)} | Sconto {cfg['sconto_min']}%"""

    else:
        risposta=f"V29 UNICO FAIL ONLINE! Min 16€ unico fail fino a 30€+! Dimmi `secondo te quale è meglio?`"

    user_history.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())})
    if len(user_history)>30:
        user_history=user_history[-30:]
    storico[str(user_id)]=user_history
    salva_chat(storico)
    return risposta

@bot.event
async def on_ready():
    carica_visti()
    cfg=carica_config()
    print(f"Bot V29 UNICO FAIL FINAL - Min {cfg['guadagno_min_netto_base']}€ unico fail fino a {cfg['guadagno_super_mostro']}€ - {bot.user}")
    controllo_vinted.start()

@bot.command()
async def filtro(ctx,azione=None,*,args=""):
    filtri=carica_filtri()
    if azione=="add":
        parti=args.rsplit(" ",1)
        if len(parti)!=2:
            await ctx.send("Usa: !filtro add lacoste 35")
            return
        kw,pr=parti[0].lower(),parti[1]
        try: pr=float(pr)
        except: return
        filtri.append({"keyword":kw,"max":pr})
        salva_filtri(filtri)
        await ctx.send(f"✅ Aggiunto {kw} sotto {pr}€")
    else:
        cfg=carica_config()
        await ctx.send(f"V29 UNICO FAIL: Min {cfg['guadagno_min_netto_base']}€ (unico fail) fino a {cfg['guadagno_super_mostro']}€ | Visti {len(gia_visti)}")

@bot.command()
async def config(ctx):
    cfg=carica_config()
    await ctx.send(f"⚙️ V29 UNICO FAIL: Min {cfg['guadagno_min_netto_base']}€ unico fail fino a {cfg['guadagno_super_mostro']}€ | Visti {len(gia_visti)}")

@bot.command()
async def prezzo(ctx,*,nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("!prezzo lacoste polo")
        return
    m=analizza_mercato_vendita(nome_oggetto)
    if m:
        netto=m["valore"]-25
        await ctx.send(f"💰 {nome_oggetto} → {m['valore']}€ netto ~{round(netto,1)}€ {'✅ PASSA' if netto>=16 else '❌ UNICO FAIL <16€'}")
    else:
        await ctx.send("Non trovo")

@bot.command()
async def vendi(ctx,*,nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("!vendi lacoste polo + foto")
        return
    r=genera_descrizione_vendita(nome_oggetto)
    embed=discord.Embed(title=f"📦 {r['titolo_seo'][:50]}",description=f"```{r['descrizione'][:1000]}```",color=0x00ff88)
    if r["mercato"]:
        embed.add_field(name="💰",value=f"{r['mercato']['valore']}€ netto ~{round(r['mercato']['valore']-25,1)}€")
    await ctx.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author==bot.user:
        return
    if len(message.attachments)>0:
        last_photo_per_user[message.author.id]=message.attachments[0].url
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    if isinstance(message.channel,discord.DMChannel):
        ha_foto=len(message.attachments)>0
        if not ha_foto and any(k in message.content.lower() for k in ["quella foto","quella","vedi l'immagine","già mandata","usa quella"]):
            if message.author.id in last_photo_per_user:
                ha_foto=True
        async with message.channel.typing():
            risposta=risposta_chat_infinita(message.author.id,message.content,ha_foto)
        await message.channel.send(risposta)
        return
    if bot.user in message.mentions:
        ha_foto=len(message.attachments)>0
        risposta=risposta_chat_infinita(message.author.id,message.content,ha_foto)
        await message.channel.send(f"{message.author.mention} {risposta}")
        return
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
                if r.status_code==429:
                    await discord.utils.sleep_until(datetime.datetime.now()+datetime.timedelta(seconds=5))
                    continue
                if r.status_code!=200:
                    continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti:
                        continue
                    gia_visti.add(iid)
                    titolo=item.get("title","")
                    titolo_low=titolo.lower()
                    brand=item.get("brand_title","")
                    try:
                        prezzo=float(item.get("price",{}).get("amount"))
                    except:
                        continue
                    max_per_brand=cfg.get("max_price_per_brand",{})
                    b_detect=detect_brand(titolo+" "+brand)
                    max_allowed=max_per_brand.get(b_detect, max_per_brand.get(brand.lower(), 80))
                    if prezzo>max_allowed:
                        continue
                    if prezzo<5 or prezzo>350:
                        continue
                    if not is_conosciuto(titolo,brand):
                        continue
                    filtri=carica_filtri()
                    if filtri:
                        if not any(f["keyword"].lower() in titolo_low and prezzo <= f["max"] for f in filtri):
                            continue
                    mercato=analizza_mostro(titolo,brand)
                    if not mercato:
                        continue
                    valore=mercato["valore"]
                    diff=valore-prezzo
                    netto=diff-cfg["spedizione"]
                    sconto=(diff/valore*100) if valore>0 else 0
                    roi=(diff/prezzo*100) if prezzo>0 else 0
                    # V29 - UNICO FAIL VERO: SOLO SE NETTO < 16
                    if netto < cfg["guadagno_min_netto_base"]:
                        continue  # UNICO FAIL
                    # Tutto il resto passa, livelli solo per emoji
                    if netto >= cfg["guadagno_super_mostro"]:
                        livello="super_mostro"
                    elif netto >= cfg["guadagno_mostro"]:
                        livello="mostro"
                    elif netto >= cfg["guadagno_min_netto_ideale"]:
                        livello="banger"
                    else:
                        livello="accettabile"
                    link=f"https://www.vinted.it/items/{iid}"
                    foto=item.get("photo",{}).get("url","")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages:
                                canale=ch
                                break
                        if canale:
                            break
                    if canale:
                        color=0x00ff88 if livello=="banger" else 0xffaa00 if livello=="accettabile" else 0xff0000 if livello=="mostro" else 0x9b59b6
                        titolo_embed=f"{'💥' if livello=='banger' else '🔴' if livello=='mostro' else '🟣' if livello=='super_mostro' else '💧'} {round(netto)}€ NETTI: {titolo[:45]}"
                        embed=discord.Embed(title=titolo_embed,description=f"**Brand:** {brand} ({b_detect})\n**Acquisto:** {prezzo}€ | **Rivendita:** {valore}€\n**NETTO: {round(netto)}€** | Sconto {round(sconto)}% ROI {round(roi)}%\n[👉 PRENDI!]({link})",color=color)
                        if foto:
                            embed.set_image(url=foto)
                        embed.set_footer(text=f"V29 UNICO FAIL | Netto {round(netto)}€ (min 16 fino a 30+) | {b_detect}")
                        content="@everyone 🟣 30€+!" if livello=="super_mostro" else "@here 🔴 22€+!" if livello=="mostro" else ""
                        await canale.send(content=content,embed=embed)
                if len(gia_visti)%20==0:
                    salva_visti()
                await discord.utils.sleep_until(datetime.datetime.now()+datetime.timedelta(milliseconds=300))
            except Exception as e_inner:
                print(f"scan err {e_inner}")
                continue
        salva_visti()
    except Exception as e:
        print(f"Errore V29: {e}")

from flask import Flask
app=Flask(__name__)
@app.route("/")
def home():
    return "Bot V29 FINAL UNICO FAIL - Min 16€ unico fail fino a 30€+ - Chat perfetta"
def run_flask():
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
import threading
threading.Thread(target=run_flask,daemon=True).start()

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        bot.run(tok)
