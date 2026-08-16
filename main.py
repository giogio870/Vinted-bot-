# 🔥 VINTED SNIPER BOT V21 CLEAN - 500 RIGHE + CHAT DM FULL
import discord, asyncio, requests, statistics, json, os, io, re, time, random, threading, difflib, datetime
from discord.ext import commands, tasks
from PIL import Image, ImageEnhance
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE="filtri.json"; CONFIG_FILE="config.json"; CHAT_FILE="chat_storico.json"; VISTI_FILE="gia_visti.json"
gia_visti=set(); last_photo_per_user={}; cache_mercato={}; vinted_session=None; last_session_refresh=0
BRANDS_BUDGET=["lacoste","ralph lauren","dsquared","dsquared2","tommy hilfiger","fred perry","stone island","pokemon","charizard","psa","pikachu","nike","jordan","balenciaga","runner","dunk","polo"]
TUTTI=list(set(BRANDS_BUDGET))
CARD_KEYWORDS=["psa","topps","bowman","pokemon","charizard","refractor","graded","autograph","auto","/99","/25","/10","numbered","sapphire","chrome","piccolo","biglietto","carta"]
USER_AGENTS=["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36","Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"]
SNEAKER_MODELS=["air zoom vomero 5","vomero 5","vomero","air max 90","air max 95","air max 97","air max 1","air max plus","air force 1","dunk low","dunk high","jordan 1 low","jordan 1 high","jordan 1 mid","jordan 4","jordan 3","jordan 11","jordan 5","p-6000","990v3","990v6","530","9060","2002r","gel-1130","gel-nyc","gel-kayano","samba","gazelle","spezial","campus","yeezy 350","yeezy 700","ultraboost","shox","pegasus","structure","invincible","zoom fly","550","574","react","cortez","blazer","waffle","tiempo","phantom","mercurial","copa","predator","superstar","forum","pro model","nizza","stan smith","ultraboost 21","ultraboost 22"]
ABBIGLIAMENTO_MODELLI=["lacoste polo","ralph lauren polo","stone island vestaglia","stone island marina","stone island reflective","stone island nylon","stone island wool","dsquared2 hoodie","dsquared2 t-shirt","fred perry shirt","tommy hilfiger polo","armani exchange","ralph lauren sweater","ralph lauren hoodie","ralph lauren jacket","lacoste sweater","lacoste hoodie","north face puffer","north face jacket","carhartt jacket","patagonia fleece"]
COND_TOP=["nuovo con etichette","nuovo senza etichette","new with tags","new without tags","nuovo"]
COND_BUONE=["ottime","molto buono","very good","ottimo","eccellente","excellent"]
COND_MEDIE=["buone","buono","good","discrete"]
COND_BASSE=["sufficiente","fair","scarso"]
COND_EMOJI={"top":"✨🔥","buone":"✅💎","medie":"👌👕","basse":"⚠️👎","sconosciuta":"❓"}
COND_MULTIPLIER={"top":1.0,"buone":0.85,"medie":0.68,"basse":0.45,"sconosciuta":0.80}

app=Flask(__name__)
@app.route("/")
def home(): return "🔥 Bot V21 CLEAN — MAROB STYLE — 24H ALERT + DM CHAT"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def carica_config():
    default={"sotto_prezzo_min":22,"guadagno_mostro":32,"guadagno_super_mostro":45,"guadagno_banger":28,"spedizione":5,"max_secondi_freschezza":2,"min_cuori_validazione":12,"min_annunci_validati":5,"scan_brands":["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","psa 10","nike dunk","jordan 1","balenciaga runner"],"user_brands":["lacoste","ralph lauren","dsquared","dsquared2","stone island","pokemon","charizard","nike","jordan"],"max_price_per_brand":{"lacoste":35,"ralph lauren":40,"dsquared":60,"dsquared2":60,"stone island":100,"pokemon":150,"charizard":200,"psa 10":300,"nike dunk":80,"jordan 1":100}}
    if os.path.exists(CONFIG_FILE):
        try:
            import json
            with open(CONFIG_FILE,"r") as f: cfg=json.load(f); default.update(cfg); return default
        except: return default
    return default
def salva_config(cfg):
    import json
    with open(CONFIG_FILE,"w") as f: json.dump(cfg,f,indent=2)
def carica_filtri():
    if os.path.exists(FILTRI_FILE):
        try:
            import json
            with open(FILTRI_FILE,"r") as f: return json.load(f)
        except: return []
    return []
