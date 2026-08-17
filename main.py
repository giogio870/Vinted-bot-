# 🔥 VINTED SNIPER BOT V22 - FIXATO SVEGLIO - NO RISPOSTE AUTOMATICHE 🧠
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
PREF_FILE="preferenze_utenti.json"; LEARNING_FILE="learning.json"; PREZZI_FILE="prezzi_reali.json"
gia_visti=set(); last_photo_per_user={}; cache_mercato={}; vinted_session=None; last_session_refresh=0
ultimo_affare=None

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
COND_MULTIPLIER={"top":0.88,"buone":0.72,"medie":0.55,"basse":0.38,"sconosciuta":0.70}

app=Flask(__name__)
@app.route("/")
def home(): return "🔥 Bot V22 FIXATO SVEGLIO"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def carica_config():
    default={
        "sotto_prezzo_min":22,"guadagno_mostro":32,"guadagno_super_mostro":45,"guadagno_banger":28,
        "spedizione":5,"max_secondi_freschezza":90,"min_cuori_validazione":12,"min_annunci_validati":5,
        "scan_brands":["lacoste","ralph lauren","dsquared2","stone island","pokemon","charizard","psa 10","nike dunk","jordan 1","balenciaga runner"],
        "user_brands":["lacoste","ralph lauren","dsquared","dsquared2","stone island","pokemon","charizard","nike","jordan"],
        "max_price_per_brand":{"lacoste":30,"ralph lauren":35,"dsquared":50,"dsquared2":50,"stone island":80,"pokemon":120,"charizard":150,"psa 10":200,"nike dunk":70,"jordan 1":75,"jordan":65},
        "max_rivendita_reale":{"lacoste polo":22,"ralph lauren polo":25,"dsquared2 t-shirt":30,"jordan 1":85,"jordan 1 low":80,"jordan 1 high":95,"nike dunk":75,"dunk low":70,"dunk high":75,"stone island":90,"lacoste":25,"ralph lauren":30,"maglietta jordan":22,"jordan t-shirt":20,"jordan maglietta":20}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE,"r") as f: cfg=json.load(f); default.update(cfg); return default
        except: return default
    return default
def salva_config(cfg):
    with open(CONFIG_FILE,"w") as f: json.dump(cfg,f,indent=2)
def carica_filtri():
    if os.path.exists(FILTRI_FILE):
        try:
            with open(FILTRI_FILE,"r") as f: return json.load(f)
        except: return []
    return []
def salva_filtri(filtri):
    with open(FILTRI_FILE,"w") as f: json.dump(filtri,f,indent=2)
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
def carica_prezzi_reali():
    if os.path.exists(PREZZI_FILE):
        try:
            with open(PREZZI_FILE,"r") as f: return json.load(f)
        except: return {}
    return {}
def salva_prezzi_reali(p):
    with open(PREZZI_FILE,"w") as f: json.dump(p,f,indent=2)
def estrai_prezzo_corretto(testo):
    tl=testo.lower()
    patterns=[r'massimo\s*a?\s*(\d+)[\s€]*',r'max\s*a?\s*(\d+)[\s€]*',r'rivendo\s*a?\s*(\d+)',r'rivedere\s*a?\s*(\d+)',r'vale\s*max\s*(\d+)',r'vale\s*(\d+)\s*max',r'può\s*valere\s*(\d+)',r'max\s*(\d+)\s*euro',r'non\s*vale\s*piu\s*di\s*(\d+)',]
    for pat in patterns:
        m=re.search(pat, tl)
        if m:
            try:
                val=int(m.group(1))
                if 3 <= val <= 300: return val
            except: pass
    if "max" in tl or "massimo" in tl:
        m=re.search(r'(\d+)\s*€', tl)
        if m:
            try:
                val=int(m.group(1))
                if 3 <= val <= 300: return val
            except: pass
    return None