def salva_filtri(filtri):
    import json
    with open(FILTRI_FILE,"w") as f: json.dump(filtri,f,indent=2)
def carica_chat():
    if os.path.exists(CHAT_FILE):
        try:
            import json
            with open(CHAT_FILE,"r") as f: return json.load(f)
        except: return {}
    return {}
def salva_chat(ch):
    import json
    with open(CHAT_FILE,"w") as f: json.dump(ch,f,indent=2)
def carica_visti():
    global gia_visti
    if os.path.exists(VISTI_FILE):
        try:
            import json
            with open(VISTI_FILE,"r") as f: gia_visti=set(json.load(f))
        except: gia_visti=set()
def salva_visti():
    try:
        import json
        with open(VISTI_FILE,"w") as f: json.dump(list(gia_visti)[-5000:],f)
    except: pass

def get_session():
    global vinted_session, last_session_refresh
    now=time.time()
    if vinted_session is None or (now-last_session_refresh)>300:
        vinted_session=requests.Session()
        try:
            vinted_session.get("https://www.vinted.it",headers={"User-Agent":random.choice(USER_AGENTS)},timeout=10)
            last_session_refresh=now
        except: pass
    return vinted_session

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
        if b in tl: return b
    return ""
def is_conosciuto(titolo,brand):
    t=(titolo+" "+brand).lower()
    return any(x in t for x in ["lacoste","ralph","dsquared","stone","pokemon","charizard","psa","pikachu","nike","jordan","balenciaga","runner","dunk","polo"])
def is_card(titolo,brand):
    t=(titolo+" "+brand).lower()
    return any(k in t for k in CARD_KEYWORDS)
def detect_card_variant(titolo):
    tl=titolo.lower(); varianti=[]
    if "auto" in tl or "autograph" in tl: varianti.append("autografo")
    if "refractor" in tl: varianti.append("refractor")
    if "sapphire" in tl: varianti.append("sapphire")
    if "chrome" in tl: varianti.append("chrome")
    m=re.search(r'/(\d+)',tl)
    if m: varianti.append(f"numerata-{m.group(1)}")
    if "psa" in tl: varianti.append("psa")
    if "base" in tl: varianti.append("base")
    return "+".join(varianti) if varianti else "base"
def is_sneaker_brand(brand,titolo):
    t=(brand+" "+titolo).lower()
    return any(x in t for x in ["nike","adidas","jordan","new balance","nb","asics","reebok","yeezy","balenciaga","salomon","on running","hoka"])
def is_abbigliamento_brand(brand,titolo):
    t=(brand+" "+titolo).lower()
    return any(x in t for x in ["lacoste","ralph","stone","dsquared","fred","tommy","armani","north","carhartt","patagonia"])
def correggi_modello_sneaker(titolo):
    tl=titolo.lower(); parole=tl.split(); mm=None; ms=0
    for modello in SNEAKER_MODELS+ABBIGLIAMENTO_MODELLI:
        mp=modello.split()
        for i in range(len(parole)):
            fr=" ".join(parole[i:i+len(mp)+1])
            sc=difflib.SequenceMatcher(None,fr,modello).ratio()
            if sc>ms: ms=sc; mm=modello
    return mm if ms>=0.75 else None

def condizione_tier(status):
    s=status.lower().strip()
    if not s: return "sconosciuta"
    if any(s==c or c in s for c in COND_TOP): return "top"
    if any(s==c or c in s for c in COND_BUONE): return "buone"
    if any(s==c or c in s for c in COND_MEDIE): return "medie"
    if any(s==c or c in s for c in COND_BASSE): return "basse"
    return "sconosciuta"
def condizioni_simili(a,b):
    t1=condizione_tier(a); t2=condizione_tier(b)
    if t1=="sconosciuta" or t2=="sconosciuta": return True
    return t1==t2
def pulisci_prezzi(p):
    if len(p)<4: return p
    s=sorted(p); q1=s[len(s)//4]; q3=s[(len(s)*3)//4]; iqr=q3-q1; low=q1-1.5*iqr; high=q3+1.5*iqr
    f=[x for x in s if low<=x<=high and 3<=x<=500]
    return f if len(f)>=3 else s
def controlla_stabilita(p):
    if not p or len(p)<3: return False,"CAMPIONE_PICCOLO"
    mn=min(p); mx=max(p)
    if mn<=0: return False,"DATI_INVALIDI"
    rap=mx/mn
    if rap>5: return False,"RANGE_TROPPO_AMPIO"
    if rap>2.5: return True,"DATI_INSTABILI"
    med=statistics.median(p)
    try:
        dev=statistics.stdev(p) if len(p)>1 else 0
        if med>0 and dev/med>0.3: return True,"DATI_INSTABILI"
    except: pass
    return True,None

_cache={}
def get_cache(k):
    k=k.lower().strip()
    if k in _cache:
        r,ts=_cache[k]
        if time.time()-ts<1800: return r
        del _cache[k]
    return None
def set_cache(k,r):
    k=k.lower().strip(); _cache[k]=(r,time.time())
    if len(_cache)>200:
        now=time.time()
        for ck in list(_cache.keys()):
            if now-_cache[ck][1]>1800: del _cache[ck]

def analizza_mostro(titolo,brand_input,prezzo_acquisto=None,condizione_item="",brand_title_api="",size_title=""):
    cfg=carica_config()
    ck=f"{titolo}_{brand_input}_{condizione_item}_{size_title}"
    c=get_cache(ck)
    if c: return c
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        is_card_item=is_card(titolo,brand_input)
        min_cuori=cfg.get("min_cuori_validazione",12)
        mod=None
        if is_sneaker_brand(brand_input,titolo) or is_abbigliamento_brand(brand_input,titolo):
            mod=correggi_modello_sneaker(titolo)
            if mod is None: return None
        if is_card_item:
            var=detect_card_variant(titolo); search="%20".join(titolo.split()[:5])
            if var!="base": search=f"{search}%20{var.replace('+','%20')}"
        elif mod:
            search="%20".join((brand_input+" "+mod).split())
        else:
            search="%20".join(titolo.split()[:6])
        url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=30&order=relevance"
        r=sess.get(url,headers=headers,timeout=10)
        if r.status_code==429: time.sleep(2); return None
        tutti=[]
        for it in r.json().get("items",[]):
            p=it.get("price",{}).get("amount")
            try:
                if p and float(p)>0:
                    pv=float(p); st=it.get("status",""); fav=it.get("favourite_count",0) or 0; bt=it.get("brand_title",""); sz=it.get("size_title","")
                    tutti.append({"prezzo":pv,"status":st,"cuori":fav,"brand":bt,"size":sz})
            except: pass
        btarg=(brand_title_api or brand_input or "").lower().strip()
        if btarg:
            sb=[a for a in tutti if a["brand"].lower().strip()==btarg]
            if len(sb)>=4: tutti=sb
        tier=condizione_tier(condizione_item)
        if condizione_item:
            sc=[a for a in tutti if condizioni_simili(a["status"],condizione_item)]
            if len(sc)>=4: tutti=sc
        if size_title:
            sclean=size_title.lower().strip()
            ss=[a for a in tutti if a["size"].lower().strip()==sclean]
            if len(ss)>=4: tutti=ss
        if len(tutti)<5 and not is_card_item:
            search2="%20".join(titolo.split()[:3])
            url2=f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=30&order=relevance"
            r2=sess.get(url2,headers=headers,timeout=10)
            extra=[]
            for it in r2.json().get("items",[]):
                p=it.get("price",{}).get("amount")
                try:
                    if p and float(p)>0:
                        pv=float(p); st=it.get("status",""); fav=it.get("favourite_count",0) or 0; bt=it.get("brand_title",""); sz=it.get("size_title","")
                        extra.append({"prezzo":pv,"status":st,"cuori":fav,"brand":bt,"size":sz})
                except: pass
            if btarg:
                eb=[a for a in extra if a["brand"].lower().strip()==btarg]
                if len(eb)>=4: extra=eb
            if condizione_item:
                ec=[a for a in extra if condizioni_simili(a["status"],condizione_item)]
                if len(ec)>=4: extra=ec
            tutti=extra
        if not tutti: return None
        valid=[a for a in tutti if a["cuori"]>=min_cuori]
        if len(valid)<cfg.get("min_annunci_validati",5): valid=[a for a in tutti if a["cuori"]>=3]
        if len(valid)<cfg.get("min_annunci_validati",5): valid=tutti
        if condizione_item:
            vc=[a for a in valid if condizioni_simili(a["status"],condizione_item)]
            if len(vc)>=cfg.get("min_annunci_validati",3): valid=vc
        prezzi=pulisci_prezzi([a["prezzo"] for a in valid])
        if not prezzi or len(prezzi)<7: return None
        stab,flag=controlla_stabilita(prezzi)
        if not stab and flag=="RANGE_TROPPO_AMPIO": return None
        prezzi_ord=sorted(prezzi)
        idx=int(len(prezzi_ord)*0.35)
        val_rif=prezzi_ord[idx] if idx<len(prezzi_ord) else statistics.median(prezzi_ord)
        mult=COND_MULTIPLIER.get(tier,0.80)
        val_corr=round(val_rif*mult,2) if tier!="top" else val_rif
        res={"valore":round(val_rif,2),"valore_condizione":round(val_corr,2),"media":round(statistics.mean(prezzi),2),"min":round(min(prezzi),2),"max":round(max(prezzi),2),"count":len(prezzi),"count_totali":len(tutti),"stabile":stab,"flag":flag,"is_card":is_card_item,"validati_cuori":len([a for a in valid if a["cuori"]>=min_cuori]),"condizione":tier,"emoji_cond":COND_EMOJI.get(tier,"❓"),"multiplier":mult}
        set_cache(ck,res)
        return res
    except Exception as e:
        print(f"Errore: {e}")
        return None

cache_mercato={}
def analizza_mercato_vendita(titolo,use_cache=True):
    global cache_mercato
    k=titolo.lower().strip()
    if use_cache and k in cache_mercato:
        d,ts=cache_mercato[k]
        if time.time()-ts<600: return d
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        for n in [5,4,3,2]:
            terms=titolo.split()
            if len(terms)<n: continue
            search="%20".join(terms[:n])
            url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=30&order=relevance"
            r=sess.get(url,headers=headers,timeout=10)
            if r.status_code==429: time.sleep(2); continue
            prezzi=[]; pv=[]
            for it in r.json().get("items",[]):
                p=it.get("price",{}).get("amount")
                try:
                    if p and float(p)>0:
                        v=float(p); prezzi.append(v); fav=it.get("favourite_count",0) or 0
                        if fav>=5: pv.append(v)
                except: pass
            fonte=pv if len(pv)>=3 else prezzi
            if len(fonte)>=4:
                fonte=pulisci_prezzi(fonte)
                stab,flag=controlla_stabilita(fonte)
                fs=sorted(fonte)
                idx=int(len(fs)*0.35)
                vr=fs[idx] if idx<len(fs) else statistics.median(fs)
                res={"valore":round(vr,2),"media":round(statistics.mean(fonte),2),"min":round(min(fonte),2),"max":round(max(fonte),2),"count":len(fonte),"stabile":stab,"flag":flag,"validati":len(pv)}
                cache_mercato[k]=(res,time.time())
                return res
        return None
    except: return None

def genera_descrizione_vendita(nome,brand_detected=""):
    brand=brand_detected or detect_brand(nome)
    merc=analizza_mercato_vendita(nome)
    if merc:
        veloce=round(merc["valore"]*0.90,2); maxp=round(merc["valore"]*1.08,2)
    else: veloce=maxp=None
    titolo=nome.title()
    if brand and brand.lower() not in nome.lower(): titolo=f"{brand.title()} {titolo}"
    desc=f"🔥 {titolo} 🔥\n✅ Brand {brand.title() if brand else 'Originale'} 9/10\n📦 Spedizione 24h"
    return {"titolo_seo":titolo,"descrizione":desc,"prezzo_veloce":veloce,"prezzo_massimo":maxp,"mercato":merc,"brand":brand}

def studia_confronto(lista):
    ris=[]
    for ogg in lista:
        m=analizza_mercato_vendita(ogg)
        if m: ris.append({"nome":ogg,"mercato":m})
    ris=sorted(ris,key=lambda x: x["mercato"]["valore"] if x["mercato"] else 0,reverse=True)
    return ris

# =============================================================
# CHAT DM FULL - CON STORICO PERSISTENTE
# =============================================================

def risposta_chat_infinita(user_id, messaggio, ha_foto=False):
    msg_lower=messaggio.lower().strip()
    storico=carica_chat()
    user_history=storico.get(str(user_id), [])
    if messaggio.strip():
        user_history.append({"role":"user","content":messaggio,"time":str(datetime.datetime.now())})

    cfg=carica_config()
    brand_det=detect_brand(messaggio)

    # --- FOTO ---
    if ha_foto:
        nome=messaggio.strip() or "oggetto in foto"
        if len(nome)<5 or any(k in msg_lower for k in ["usa quella","quella foto","vedi l'immagine","gia mandata","quella"]):
            for h in reversed(user_history[:-1]):
                txt=h.get("content","")
                if len(txt)>5:
                    nome=txt
                    brand_det=detect_brand(txt) or brand_det
                    break
            if len(nome)<5:
                nome="oggetto in foto"

        result=genera_descrizione_vendita(nome, brand_det)
        merc=result.get("mercato")
        if merc:
            flag_str=f"\n⚠️ {merc['flag'].replace('_',' ')}" if merc.get("flag") else ""
            validati_str=f"\n❤️ {merc.get('validati',0)} validati (5+ cuori)" if merc.get("validati",0)>0 else ""
            card_str=""
            if is_card(nome, brand_det or ""):
                card_str=f"\n🃏 Carta: variante {detect_card_variant(nome)}"
            risposta=(
                f"📸 **{result['titolo_seo']}**\n"
                f"📊 Valore mercato: {merc['valore']}€ (range: {merc['min']}-{merc['max']}€ su {merc['count']} annunci)"
                f"{validati_str}{card_str}{flag_str}\n\n"
                f"⚡ Prezzo veloce: {result['prezzo_veloce']}€ | Max: {result['prezzo_massimo']}€\n\n"
                f"Vuoi la descrizione? Scrivi `!vendi {nome}`"
            )
        else:
            risposta="📸 Foto ricevuta! Non trovo abbastanza annunci validati. Dimmi brand e modello precisi. 🔍"

    # --- STATO BOT ---
    elif any(x in msg_lower for x in ["non trovo","sta a cerca","stai cercando","cerchi","sniper","offert","stato"]):
        risposta=(
            f"✅ Bot attivo 🔥\n"
            f"🔄 Scansione ogni 2s su {len(cfg['user_brands'])} brand\n"
            f"⏱️ Solo freschi (max {cfg['max_secondi_freschezza']}s)\n"
            f"❤️ Confronto con annunci {cfg['min_cuori_validazione']}+ cuori\n"
            f"🧐 Condizioni: ✨ Top 100% | ✅ Buone 85% | 👌 Medie 68% | ⚠️ Basse 45%\n"
            f"💰 Sotto prezzo min: {cfg['sotto_prezzo_min']}€\n"
            f"👀 Visti: {len(gia_visti)}"
        )

    # --- CONFRONTO ---
    elif any(x in msg_lower for x in ["secondo te","come e meglio","quale e meglio","consigliami","quale conviene","confronto"]):
        all_text=" ".join([h.get("content","") for h in user_history[-6:]]) + " " + messaggio
        oggetti=[]
        for b in ["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","nike dunk","jordan 1"]:
            if b in all_text.lower() and b not in oggetti:
                oggetti.append(b)
        if len(oggetti)<2:
            oggetti=["lacoste polo","ralph lauren polo","dsquared2 t-shirt","pokemon charizard"]
        risultati=studia_confronto(oggetti[:4])
        txt="🧠 **Confronto mercati:**\n\n"
        for i,r in enumerate(risultati):
            if r["mercato"]:
                flag_str=f" ⚠️ {r['mercato']['flag'].replace('_',' ')}" if r["mercato"].get("flag") else ""
                val_str=f" | ❤️ {r['mercato'].get('validati',0)} validati" if r["mercato"].get("validati",0)>0 else ""
                txt+=f"**{i+1}. {r['nome'].title()}** → {r['mercato']['valore']}€ ({r['mercato']['count']} annunci){val_str}{flag_str}\n"
        if risultati:
            txt+=f"\n👉 Top: {risultati[0]['nome'].title()} a {risultati[0]['mercato']['valore']}€ 🏆"
        risposta=txt

    # --- CONFIG ---
    elif any(x in msg_lower for x in ["filtr","guadagno","config","soglie","impostazioni"]):
        risposta=(
            f"⚙️ **Config V21 CLEAN:**\n"
            f"• Sotto prezzo min: {cfg['sotto_prezzo_min']}€\n"
            f"• Soglie: 💧🔥 {cfg['sotto_prezzo_min']}€ | 💥🔥 {cfg['guadagno_banger']}€ | 🔴🔥 {cfg['guadagno_mostro']}€ | 🟣🔥 {cfg['guadagno_super_mostro']}€\n"
            f"• Cuori min: {cfg['min_cuori_validazione']}\n"
            f"• Freschi max: {cfg['max_secondi_freschezza']}s\n"
            f"• Spedizione: {cfg['spedizione']}€\n"
            f"• Brand: {', '.join(cfg['user_brands'])}\n"
            f"• Visti: {len(gia_visti)}"
        )

    # --- DEFAULT ---
    else:
        if brand_det:
            m=analizza_mercato_vendita(messaggio)
            if m:
                flag_str=f"\n⚠️ {m['flag'].replace('_',' ')}" if m.get("flag") else ""
                validati_str=f"\n❤️ {m.get('validati',0)} validati" if m.get("validati",0)>0 else ""
                risposta=(
                    f"📊 **{messaggio.title()}**\n"
                    f"💰 Valore: {m['valore']}€ (range: {m['min']}-{m['max']}€ su {m['count']})"
                    f"{validati_str}{flag_str}\n\n"
                    f"Scrivi !vendi {messaggio} per descrizione ✍️"
                )
            else:
                risposta=f"Ho riconosciuto {brand_det.title()} 👀 ma non trovo abbastanza annunci validati. Dimmi il modello preciso. 🔍"
        else:
            risposta=(
                "🤖 Bot Vinted V21 🔥 CLEAN + DM\n"
                "Mandami una foto 📸 + nome per analisi prezzo\n"
                "Comandi: !vendi, !prezzo, !migliora, !config ✨\n"
                "Dimmi 'stato' per vedere se snipa ✅"
            )

    user_history.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())})
    if len(user_history)>30:
        user_history=user_history[-30:]
    storico[str(user_id)]=user_history
    salva_chat(storico)
    return risposta