def get_prezzo_reale_appreso(titolo, brand):
    prezzi=carica_prezzi_reali()
    chiave=(brand+" "+titolo).lower()
    for k,v in prezzi.items():
        if k in chiave or chiave in k: return v
    for k,v in prezzi.items():
        if brand.lower() in k and brand.lower() in chiave: return v
    return None

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

def categoria_articolo(titolo):
    tl=titolo.lower()
    if any(x in tl for x in ["t-shirt","t shirt","tee","maglietta","maglia","shirt","polo"]):
        if "polo" in tl: return "polo"
        return "tshirt"
    if any(x in tl for x in ["felpa","hoodie","sweatshirt","crewneck"]): return "felpa"
    if any(x in tl for x in ["scarpa","sneaker","shoe","trainer","jordan 1","dunk low","dunk high","air max","air force","yeezy","new balance"]):
        if any(y in tl for y in ["t-shirt","maglietta","tee","polo"]): return "tshirt"
        return "scarpa"
    if any(x in tl for x in ["giacca","jacket","puffer","parka","coat"]): return "giacca"
    if any(x in tl for x in ["pantalone","pants","jeans","short"]): return "pantalone"
    if any(x in tl for x in ["carta","card","psa","charizard","pokemon"]): return "carta"
    return "altro"

def similarita_titoli(t1,t2):
    import difflib
    t1=t1.lower(); t2=t2.lower()
    parole1=set(t1.split()); parole2=set(t2.split())
    stop=["di","da","con","per","il","la","lo","a","e","in","nuovo","nuova","usato","taglia","size","uomo","donna","unisex"]
    parole1=parole1 - set(stop); parole2=parole2 - set(stop)
    if not parole1 or not parole2: return difflib.SequenceMatcher(None,t1,t2).ratio()
    intersezione=len(parole1 & parole2); unione=len(parole1 | parole2)
    jaccard=intersezione/unione if unione>0 else 0
    seq=difflib.SequenceMatcher(None,t1,t2).ratio()
    return (jaccard*0.6 + seq*0.4)