@bot.event
async def on_ready():
    carica_visti(); cfg=carica_config()
    print(f"🔥 Bot V21 CLEAN + DM online {bot.user} | Cuori {cfg['min_cuori_validazione']}+ | Min {cfg['sotto_prezzo_min']}€ | Visti {len(gia_visti)}")
    if not controllo_vinted.is_running(): controllo_vinted.start()

@bot.event
async def on_message(message):
    if message.author==bot.user: return

    # Salva ultima foto per user
    if len(message.attachments)>0:
        last_photo_per_user[message.author.id]=message.attachments[0].url

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # DM: chat intelligente con foto
    if isinstance(message.channel, discord.DMChannel):
        ha_foto=len(message.attachments)>0
        if not ha_foto and any(k in message.content.lower() for k in ["quella foto","quella","vedi l'immagine","gia mandata","usa quella"]):
            if message.author.id in last_photo_per_user:
                ha_foto=True
        async with message.channel.typing():
            risposta=risposta_chat_infinita(message.author.id, message.content, ha_foto)
        await message.channel.send(risposta)
        return

    # Mention nel server
    if bot.user in message.mentions:
        ha_foto=len(message.attachments)>0
        risposta=risposta_chat_infinita(message.author.id, message.content, ha_foto)
        await message.channel.send(f"{message.author.mention} {risposta}")
        return

    await bot.process_commands(message)

@bot.command()
async def filtro(ctx, azione=None, *, args=""):
    filtri=carica_filtri()
    if azione=="add":
        parti=args.rsplit(" ",1)
        if len(parti)!=2:
            await ctx.send("❌ Usa: !filtro add lacoste 35 📝")
            return
        kw,pr=parti[0].lower(),parti[1]
        try: pr=float(pr)
        except: return
        filtri.append({"keyword":kw,"max":pr})
        salva_filtri(filtri)
        await ctx.send(f"✅ Aggiunto {kw} sotto {pr}€ 💰")
    else:
        cfg=carica_config()
        await ctx.send(f"⚙️ Sotto prezzo {cfg['sotto_prezzo_min']}€ | Cuori min {cfg['min_cuori_validazione']} ❤️ | Freschi {cfg['max_secondi_freschezza']}s ⏱️ | Visti {len(gia_visti)} 👀")

@bot.command()
async def config(ctx):
    cfg=carica_config()
    await ctx.send(f"⚙️ V21 ✨ | 💧🔥 {cfg['sotto_prezzo_min']}€ | 💥🔥 {cfg['guadagno_banger']}€ | 🔴🔥 {cfg['guadagno_mostro']}€ | 🟣🔥 {cfg['guadagno_super_mostro']}€ | Cuori: {cfg['min_cuori_validazione']}+ ❤️ | Spedizione {cfg['spedizione']}€ 📦 | Freschi {cfg['max_secondi_freschezza']}s ⏱️ | Visti {len(gia_visti)} 👀")