def analizza_mostro(titolo,brand_input,prezzo_acquisto=None,condizione_item="",brand_title_api="",size_title=""):
    prezzo_appreso = get_prezzo_reale_appreso(titolo, brand_input)
    cfg=carica_config()
    ck=f"{titolo}_{brand_input}_{condizione_item}_{size_title}"
    c=get_cache(ck)
    if c and not prezzo_appreso: return c
    sess=get_session()
    headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
    try:
        is_card_item=is_card(titolo,brand_input)
        min_cuori=cfg.get("min_cuori_validazione",12)
        cat_query=categoria_articolo(titolo)
        search_base = titolo
        if cat_query=="tshirt" and "t-shirt" not in titolo.lower() and "maglietta" not in titolo.lower(): search_base = titolo + " t-shirt"
        if cat_query=="scarpa" and "scarpa" not in titolo.lower(): search_base = titolo + " scarpa"
        mod=None
        if is_sneaker_brand(brand_input,titolo) or is_abbigliamento_brand(brand_input,titolo): mod=correggi_modello_sneaker(titolo)
        if is_card_item:
            var=detect_card_variant(titolo); search="%20".join(search_base.split()[:5])
            if var!="base": search=f"{search}%20{var.replace('+','%20')}"
        elif mod: search="%20".join((brand_input+" "+mod).split())
        else:
            parole=search_base.split()
            if brand_input and brand_input.lower() not in search_base.lower(): search="%20".join((brand_input+" "+" ".join(parole[:4])).split())
            else: search="%20".join(parole[:5])
        url=f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=40&order=relevance"
        r=sess.get(url,headers=headers,timeout=12)
        if r.status_code==429: time.sleep(2); return None
        tutti_raw=[]
        for it in r.json().get("items",[]):
            p=it.get("price",{}).get("amount")
            try:
                if p and float(p)>0:
                    pv=float(p)
                    if pv<2 or pv>800: continue
                    st=it.get("status",""); fav=it.get("favourite_count",0) or 0; bt=it.get("brand_title",""); sz=it.get("size_title",""); ttl=it.get("title","")
                    tutti_raw.append({"prezzo":pv,"status":st,"cuori":fav,"brand":bt,"size":sz,"titolo":ttl,"id":it.get("id")})
            except: pass
        filtrati_categoria=[]
        for a in tutti_raw:
            cat_a=categoria_articolo(a["titolo"])
            if cat_query=="tshirt" and cat_a=="scarpa": continue
            if cat_query=="scarpa" and cat_a=="tshirt": continue
            if cat_query=="polo" and cat_a=="scarpa": continue
            filtrati_categoria.append(a)
        tutti=filtrati_categoria if len(filtrati_categoria)>=4 else tutti_raw
        for a in tutti: a["sim"] = similarita_titoli(titolo, a["titolo"])
        tutti.sort(key=lambda x: (x["sim"]*0.7 + (min(x["cuori"],50)/50)*0.3), reverse=True)
        tutti_simili=[a for a in tutti if a["sim"]>=0.25]
        if len(tutti_simili)>=5: tutti=tutti_simili
        btarg=(brand_title_api or brand_input or "").lower().strip()
        if btarg:
            sb=[a for a in tutti if btarg in a["brand"].lower() or a["brand"].lower() in btarg or btarg.split()[0] in a["brand"].lower()]
            if len(sb)>=4: tutti=sb
        tier=condizione_tier(condizione_item)
        if size_title and size_title.strip():
            sclean=size_title.lower().strip()
            ss=[a for a in tutti if a["size"].lower().strip()==sclean]
            if len(ss)>=3: tutti=ss
        if condizione_item:
            sc=[a for a in tutti if condizioni_simili(a["status"],condizione_item)]
            if len(sc)>=4: tutti=sc
        tutti_per_cuori=sorted(tutti, key=lambda x: x["cuori"], reverse=True)
        valid=[a for a in tutti_per_cuori if a["cuori"]>=min_cuori]
        if len(valid)<cfg.get("min_annunci_validati",5): valid=[a for a in tutti_per_cuori if a["cuori"]>=5]
        if len(valid)<cfg.get("min_annunci_validati",5): valid=[a for a in tutti_per_cuori if a["cuori"]>=2]
        if len(valid)<3: valid=tutti_per_cuori[:10]
        prezzi_raw=[a["prezzo"] for a in valid]
        if not prezzi_raw: return None
        prezzi_puliti=pulisci_prezzi(prezzi_raw)
        if len(prezzi_puliti)>=3:
            med=statistics.median(prezzi_puliti)
            prezzi_puliti=[p for p in prezzi_puliti if med/3 <= p <= med*3]
        if not prezzi_puliti or len(prezzi_puliti)<5:
            if not is_card_item and len(tutti_raw)<10:
                search2="%20".join(titolo.split()[:3])
                url2=f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=30&order=relevance"
                r2=sess.get(url2,headers=headers,timeout=10)
                extra=[]
                for it in r2.json().get("items",[]):
                    p=it.get("price",{}).get("amount")
                    try:
                        if p and float(p)>0:
                            pv=float(p); st=it.get("status",""); fav=it.get("favourite_count",0) or 0; bt=it.get("brand_title",""); sz=it.get("size_title",""); ttl=it.get("title","")
                            if pv<2 or pv>800: continue
                            if cat_query=="tshirt" and categoria_articolo(ttl)=="scarpa": continue
                            if cat_query=="scarpa" and categoria_articolo(ttl)=="tshirt": continue
                            extra.append({"prezzo":pv,"status":st,"cuori":fav,"brand":bt,"size":sz,"titolo":ttl,"sim":similarita_titoli(titolo,ttl)})
                    except: pass
                extra=[e for e in extra if e["sim"]>=0.25]
                if extra:
                    extra_valid=[e for e in extra if e["cuori"]>=3]
                    if len(extra_valid)>=3: prezzi_puliti=pulisci_prezzi([e["prezzo"] for e in extra_valid])
        if not prezzi_puliti or len(prezzi_puliti)<5: return None
        stab,flag=controlla_stabilita(prezzi_puliti)
        if not stab and flag=="RANGE_TROPPO_AMPIO": return None
        prezzi_ord=sorted(prezzi_puliti)
        idx=int(len(prezzi_ord)*0.35)
        val_rif=prezzi_ord[idx] if idx<len(prezzi_ord) else statistics.median(prezzi_ord)
        valid_puliti=[a for a in valid if a["prezzo"] in prezzi_puliti]
        if valid_puliti:
            valid_puliti.sort(key=lambda x: x["cuori"], reverse=True)
            top_cuori=valid_puliti[:max(5, len(valid_puliti)//2)]
            if top_cuori:
                prezzi_top=[a["prezzo"] for a in top_cuori]
                val_top=statistics.median(prezzi_top)
                val_rif = (val_rif*0.6 + val_top*0.4)
        mult=COND_MULTIPLIER.get(tier,0.70)
        val_corr=round(val_rif*mult,2) if tier!="top" else val_rif
        tl_check=(titolo+" "+brand_input).lower()
        cfg_cap = carica_config()
        max_riv = cfg_cap.get("max_rivendita_reale",{})
        for k,cap in max_riv.items():
            if k in tl_check:
                if val_rif > cap:
                    val_rif = float(cap)
                    val_corr = float(cap) * COND_MULTIPLIER.get(tier,0.70) if tier!="top" else float(cap)
                break
        # FIX BUG: prima era is_card = is_card_item che shadowa la funzione
        is_luxury_flag = any(x in tl_check for x in ["balenciaga","louis vuitton","lv","prada","gucci","dior","fendi","off white","chrome hearts","psa 10","charizard"])
        is_card_flag = is_card_item
        if not is_luxury_flag and not is_card_flag:
            if "t-shirt" in tl_check or "t shirt" in tl_check or "maglietta" in tl_check or "polo" in tl_check:
                if val_rif > 28: val_rif = 24.0; val_corr = 24.0 * COND_MULTIPLIER.get(tier,0.70)
            elif "jordan 1" in tl_check or ("jordan" in tl_check and "t-shirt" not in tl_check and "maglietta" not in tl_check):
                if "scarpa" in tl_check or "shoe" in tl_check or "sneaker" in tl_check or "jordan 1" in tl_check:
                    if val_rif > 90: val_rif = 85.0; val_corr = 85.0 * COND_MULTIPLIER.get(tier,0.70) if tier!="top" else 85.0
            elif "jordan" in tl_check:
                if val_rif > 30: val_rif = 22.0; val_corr = 22.0 * COND_MULTIPLIER.get(tier,0.70)
        if prezzo_appreso:
            val_rif = float(prezzo_appreso)
            val_corr = float(prezzo_appreso) * COND_MULTIPLIER.get(tier,0.70) if tier!="top" else float(prezzo_appreso)
        res={"valore":round(val_rif,2),"valore_condizione":round(val_corr,2),"media":round(statistics.mean(prezzi_puliti),2),"min":round(min(prezzi_puliti),2),"max":round(max(prezzi_puliti),2),"count":len(prezzi_puliti),"count_totali":len(tutti_raw),"stabile":stab,"flag":flag,"is_card":is_card_item,"validati_cuori":len([a for a in valid if a["cuori"]>=min_cuori]),"condizione":tier,"emoji_cond":COND_EMOJI.get(tier,"❓"),"multiplier":mult,"prezzo_appreso": prezzo_appreso is not None, "categoria":cat_query}
        set_cache(ck,res)
        return res
    except Exception as e:
        print(f"Errore analizza_mostro: {e}")
        import traceback; traceback.print_exc()
        return None

#... resto del codice identico a prima per analizza_mercato_vendita, genera_descrizione_vendita...

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
    if merc: veloce=round(merc["valore"]*0.90,2); maxp=round(merc["valore"]*1.08,2)
    else: veloce=maxp=None
    titolo=nome.title()
    if brand and brand.lower() not in nome.lower(): titolo=f"{brand.title()} {titolo}"
    desc=f"🔥 {titolo} 🔥\n✅ Brand {brand.title() if brand else 'Originale'} 9/10\n📦 Spedizione 24h"
    return {"titolo_seo":titolo,"descrizione":desc,"prezzo_veloce":veloce,"prezzo_massimo":maxp,"mercato":merc,"brand":brand}

def risposta_chat_infinita(user_id, messaggio, ha_foto=False):
    global ultimo_affare
    ml=messaggio.lower().strip()
    storico=carica_chat()
    uh=storico.get(str(user_id),[])
    if messaggio.strip(): uh.append({"role":"user","content":messaggio,"time":str(datetime.datetime.now())})
    cfg=carica_config(); pref=carica_pref()
    up=pref.get(str(user_id),{"brands":[],"sizes":[],"temp_brand":None,"temp_size":None,"until":0,"liked":[],"disliked":[]})
    brand_det=detect_brand(messaggio)
    prezzo_corretto = estrai_prezzo_corretto(messaggio)
    if prezzo_corretto and ultimo_affare and any(x in ml for x in ["max","massimo","rivendo","rivedere","vale","vinted bot"]):
        prezzi_reali = carica_prezzi_reali()
        chiave = (ultimo_affare.get("brand_detected","") + " " + ultimo_affare.get("titolo","")).lower()[:80]
        chiave = re.sub(r'[^a-z0-9 ]', '', chiave).strip()
        prezzi_reali[chiave] = prezzo_corretto
        if "jordan" in chiave and ("t-shirt" in ml or "maglietta" in ml):
            prezzi_reali["jordan t-shirt"] = prezzo_corretto; prezzi_reali["jordan maglietta"] = prezzo_corretto
        salva_prezzi_reali(prezzi_reali)
        learning = carica_learning(); learning.append({"type":"price_correction","affare":ultimo_affare,"correct_value":prezzo_corretto,"user":str(user_id),"time":str(datetime.datetime.now()),"msg":messaggio}); salva_learning(learning)
        risposta=f"Cazzo hai ragione! 🙏 {ultimo_affare.get('valore','?')}€ era sparato, vale max {prezzo_corretto}€. Ho imparato!"
        uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if any(x in ml for x in ["resetta","azzera filtri","togli filtri","torna normale"]):
        pref[str(user_id)]={"brands":[],"sizes":[],"temp_brand":None,"temp_size":None,"until":0,"liked":[],"disliked":[]}; salva_pref(pref)
        risposta="Fatto ✅ Azzerato — tutti gli affari di nuovo."
        uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if any(x in ml for x in ["bravo bot","questi sono gli affari che cerco","vero affare","questo è un vero affare","grande bot"]):
        learning=carica_learning()
        if ultimo_affare:
            learning.append({"type":"good","affare":ultimo_affare,"user":str(user_id),"time":str(datetime.datetime.now())}); salva_learning(learning)
            up.setdefault("liked",[]).append(ultimo_affare.get("brand_detected","")); pref[str(user_id)]=up; salva_pref(pref)
            risposta=f"Grande! 🔥 Capito — {ultimo_affare['titolo'][:40]} netto {ultimo_affare['netto']}€. Cerco più roba simile."
        else: risposta="Grazie fra! Salvo lo stile e mando più roba simile"
        uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if any(x in ml for x in ["questo non è un affare","non è un affare","non mi interessa","non mi piace","prezzo troppo alto","troppo alto","costa troppo","non vale"]):
        learning=carica_learning(); prezzi_reali=carica_prezzi_reali()
        if ultimo_affare:
            learning.append({"type":"bad","affare":ultimo_affare,"user":str(user_id),"time":str(datetime.datetime.now()),"msg":messaggio}); salva_learning(learning)
            up.setdefault("disliked",[]).append(ultimo_affare.get("brand_detected",""))
            chiave_black = re.sub(r'[^a-z0-9 ]', '', (ultimo_affare.get("titolo","")[:40]).lower()).strip()
            up.setdefault("blacklist_titoli",[]).append(chiave_black)
            if len(up["blacklist_titoli"])>50: up["blacklist_titoli"]=up["blacklist_titoli"][-50:]
            prezzo_acq = ultimo_affare.get("prezzo", 0); vecchio_valore = ultimo_affare.get("valore", 0)
            nuovo_valore = min(vecchio_valore*0.55, prezzo_acq + 15) if prezzo_acq>0 else vecchio_valore*0.55
            nuovo_valore = max(8, int(nuovo_valore))
            chiave = re.sub(r'[^a-z0-9 ]', '', (ultimo_affare.get("brand_detected","") + " " + ultimo_affare.get("titolo","")).lower()[:80]).strip()
            prezzi_reali[chiave] = nuovo_valore; salva_prezzi_reali(prezzi_reali)
            risposta=f"Hai ragione! ❌ {ultimo_affare['titolo'][:35]} a {vecchio_valore}€ era alto. Corretto a {nuovo_valore}€ — non te lo segnalo più."
            pref[str(user_id)]=up; salva_pref(pref)
        else: risposta="Ok dimmi cosa non ti piace — marca o taglia?"
        uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if "taglia" in ml and any(x in ml for x in ["solo","voglio","dammi"]):
        m=re.search(r'taglia\s*([a-z0-9\.]+)',ml)
        if m:
            taglia=m.group(1).upper().strip(); is_temp="per un po" in ml or "per ora" in ml
            if is_temp: up["temp_size"]=taglia; up["until"]=time.time()+7200; risposta=f"Perfetto 👕 Per 2 ore solo taglia {taglia}"
            else:
                if taglia not in up.get("sizes",[]): up.setdefault("sizes",[]).append(taglia)
                up["temp_size"]=None; risposta=f"Chiaro! 📏 Da ora solo taglia {taglia}"
            pref[str(user_id)]=up; salva_pref(pref)
            uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if any(x in ml for x in ["solo","voglio solo","dammi solo"]):
        b=detect_brand(messaggio)
        if b:
            is_temp="per un po" in ml or "per ora" in ml
            if is_temp: up["temp_brand"]=b; up["until"]=time.time()+7200; risposta=f"Ok 👑 Per 2 ore solo {b.title()}"
            else:
                if b not in up.get("brands",[]): up.setdefault("brands",[]).append(b)
                up["temp_brand"]=None; risposta=f"Ricevuto! 🏷️ Da ora solo {b.title()}"
            pref[str(user_id)]=up; salva_pref(pref)
            uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if ha_foto:
        nome=messaggio.strip() or "oggetto in foto"
        result=genera_descrizione_vendita(nome,brand_det); merc=result.get("mercato")
        if merc: risposta=f"📸 {result['titolo_seo']} - {merc['valore']}€ range {merc['min']}-{merc['max']} su {merc['count']}"
        else: risposta="📸 Foto! Dimmi brand + modello + taglia."
        uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    if any(x in ml for x in ["stato","cosa fai","come funziona","logica","spiega"]):
        active=[]
        if up.get("temp_brand") and time.time()<up.get("until",0): active.append(f"Solo {up['temp_brand']} 2h")
        if up.get("temp_size") and time.time()<up.get("until",0): active.append(f"Solo taglia {up['temp_size']} 2h")
        if up.get("brands"): active.append(f"Brand {', '.join(up['brands'])}")
        if up.get("sizes"): active.append(f"Taglie {', '.join(up['sizes'])}")
        act="\n".join(active) if active else "Nessun filtro - tutti gli affari"
        risposta=f"✅ Bot 24H 🧠\n🆕 Solo appena usciti max {cfg['max_secondi_freschezza']}s\n💸 Solo affari min {cfg['sotto_prezzo_min']}€\n\nTuoi filtri:\n{act}\n👀 Visti {len(gia_visti)}"
        uh.append({"role":"assistant","content":risposta,"time":str(datetime.datetime.now())}); storico[str(user_id)]=uh[-30:]; salva_chat(storico); return risposta
    # SVEGLIO: se non è comando, NON rispondere automaticamente
    storico[str(user_id)]=uh[-30:]; salva_chat(storico)
    return None

@bot.event
async def on_ready():
    carica_visti(); cfg=carica_config()
    print(f"🔥 Bot V22 SVEGLIO online {bot.user} | Visti {len(gia_visti)}")
    if not controllo_vinted.is_running(): controllo_vinted.start()

@bot.event
async def on_message(message):
    if message.author==bot.user: return
    if len(message.attachments)>0: last_photo_per_user[message.author.id]=message.attachments[0].url
    if message.content.startswith("!"): await bot.process_commands(message); return
    if isinstance(message.channel, discord.DMChannel):
        ha_foto=len(message.attachments)>0
        if not ha_foto and any(k in message.content.lower() for k in ["quella foto","quella","vedi l'immagine","gia mandata","usa quella"]):
            if message.author.id in last_photo_per_user: ha_foto=True
        async with message.channel.typing():
            risposta=risposta_chat_infinita(message.author.id, message.content, ha_foto)
        if risposta: await message.channel.send(risposta)
        return
    if bot.user in message.mentions:
        risposta=risposta_chat_infinita(message.author.id, message.content, len(message.attachments)>0)
        if risposta: await message.channel.send(f"{message.author.mention} {risposta}")
        return
    await bot.process_commands(message)

@bot.command()
async def config(ctx):
    cfg=carica_config()
    await ctx.send(f"⚙️ V22 SVEGLIO | 💧🔥 {cfg['sotto_prezzo_min']}€ | 💥🔥 {cfg['guadagno_banger']}€ | 🔴🔥 {cfg['guadagno_mostro']}€ | 🟣🔥 {cfg['guadagno_super_mostro']}€ | 👀 {len(gia_visti)}")
@bot.command()
async def resetta(ctx):
    pref=carica_pref()
    pref[str(ctx.author.id)]={"brands":[],"sizes":[],"temp_brand":None,"temp_size":None,"until":0,"liked":[],"disliked":[]}
    salva_pref(pref)
    await ctx.send("Azzerato ✅ Tutti gli affari")

@tasks.loop(seconds=2.5)
async def controllo_vinted():
    global ultimo_affare
    try:
        cfg=carica_config(); sess=get_session()
        headers={"User-Agent":random.choice(USER_AGENTS),"Accept":"application/json","Referer":"https://www.vinted.it/"}
        max_fresco=cfg.get("max_secondi_freschezza",2); sotto_min=cfg.get("sotto_prezzo_min",22)
        pref=carica_pref()
        active_brands=set(); active_sizes=set(); now=time.time()
        for data in pref.values():
            if data.get("temp_brand") and now < data.get("until",0): active_brands.add(data["temp_brand"].lower())
            if data.get("temp_size") and now < data.get("until",0): active_sizes.add(data["temp_size"].lower())
            for b in data.get("brands",[]): active_brands.add(b.lower())
            for s in data.get("sizes",[]): active_sizes.add(s.lower())
        urls=[]
        search_brands = list(active_brands) if active_brands else cfg.get("user_brands",[])+cfg.get("scan_brands",[])
        for brand in search_brands:
            bq=brand.replace(" ","%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={bq}&order=newest_first&per_page=20")
        urls.append("https://www.vinted.it/api/v2/catalog/items?order=newest_first&per_page=40")
        urls=list(dict.fromkeys(urls))[:10]
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
                    if active_sizes:
                        sl=size.lower()
                        if sl and not any(s in sl or sl in s for s in active_sizes): continue
                    if active_brands:
                        if not any(ab in (titolo+" "+brand+" "+b_det).lower() for ab in active_brands): continue
                    is_blacklisted=False
                    for data in pref.values():
                        for bt in data.get("blacklist_titoli",[]):
                            if bt and len(bt)>=5 and bt in tlow: is_blacklisted=True; break
                        if is_blacklisted: break
                        for dis in data.get("disliked",[]):
                            if dis and len(dis)>=3 and dis.lower() in (titolo+" "+brand).lower():
                                if len(dis)>=4 and dis.lower() in tlow: is_blacklisted=True
                    if is_blacklisted: continue
                    merc=analizza_mostro(titolo,brand,prezzo,cond,brand,size)
                    if not merc or merc["count"]<4: continue
                    valore=merc["valore_condizione"]; diff=valore-prezzo; netto=diff-cfg["spedizione"]
                    if diff<sotto_min: continue
                    if netto< sotto_min: continue
                    emoji_cond=merc.get("emoji_cond","❓")
                    if netto>=cfg["guadagno_super_mostro"]: emoji="🟣🔥🔥🔥💸💸💸"; ping="@everyone 🟣🔥 45€+ NETTI! 🚀"; color=0x9b59b6; fuoco="🔥🔥🔥 AFFARONE MOSTRUOSO 🔥🔥🔥"
                    elif netto>=cfg["guadagno_mostro"]: emoji="🔴🔥🔥💸💸"; ping="@here 🔴🔥 32€+ NETTI! 💥"; color=0xff0000; fuoco="🔥🔥 MOSTRO 🔥🔥"
                    elif netto>=cfg["guadagno_banger"]: emoji="💥🔥💸"; ping=""; color=0x00ff88; fuoco="🔥 BANGER 🔥"
                    else: emoji="💧🔥"; ping=""; color=0xffaa00; fuoco="🔥 BUON AFFARE"
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url",""); cuori=item.get("favourite_count",0) or 0
                    try:
                        sec=int(time.time()-float(item.get("created_at_ts",time.time())))
                        pub=f"{sec}s fa" if sec<60 else f"{sec//60} minuti fa"
                    except: pub="ora"
                    ultimo_affare={"id":iid,"titolo":titolo,"brand":brand,"brand_detected":b_det,"size":size,"prezzo":prezzo,"valore":valore,"netto":round(netto),"link":link}
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        titolo_embed=f"{emoji} {titolo[:50].strip()} | {round(netto)}€ NETTI"
                        desc=(f"{fuoco}\n{titolo}\n\n🏷️ Brand {brand} ({b_det})\n📦 Size {size or 'Unica'}\n✨ Condition {emoji_cond} {cond}\n⏱️ Published {pub}\n⭐ Reviews ❤️ {cuori} | {merc['count']} validati\n💰 Price {prezzo}€ + {cfg['spedizione']}€ → {valore}€\nNETTO {round(netto)}€ 💸\n[🚀 PRENDI SUBITO]({link})")
                        emb=discord.Embed(title=titolo_embed,description=desc,color=color)
                        if foto: emb.set_image(url=foto)
                        await canale.send(content=ping,embed=emb)
                if len(gia_visti)%20==0: salva_visti()
                await asyncio.sleep(random.uniform(0.25,0.7))
            except Exception as e: print(f"scan err {e}"); continue
        salva_visti()
    except Exception as e:
        print(f"Errore scan: {e}")
        import traceback; traceback.print_exc()

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio V22 SVEGLIO - 2.5s safe")
        bot.run(tok)
    else:
        print("❌ DISCORD_TOKEN mancante")