@bot.command()
async def prezzo(ctx,*,nome=""):
    if not nome: await ctx.send("💰 !prezzo lacoste polo 👕"); return
    m=analizza_mercato_vendita(nome)
    if m:
        flag_str=f" ⚠️ {m['flag'].replace('_',' ')}" if m.get("flag") else ""
        val_str=f" | ❤️ {m.get('validati',0)} validati" if m.get("validati",0)>0 else ""
        await ctx.send(f"💰 {nome} → {m['valore']}€ (range: {m['min']}-{m['max']}€ su {m['count']}){val_str}{flag_str} 📊")
    else: await ctx.send("❌ Non trovo abbastanza annunci validati 🔍")

@bot.command()
async def vendi(ctx,*,nome=""):
    if not nome: await ctx.send("✍️ !vendi lacoste polo + foto 📸"); return
    r=genera_descrizione_vendita(nome)
    embed=discord.Embed(title=f"📦 {r['titolo_seo'][:50]} ✨",description=f"```{r['descrizione'][:1000]}```",color=0x00ff88)
    if r["mercato"]:
        flag_str=f" ⚠️ {r['mercato']['flag'].replace('_',' ')}" if r["mercato"].get("flag") else ""
        val_str=f"\n❤️ {r['mercato'].get('validati',0)} validati" if r["mercato"].get("validati",0)>0 else ""
        embed.add_field(name="💰 Mercato 📊",value=f"{r['mercato']['valore']}€ (range: {r['mercato']['min']}-{r['mercato']['max']}€ su {r['mercato']['count']}){val_str}{flag_str}\n⚡ Veloce: {r['prezzo_veloce']}€ | Max: {r['prezzo_massimo']}€")
    await ctx.send(embed=embed)

@bot.command()
async def migliora(ctx):
    if not ctx.message.attachments: await ctx.send("📸 Mandami una foto con !migliora ✨"); return
    try:
        foto_url=ctx.message.attachments[0].url; r=requests.get(foto_url,timeout=15)
        img=Image.open(io.BytesIO(r.content))
        img=ImageEnhance.Contrast(img).enhance(1.2); img=ImageEnhance.Brightness(img).enhance(1.1); img=ImageEnhance.Sharpness(img).enhance(1.3)
        buf=io.BytesIO(); img.save(buf,format="JPEG",quality=95); buf.seek(0)
        await ctx.send(file=discord.File(buf,filename="migliorata.jpg"))
    except Exception as e: await ctx.send(f"❌ Errore: {e} 😢")

@tasks.loop(seconds=2)
async def controllo_vinted():
    try:
        cfg=carica_config(); sess=get_session()
        headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
        max_fresco=cfg.get("max_secondi_freschezza",2); sotto_min=cfg.get("sotto_prezzo_min",22)
        urls=[]
        for brand in cfg.get("user_brands",[])+cfg.get("scan_brands",[]):
            bq=brand.replace(" ","%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={bq}&order=newest_first&per_page=20")
        urls.append("https://www.vinted.it/api/v2/catalog/items?order=newest_first&per_page=40")
        urls=list(dict.fromkeys(urls))[:8]
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
                            eta=time.time()-float(cts)
                            if eta>max_fresco: gia_visti.add(iid); continue
                        except: pass
                    gia_visti.add(iid)
                    titolo=item.get("title",""); tlow=titolo.lower(); brand=item.get("brand_title",""); cond=item.get("status",""); size=item.get("size_title","")
                    try: prezzo=float(item.get("price",{}).get("amount"))
                    except: continue
                    b_det=detect_brand(titolo+" "+brand)
                    maxp=cfg.get("max_price_per_brand",{}); max_allowed=maxp.get(b_det,maxp.get(brand.lower(),80))
                    if prezzo>max_allowed or prezzo<5 or prezzo>350: continue
                    if not is_conosciuto(titolo,brand): continue
                    filtri=carica_filtri()
                    if filtri:
                        if not any(f["keyword"].lower() in tlow and prezzo<=f["max"] for f in filtri): continue
                    merc=analizza_mostro(titolo,brand,prezzo,cond,brand,size)
                    if not merc or merc["count"]<7: continue
                    valore=merc["valore_condizione"]; val_grez=merc["valore"]
                    diff=valore-prezzo; netto=diff-cfg["spedizione"]; sconto=(diff/valore*100) if valore>0 else 0; roi=(diff/prezzo*100) if prezzo>0 else 0
                    if diff<sotto_min: continue
                    flag=merc.get("flag"); cp=merc["count"]<10; cm=merc["count"]<7
                    diff_min=max(sotto_min,prezzo*0.8) if prezzo<50 else max(sotto_min,prezzo*0.45)
                    troppo=netto>2*prezzo and prezzo>10
                    insuff=diff<diff_min
                    nf=0
                    if cp: nf+=1
                    if cm: nf+=1
                    if troppo: nf+=1
                    if flag and flag not in ("DATI_INSTABILI","CAMPIONE_PICCOLO"): nf+=1
                    if nf>=2: continue
                    sb=sotto_min; sban=cfg.get("guadagno_banger",28); smos=cfg.get("guadagno_mostro",32); ssup=cfg.get("guadagno_super_mostro",45)
                    if flag=="DATI_INSTABILI": sb+=5; sban+=5; smos+=5; ssup+=5
                    if cp: sb+=3; sban+=3; smos+=3; ssup+=3
                    if insuff or netto<sb: continue
                    emoji_cond=merc.get("emoji_cond","❓"); cond_text=merc.get("condizione","sconosciuta"); mult=merc.get("multiplier",1.0)
                    if netto>=ssup:
                        emoji="🟣🔥🔥🔥💸💸💸"; ping="@everyone 🟣🔥 45€+ NETTI! 🚀"; color=0x9b59b6; fuoco="🔥🔥🔥 AFFARONE MOSTRUOSO 🔥🔥🔥"
                    elif netto>=smos:
                        emoji="🔴🔥🔥💸💸"; ping="@here 🔴🔥 32€+ NETTI! 💥"; color=0xff0000; fuoco="🔥🔥 MOSTRO 🔥🔥"
                    elif netto>=sban:
                        emoji="💥🔥💸"; ping=""; color=0x00ff88; fuoco="🔥 BANGER 🔥"
                    else:
                        emoji="💧🔥"; ping=""; color=0xffaa00; fuoco="🔥 BUON AFFARE"
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url",""); cuori=item.get("favourite_count",0) or 0
                    try:
                        sec=int(time.time()-float(item.get("created_at_ts",time.time())))
                        pub=f"{sec}s fa" if sec<60 else f"{sec//60} minuti fa"
                    except: pub="ora"
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        flagt=""
                        if flag: flagt+=f"\n⚠️ {flag.replace('_',' ')}"
                        if cp: flagt+="\n⚠️ CAMPIONE PICCOLO 🔍"
                        if troppo: flagt+="\n⚠️ VERIFICARE MANUALMENTE 👀"
                        if merc.get("is_card"): flagt+="\n🃏 Carta: verifica variante 🎴"
                        titolo_embed=f"{emoji} {titolo[:50].strip()} | {round(netto)}€ NETTI"
                        desc=(f"{fuoco}\n{titolo}\n\n🏷️ **Brand**\n{brand} ({b_det})\n\n📦 **Size**\n{size or 'Unica / Non specificata'}\n\n✨ **Condition**\n{emoji_cond} {cond} ({cond_text} x{mult})\n\n⏱️ **Published**\n{pub}\n\n⭐ **Reviews**\n❤️ {cuori} cuori item | {merc['count']} validati | {merc['validati_cuori']} con {cfg['min_cuori_validazione']}+ ❤️\n📊 Range: {merc['min']}-{merc['max']}€ su {merc['count_totali']} totali\n\n💰 **Price**\n{prezzo}€ (acquisto) + {cfg['spedizione']}€ sped → Rivendita corretta {valore}€ {emoji_cond} (grezzo {val_grez}€)\n**NETTO: {round(netto)}€** 💸 | Sotto prezzo {round(diff)}€ | Sconto {round(sconto)}% | ROI {round(roi)}%\n{flagt}\n\n[🚀 PRENDI SUBITO]({link})")
                        emb=discord.Embed(title=titolo_embed,description=desc,color=color)
                        if foto: emb.set_image(url=foto)
                        emb.set_footer(text=f"🔥 V21 {emoji_cond} {b_det} | Netto {round(netto)}€ | Cond: {cond_text} | {pub} | ❤️ {cuori}")
                        await canale.send(content=ping,embed=emb)
                if len(gia_visti)%20==0: salva_visti()
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"scan err {e}")
                continue
        salva_visti()
    except Exception as e:
        print(f"Errore scan: {e}")

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio V21 CLEAN + DM CHAT")
        bot.run(tok)
    else:
        print("❌ DISCORD_TOKEN mancante")
