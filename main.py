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

CARD_KEYWORDS = ["psa","topps","bowman","pokemon","charizard","refractor","graded","autograph","auto","/99","/25","/10","numbered","sapphire","chrome","piccolo","biglietto","carta"]

import difflib

SNEAKER_MODELS = [
    "air zoom vomero 5", "vomero 5", "vomero", "air max 90", "air max 95", "air max 97",
    "air max 1", "air max plus", "air force 1", "dunk low", "dunk high",
    "jordan 1 low", "jordan 1 high", "jordan 1 mid", "jordan 4", "jordan 3",
    "jordan 11", "jordan 5", "p-6000", "990v3", "990v6", "530", "9060",
    "2002r", "gel-1130", "gel-nyc", "gel-kayano", "samba", "gazelle",
    "spezial", "campus", "yeezy 350", "yeezy 700", "ultraboost", "shox",
    "pegasus", "structure", "invincible", "zoom fly", "550", "574",
    "react", "cortez", "blazer", "waffle", "tiempo", "phantom",
    "mercurial", "copa", "predator", "superstar", "forum", "pro model",
    "nizza", "stan smith", "ultraboost 21", "ultraboost 22"
]

ABBIGLIAMENTO_MODELLI = [
    "lacoste polo", "ralph lauren polo", "stone island vestaglia",
    "stone island marina", "stone island reflective", "stone island nylon",
    "stone island wool", "dsquared2 hoodie", "dsquared2 t-shirt",
    "fred perry shirt", "tommy hilfiger polo", "armani exchange",
    "ralph lauren sweater", "ralph lauren hoodie", "ralph lauren jacket",
    "lacoste sweater", "lacoste hoodie", "north face puffer",
    "north face jacket", "carhartt jacket", "patagonia fleece"
]

def correggi_modello_sneaker(titolo):
    tl = titolo.lower()
    parole = tl.split()
    migliore_match = None
    migliore_score = 0
    tutti_modelli = SNEAKER_MODELS + ABBIGLIAMENTO_MODELLI
    for modello in tutti_modelli:
        modello_parole = modello.split()
        for i in range(len(parole)):
            frammento = " ".join(parole[i:i+len(modello_parole)+1])
            score = difflib.SequenceMatcher(None, frammento, modello).ratio()
            if score > migliore_score:
                migliore_score = score
                migliore_match = modello
    if migliore_score >= 0.6:
        return migliore_match
    return None

def is_sneaker_brand(brand, titolo):
    t = (brand + " " + titolo).lower()
    return any(x in t for x in ["nike", "adidas", "jordan", "new balance", "nb", "asics", "reebok", "yeezy", "balenciaga", "salomon", "on running", "hoka"])
def is_abbigliamento_brand(brand, titolo):
    t = (brand + " " + titolo).lower()
    return any(x in t for x in ["lacoste", "ralph", "stone", "dsquared", "fred", "tommy", "armani", "north", "carhartt", "patagonia"])

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
]

def carica_config():
    default = {
        "sotto_prezzo_min": 20,
        "guadagno_mostro": 30,
        "guadagno_super_mostro": 40,
        "guadagno_banger": 25,
        "spedizione": 5,
        "max_secondi_freschezza": 2,
        "min_cuori_validazione": 10,
        "min_annunci_validati": 5,
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

def is_card(titolo,brand):
    t=(titolo+" "+brand).lower()
    return any(k in t for k in CARD_KEYWORDS)

def detect_card_variant(titolo):
    tl=titolo.lower()
    varianti=[]
    if "auto" in tl or "autograph" in tl:
        varianti.append("autografo")
    if "refractor" in tl:
        varianti.append("refractor")
    if "sapphire" in tl:
        varianti.append("sapphire")
    if "chrome" in tl:
        varianti.append("chrome")
    num_match=re.search(r'/(\d+)',tl)
    if num_match:
        varianti.append(f"numerata-{num_match.group(1)}")
    if "psa" in tl:
        varianti.append("psa")
    if "base" in tl:
        varianti.append("base")
    return "+".join(varianti) if varianti else "base"

# ===================== CONDIZIONI VINTED + EMOJI + CONTROLLO PREZZO PER CONDIZIONE =====================
COND_TOP = ["nuovo con etichette","nuovo senza etichette","new with tags","new without tags","nuovo"]
COND_BUONE = ["ottime","molto buono","very good","ottimo","eccellente","excellent"]
COND_MEDIE = ["buone","buono","good","discrete"]
COND_BASSE = ["sufficiente","fair","scarso"]

COND_EMOJI = {
    "top": "✨🔥",
    "buone": "✅💎",
    "medie": "👌👕",
    "basse": "⚠️👎",
    "sconosciuta": "❓"
}

# Moltiplicatore prezzo per condizione: un articolo Buone vale meno di Nuovo!
COND_MULTIPLIER = {
    "top": 1.0,
    "buone": 0.85,
    "medie": 0.68,
    "basse": 0.45,
    "sconosciuta": 0.80
}

def condizione_tier(status):
    s = status.lower().strip()
    if not s:
        return "sconosciuta"
    if any(s == c or c in s for c in COND_TOP):
        return "top"
    if any(s == c or c in s for c in COND_BUONE):
        return "buone"
    if any(s == c or c in s for c in COND_MEDIE):
        return "medie"
    if any(s == c or c in s for c in COND_BASSE):
        return "basse"
    return "sconosciuta"

def condizioni_simili(status1, status2):
    t1 = condizione_tier(status1)
    t2 = condizione_tier(status2)
    if t1 == "sconosciuta" or t2 == "sconosciuta":
        return True
    return t1 == t2

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

def controlla_stabilita(prezzi):
    if not prezzi or len(prezzi)<3:
        return False,"CAMPIONE_PICCOLO"
    p_min=min(prezzi)
    p_max=max(prezzi)
    if p_min<=0:
        return False,"DATI_INVALIDI"
    rapporto=p_max/p_min
    if rapporto>5:
        return False,"RANGE_TROPPO_AMPIO"
    if rapporto>2.5:
        return True,"DATI_INSTABILI"
    mediana=statistics.median(prezzi)
    try:
        dev_std=statistics.stdev(prezzi) if len(prezzi)>1 else 0
        if mediana>0 and dev_std/mediana>0.3:
            return True,"DATI_INSTABILI"
    except:
        pass
    return True,None

_cache_analisi = {}
def get_cache_analisi(key):
    k = key.lower().strip()
    if k in _cache_analisi:
        result, ts = _cache_analisi[k]
        if time.time() - ts < 1800:
            return result
        del _cache_analisi[k]
    return None

def set_cache_analisi(key, result):
    k = key.lower().strip()
    _cache_analisi[k] = (result, time.time())
    if len(_cache_analisi) > 200:
        now = time.time()
        for ck in list(_cache_analisi.keys()):
            if now - _cache_analisi[ck][1] > 1800:
                del _cache_analisi[ck]

def analizza_mostro(titolo, brand_input, prezzo_acquisto=None, condizione_item="", brand_title_api="", size_title=""):
    cfg = carica_config()
    cache_key = f"{titolo}_{brand_input}_{condizione_item}_{size_title}"
    cached = get_cache_analisi(cache_key)
    if cached is not None:
        return cached
    sess = get_session()
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json", "Referer": "https://www.vinted.it/"}
    try:
        is_card_item = is_card(titolo, brand_input)
        min_cuori = cfg.get("min_cuori_validazione", 5)

        modello_corretto = None
        if is_sneaker_brand(brand_input, titolo) or is_abbigliamento_brand(brand_input, titolo):
            modello_corretto = correggi_modello_sneaker(titolo)
            if modello_corretto is None:
                return None

        if is_card_item:
            variante = detect_card_variant(titolo)
            search = "%20".join(titolo.split()[:5])
            if variante and variante != "base":
                search = f"{search}%20{variante.replace('+', '%20')}"
        elif modello_corretto:
            search = "%20".join((brand_input + " " + modello_corretto).split())
        else:
            search = "%20".join(titolo.split()[:6])

        url = f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=40&order=relevance"
        r = sess.get(url, headers=headers, timeout=10)
        if r.status_code == 429:
            time.sleep(2)
            return None

        tutti_annunci = []
        for it in r.json().get("items", []):
            p = it.get("price", {}).get("amount")
            try:
                if p and float(p) > 0:
                    p_val = float(p)
                    status = it.get("status", "")
                    fav_count = it.get("favourite_count", 0) or 0
                    bt = it.get("brand_title", "")
                    sz = it.get("size_title", "")
                    tutti_annunci.append({"prezzo": p_val, "status": status, "cuori": fav_count, "brand": bt, "size": sz})
            except:
                pass

        brand_target = (brand_title_api or brand_input or "").lower().strip()
        if brand_target:
            stessi_brand = [a for a in tutti_annunci if a["brand"].lower().strip() == brand_target]
            if len(stessi_brand) >= 4:
                tutti_annunci = stessi_brand

        # 🔥 FIX CONDIZIONI: filtra solo stessa condizione + emoji + multiplier
        tier_item = condizione_tier(condizione_item)
        if condizione_item:
            simili_cond = [a for a in tutti_annunci if condizioni_simili(a["status"], condizione_item)]
            if len(simili_cond) >= 4:
                tutti_annunci = simili_cond
            else:
                # Se pochi con stessa condizione, prendi almeno quelli simili ma abbassa valore
                pass

        if size_title:
            size_clean = size_title.lower().strip()
            stessi_size = [a for a in tutti_annunci if a["size"].lower().strip() == size_clean]
            if len(stessi_size) >= 4:
                tutti_annunci = stessi_size

        if len(tutti_annunci) < 5 and not is_card_item:
            search2 = "%20".join(titolo.split()[:3])
            url2 = f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=40&order=relevance"
            r2 = sess.get(url2, headers=headers, timeout=10)
            extra = []
            for it in r2.json().get("items", []):
                p = it.get("price", {}).get("amount")
                try:
                    if p and float(p) > 0:
                        p_val = float(p)
                        status = it.get("status", "")
                        fav_count = it.get("favourite_count", 0) or 0
                        bt = it.get("brand_title", "")
                        sz = it.get("size_title", "")
                        extra.append({"prezzo": p_val, "status": status, "cuori": fav_count, "brand": bt, "size": sz})
                except:
                    pass
            if brand_target:
                extra_brand = [a for a in extra if a["brand"].lower().strip() == brand_target]
                if len(extra_brand) >= 4:
                    extra = extra_brand
            # Filtra anche extra per condizione
            if condizione_item:
                extra_cond = [a for a in extra if condizioni_simili(a["status"], condizione_item)]
                if len(extra_cond) >= 4:
                    extra = extra_cond
            tutti_annunci = extra

        if not tutti_annunci:
            return None

        validati = [a for a in tutti_annunci if a["cuori"] >= min_cuori]
        if len(validati) < cfg.get("min_annunci_validati", 5):
            validati = [a for a in tutti_annunci if a["cuori"] >= 3]
        if len(validati) < cfg.get("min_annunci_validati", 5):
            validati = tutti_annunci

        if condizione_item:
            validati_cond = [a for a in validati if condizioni_simili(a["status"], condizione_item)]
            if len(validati_cond) >= cfg.get("min_annunci_validati", 3):
                validati = validati_cond

        prezzi_validati = pulisci_prezzi([a["prezzo"] for a in validati])
        if not prezzi_validati or len(prezzi_validati) < 5:
            return None

        stabile, flag = controlla_stabilita(prezzi_validati)
        if not stabile and flag == "RANGE_TROPPO_AMPIO":
            return None

        valore_riferimento = statistics.median(prezzi_validati)

        # 🔥 CONTROLLO PREZZO IN BASE A CONDIZIONE: Buone/Medie valgono meno!
        # Se stai comparando un articolo in condizioni "Buone" vs mercato "Ottime", abbassa il valore di riferimento
        multiplier = COND_MULTIPLIER.get(tier_item, 0.80)
        valore_corretto_condizione = round(valore_riferimento * multiplier, 2) if tier_item != "top" else valore_riferimento

        result = {
            "valore": round(valore_riferimento, 2),
            "valore_condizione": round(valore_corretto_condizione, 2),
            "media": round(statistics.mean(prezzi_validati), 2),
            "min": round(min(prezzi_validati), 2),
            "max": round(max(prezzi_validati), 2),
            "count": len(prezzi_validati),
            "count_totali": len(tutti_annunci),
            "stabile": stabile,
            "flag": flag,
            "is_card": is_card_item,
            "validati_cuori": len([a for a in validati if a["cuori"] >= min_cuori]),
            "condizione": tier_item,
            "emoji_cond": COND_EMOJI.get(tier_item, "❓"),
            "multiplier": multiplier
        }
        set_cache_analisi(cache_key, result)
        return result
    except Exception as e:
        print(f"🔥 Errore analisi mercato: {e}")
        return None

def analizza_mercato_vendita(titolo, use_cache=True):
    global cache_mercato
    key = titolo.lower().strip()
    if use_cache and key in cache_mercato:
        data, ts = cache_mercato[key]
        if time.time() - ts < 600:
            return data
    sess = get_session()
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json", "Referer": "https://www.vinted.it/"}
    try:
        for n in [5, 4, 3, 2]:
            terms = titolo.split()
            if len(terms) < n:
                continue
            search = "%20".join(terms[:n])
            url = f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=40&order=relevance"
            r = sess.get(url, headers=headers, timeout=10)
            if r.status_code == 429:
                time.sleep(2)
                continue
            prezzi = []
            prezzi_validati = []
            for it in r.json().get("items", []):
                p = it.get("price", {}).get("amount")
                try:
                    if p and float(p) > 0:
                        p_val = float(p)
                        prezzi.append(p_val)
                        fav = it.get("favourite_count", 0) or 0
                        if fav >= 5:
                            prezzi_validati.append(p_val)
                except:
                    pass
            fonte = prezzi_validati if len(prezzi_validati) >= 3 else prezzi
            if len(fonte) >= 4:
                fonte = pulisci_prezzi(fonte)
                stabile, flag = controlla_stabilita(fonte)
                result = {
                    "valore": round(statistics.median(fonte), 2),
                    "media": round(statistics.mean(fonte), 2),
                    "min": round(min(fonte), 2),
                    "max": round(max(fonte), 2),
                    "count": len(fonte),
                    "stabile": stabile,
                    "flag": flag,
                    "validati": len(prezzi_validati)
                }
                cache_mercato[key] = (result, time.time())
                return result
        return None
    except:
        return None

def genera_descrizione_vendita(nome, brand_detected=""):
    brand = brand_detected or detect_brand(nome)
    merc = analizza_mercato_vendita(nome)
    if merc:
        veloce = round(merc["valore"] * 0.90, 2)
        maxp = round(merc["valore"] * 1.08, 2)
    else:
        veloce = maxp = None
    titolo = nome.title()
    if brand and brand.lower() not in nome.lower():
        titolo = f"{brand.title()} {titolo}"
    desc = f"🔥 {titolo} 🔥\n✅ Brand {brand.title() if brand else 'Originale'} 9/10\n📦 Spedizione 24h tracciata"
    return {"titolo_seo": titolo, "descrizione": desc, "prezzo_veloce": veloce, "prezzo_massimo": maxp, "mercato": merc, "brand": brand}

def studia_confronto(lista):
    ris = []
    for ogg in lista:
        m = analizza_mercato_vendita(ogg)
        if m:
            ris.append({"nome": ogg, "mercato": m})
    ris = sorted(ris, key=lambda x: x["mercato"]["valore"] if x["mercato"] else 0, reverse=True)
    return ris

def risposta_chat_infinita(user_id, messaggio, ha_foto=False):
    msg_lower = messaggio.lower().strip()
    storico = carica_chat()
    user_history = storico.get(str(user_id), [])
    if messaggio.strip():
        user_history.append({"role": "user", "content": messaggio, "time": str(datetime.datetime.now())})
    cfg = carica_config()
    brand_det = detect_brand(messaggio)

    if ha_foto:
        nome = messaggio.strip() or "oggetto in foto"
        if len(nome) < 5 or any(k in msg_lower for k in ["usa quella", "quella foto", "vedi l'immagine", "gia mandata"]):
            for h in reversed(user_history[:-1]):
                txt = h.get("content", "")
                if len(txt) > 5:
                    nome = txt
                    brand_det = detect_brand(txt) or brand_det
                    break
            if len(nome) < 5:
                nome = "oggetto in foto"
        result = genera_descrizione_vendita(nome, brand_det)
        merc = result.get("mercato")
        if merc:
            flag_str = ""
            if merc.get("flag"):
                flag_str = f"\n⚠️ {merc['flag'].replace('_', ' ')}"
            validati_str = f"\n❤️ {merc.get('validati', 0)} annunci validati (5+ cuori)" if merc.get("validati", 0) > 0 else ""
            is_card_item = is_card(nome, brand_det or "")
            card_str = ""
            if is_card_item:
                variante = detect_card_variant(nome)
                card_str = f"\n🃏 Carta: variante {variante}"
            risposta = (f"📸 **{result['titolo_seo']}**\n"
                       f"📊 Valore mercato: **{merc['valore']}€** (range: {merc['min']}-{merc['max']}€ su {merc['count']} annunci)"
                       f"{validati_str}{card_str}{flag_str}\n\n"
                       f"⚡ Prezzo veloce: {result['prezzo_veloce']}€ | Max: {result['prezzo_massimo']}€\n\n"
                       f"Vuoi la descrizione? Scrivi `!vendi {nome}`")
        else:
            risposta = f"📸 Foto {nome} ricevuta! Non trovo abbastanza annunci validati (5+ cuori). Dimmi brand e modello precisi. 🔍"

    elif any(x in msg_lower for x in ["non trovo", "sta a cerca", "stai cercando", "cerchi", "sniper", "offert"]):
        risposta = (f"✅ **Bot attivo** 🔥\n"
                    f"🔄 Scansione ogni 1.2s su {len(cfg['user_brands'])} brand\n"
                    f"⏱️ Solo freschi (max {cfg['max_secondi_freschezza']}s)\n"
                    f"❤️ Confronto con annunci 5+ cuori\n"
                    f"🧐 Controllo prezzo per condizione: ✨ Top 100% | ✅ Buone 85% | 👌 Medie 68% | ⚠️ Basse 45%\n"
                    f"💰 Sotto prezzo min: {cfg['sotto_prezzo_min']}€\n"
                    f"👀 Visti: {len(gia_visti)}")

    elif any(x in msg_lower for x in ["secondo te", "come e meglio", "quale e meglio", "consigliami", "quale conviene"]):
        all_text = " ".join([h.get("content", "") for h in user_history[-6:]]) + " " + messaggio
        oggetti = []
        for b in ["lacoste", "ralph lauren", "dsquared2", "stone island", "pokemon", "charizard", "nike dunk", "jordan 1"]:
            if b in all_text.lower() and b not in oggetti:
                oggetti.append(b)
        if len(oggetti) < 2:
            oggetti = ["lacoste polo", "ralph lauren polo", "dsquared2 t-shirt", "pokemon charizard"]
        risultati = studia_confronto(oggetti[:4])
        txt = "🧠 **Confronto mercati:**\n\n"
        for i, r in enumerate(risultati):
            if r["mercato"]:
                flag_str = f" ⚠️ {r['mercato']['flag'].replace('_', ' ')}" if r["mercato"].get("flag") else ""
                val_str = f" | ❤️ {r['mercato'].get('validati', 0)} validati" if r["mercato"].get("validati", 0) > 0 else ""
                txt += f"**{i+1}. {r['nome'].title()}** → {r['mercato']['valore']}€ ({r['mercato']['count']} annunci){val_str}{flag_str}\n"
        if risultati:
            txt += f"\n👉 **Top: {risultati[0]['nome'].title()}** a {risultati[0]['mercato']['valore']}€ 🏆"
        risposta = txt

    elif any(x in msg_lower for x in ["filtr", "guadagno", "config", "soglie", "impostazioni"]):
        risposta = (f"⚙️ **Config V20 EMOJI+CONDIZIONI:**\n"
                    f"• Sotto prezzo min: {cfg['sotto_prezzo_min']}€\n"
                    f"• Soglie: 💧🔥 {cfg['sotto_prezzo_min']}€ | 💥🔥 {cfg['guadagno_banger']}€ | 🔴🔥 {cfg['guadagno_mostro']}€ | 🟣🔥 {cfg['guadagno_super_mostro']}€\n"
                    f"• Cuori min validazione: {cfg['min_cuori_validazione']}\n"
                    f"• Freschi max: {cfg['max_secondi_freschezza']}s\n"
                    f"• Spedizione: {cfg['spedizione']}€\n"
                    f"• Controllo condizione: ✨ Top 100% | ✅ 85% | 👌 68% | ⚠️ 45%\n"
                    f"• Brand: {', '.join(cfg['user_brands'])}\n"
                    f"• Visti: {len(gia_visti)}")

    else:
        if brand_det:
            m = analizza_mercato_vendita(messaggio)
            if m:
                flag_str = f"\n⚠️ {m['flag'].replace('_', ' ')}" if m.get("flag") else ""
                validati_str = f"\n❤️ {m.get('validati', 0)} validati (5+ cuori)" if m.get("validati", 0) > 0 else ""
                risposta = (f"📊 **{messaggio.title()}**\n"
                           f"💰 Valore: {m['valore']}€ (range: {m['min']}-{m['max']}€ su {m['count']})"
                           f"{validati_str}{flag_str}\n\n"
                           f"Scrivi `!vendi {messaggio}` per la descrizione ✍️")
            else:
                risposta = f"Ho riconosciuto **{brand_det.title()}** 👀 ma non trovo abbastanza annunci validati. Dimmi il modello preciso. 🔍"
        else:
            risposta = ("🤖 Bot Vinted V20 🔥\n"
                       "Mandami una **foto** 📸 + nome per analisi prezzo\n"
                       "Comandi: `!vendi`, `!prezzo`, `!migliora` ✨\n"
                       "Dimmi `config` per le soglie ⚙️")

    user_history.append({"role": "assistant", "content": risposta, "time": str(datetime.datetime.now())})
    if len(user_history) > 30:
        user_history = user_history[-30:]
    storico[str(user_id)] = user_history
    salva_chat(storico)
    return risposta

@bot.event
async def on_ready():
    carica_visti()
    cfg = carica_config()
    print(f"🔥 Bot V20 EMOJI+CONDIZIONI - Cuori {cfg['min_cuori_validazione']}+ | Sotto prezzo {cfg['sotto_prezzo_min']}€ | Mostro {cfg['guadagno_mostro']}/{cfg['guadagno_super_mostro']}€ | Freschi {cfg['max_secondi_freschezza']}s | {bot.user} ✨")
    controllo_vinted.start()

@bot.command()
async def filtro(ctx, azione=None, *, args=""):
    filtri = carica_filtri()
    if azione == "add":
        parti = args.rsplit(" ", 1)
        if len(parti) != 2:
            await ctx.send("❌ Usa: !filtro add lacoste 35 📝")
            return
        kw, pr = parti[0].lower(), parti[1]
        try:
            pr = float(pr)
        except:
            return
        filtri.append({"keyword": kw, "max": pr})
        salva_filtri(filtri)
        await ctx.send(f"✅ Aggiunto {kw} sotto {pr}€ 💰")
    else:
        cfg = carica_config()
        await ctx.send(f"⚙️ Sotto prezzo {cfg['sotto_prezzo_min']}€ | Cuori min {cfg['min_cuori_validazione']} ❤️ | Freschi {cfg['max_secondi_freschezza']}s ⏱️ | Visti {len(gia_visti)} 👀")

@bot.command()
async def config(ctx):
    cfg = carica_config()
    await ctx.send(f"⚙️ V20 ✨ | 💧🔥 {cfg['sotto_prezzo_min']}€ | 💥🔥 {cfg['guadagno_banger']}€ | 🔴🔥 {cfg['guadagno_mostro']}€ | 🟣🔥 {cfg['guadagno_super_mostro']}€ | Cuori: {cfg['min_cuori_validazione']}+ ❤️ | Spedizione {cfg['spedizione']}€ 📦 | Freschi {cfg['max_secondi_freschezza']}s ⏱️ | Visti {len(gia_visti)} 👀")

@bot.command()
async def prezzo(ctx, *, nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("💰 !prezzo lacoste polo 👕")
        return
    m = analizza_mercato_vendita(nome_oggetto)
    if m:
        flag_str = f" ⚠️ {m['flag'].replace('_', ' ')}" if m.get("flag") else ""
        val_str = f" | ❤️ {m.get('validati', 0)} validati" if m.get("validati", 0) > 0 else ""
        await ctx.send(f"💰 {nome_oggetto} → {m['valore']}€ (range: {m['min']}-{m['max']}€ su {m['count']}){val_str}{flag_str} 📊")
    else:
        await ctx.send("❌ Non trovo abbastanza annunci validati 🔍")

@bot.command()
async def vendi(ctx, *, nome_oggetto=""):
    if not nome_oggetto:
        await ctx.send("✍️ !vendi lacoste polo + foto 📸")
        return
    r = genera_descrizione_vendita(nome_oggetto)
    embed = discord.Embed(title=f"📦 {r['titolo_seo'][:50]} ✨", description=f"```{r['descrizione'][:1000]}```", color=0x00ff88)
    if r["mercato"]:
        flag_str = f" ⚠️ {r['mercato']['flag'].replace('_', ' ')}" if r["mercato"].get("flag") else ""
        val_str = f"\n❤️ {r['mercato'].get('validati', 0)} validati (5+ cuori)" if r["mercato"].get("validati", 0) > 0 else ""
        embed.add_field(name="💰 Mercato 📊", value=f"{r['mercato']['valore']}€ (range: {r['mercato']['min']}-{r['mercato']['max']}€ su {r['mercato']['count']}){val_str}{flag_str}\n⚡ Veloce: {r['prezzo_veloce']}€ | Max: {r['prezzo_massimo']}€")
    await ctx.send(embed=embed)

@bot.command()
async def migliora(ctx):
    if not ctx.message.attachments:
        await ctx.send("📸 Mandami una foto con `!migliora` ✨")
        return
    try:
        foto_url = ctx.message.attachments[0].url
        r = requests.get(foto_url, timeout=15)
        img = Image.open(io.BytesIO(r.content))
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Brightness(img).enhance(1.1)
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        await ctx.send(file=discord.File(buf, filename="migliorata.jpg"))
    except Exception as e:
        await ctx.send(f"❌ Errore: {e} 😢")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if len(message.attachments) > 0:
        last_photo_per_user[message.author.id] = message.attachments[0].url
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    if isinstance(message.channel, discord.DMChannel):
        ha_foto = len(message.attachments) > 0
        if not ha_foto and any(k in message.content.lower() for k in ["quella foto", "quella", "vedi l'immagine", "gia mandata", "usa quella"]):
            if message.author.id in last_photo_per_user:
                ha_foto = True
        async with message.channel.typing():
            risposta = risposta_chat_infinita(message.author.id, message.content, ha_foto)
        await message.channel.send(risposta)
        return
    if bot.user in message.mentions:
        ha_foto = len(message.attachments) > 0
        risposta = risposta_chat_infinita(message.author.id, message.content, ha_foto)
        await message.channel.send(f"{message.author.mention} {risposta}")
        return
    await bot.process_commands(message)

@tasks.loop(seconds=1.2)
async def controllo_vinted():
    try:
        cfg = carica_config()
        sess = get_session()
        headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json", "Referer": "https://www.vinted.it/"}
        max_fresco = cfg.get("max_secondi_freschezza", 2)
        sotto_prezzo_min = cfg.get("sotto_prezzo_min", 15)

        urls = []
        for brand in cfg.get("user_brands", []) + cfg.get("scan_brands", []):
            b_q = brand.replace(" ", "%20")
            urls.append(f"https://www.vinted.it/api/v2/catalog/items?search_text={b_q}&order=newest_first&per_page=25")
        urls.append("https://www.vinted.it/api/v2/catalog/items?order=newest_first&per_page=40")
        urls = list(dict.fromkeys(urls))[:12]

        for url in urls:
            try:
                r = sess.get(url, headers=headers, timeout=12)
                if r.status_code == 429:
                    await discord.utils.sleep_until(datetime.datetime.now() + datetime.timedelta(seconds=5))
                    continue
                if r.status_code != 200:
                    continue
                for item in r.json().get("items", []):
                    iid = str(item.get("id"))
                    if iid in gia_visti:
                        continue

                    created_ts = item.get("created_at_ts")
                    if created_ts:
                        try:
                            eta = time.time() - float(created_ts)
                            if eta > max_fresco:
                                gia_visti.add(iid)
                                continue
                        except:
                            pass

                    gia_visti.add(iid)
                    titolo = item.get("title", "")
                    titolo_low = titolo.lower()
                    brand = item.get("brand_title", "")
                    condizione_item = item.get("status", "")
                    size_item = item.get("size_title", "")
                    try:
                        prezzo = float(item.get("price", {}).get("amount"))
                    except:
                        continue

                    max_per_brand = cfg.get("max_price_per_brand", {})
                    b_detect = detect_brand(titolo + " " + brand)
                    max_allowed = max_per_brand.get(b_detect, max_per_brand.get(brand.lower(), 80))
                    if prezzo > max_allowed:
                        continue
                    if prezzo < 5 or prezzo > 350:
                        continue
                    if not is_conosciuto(titolo, brand):
                        continue

                    filtri = carica_filtri()
                    if filtri:
                        if not any(f["keyword"].lower() in titolo_low and prezzo <= f["max"] for f in filtri):
                            continue

                    mercato = analizza_mostro(titolo, brand, prezzo, condizione_item, brand, size_item)
                    if not mercato:
                        continue
                    if mercato["count"] < 5:
                        continue

                    # 🔥 USA VALORE CORRETTO PER CONDIZIONE!
                    valore = mercato["valore_condizione"]
                    valore_mercato_grezzo = mercato["valore"]
                    diff = valore - prezzo
                    netto = diff - cfg["spedizione"]
                    sconto = (diff / valore * 100) if valore > 0 else 0
                    roi = (diff / prezzo * 100) if prezzo > 0 else 0

                    if diff < sotto_prezzo_min:
                        continue

                    flag = mercato.get("flag")
                    campione_piccolo = mercato["count"] < 10
                    campione_mini = mercato["count"] < 7
                    diff_min_proporzionale = max(sotto_prezzo_min, prezzo * 0.8) if prezzo < 50 else max(sotto_prezzo_min, prezzo * 0.45)
                    troppo_bello = netto > 2 * prezzo
                    diff_insufficiente = diff < diff_min_proporzionale

                    num_flag = 0
                    if campione_piccolo:
                        num_flag += 1
                    if campione_mini:
                        num_flag += 1
                    if troppo_bello:
                        num_flag += 1
                    if flag and flag != "DATI_INSTABILI" and flag != "CAMPIONE_PICCOLO":
                        num_flag += 1
                    if num_flag >= 2:
                        continue

                    soglia_base = sotto_prezzo_min
                    soglia_banger = cfg.get("guadagno_banger", 20)
                    soglia_mostro = cfg.get("guadagno_mostro", 25)
                    soglia_super = cfg.get("guadagno_super_mostro", 30)

                    if flag == "DATI_INSTABILI":
                        soglia_base += 5
                        soglia_banger += 5
                        soglia_mostro += 5
                        soglia_super += 5
                    if campione_piccolo:
                        soglia_base += 3
                        soglia_banger += 3
                        soglia_mostro += 3
                        soglia_super += 3

                    if diff_insufficiente:
                        continue

                    if netto < soglia_base:
                        continue

                    # Emoji per condizione
                    emoji_cond = mercato.get("emoji_cond", "❓")
                    cond_text = mercato.get("condizione", "sconosciuta")
                    multiplier = mercato.get("multiplier", 1.0)

                    if netto >= soglia_super:
                        livello = "super_mostro"
                        emoji = "🟣🔥🔥🔥💸💸💸"
                        ping = "@everyone 🟣🔥 30€+ NETTI! 🚀"
                    elif netto >= soglia_mostro:
                        livello = "mostro"
                        emoji = "🔴🔥🔥💸💸"
                        ping = "@here 🔴🔥 25€+ NETTI! 💥"
                    elif netto >= soglia_banger:
                        livello = "banger"
                        emoji = "💥🔥💸"
                        ping = ""
                    else:
                        livello = "accettabile"
                        emoji = "💧🔥"
                        ping = ""

                    link = f"https://www.vinted.it/items/{iid}"
                    foto = item.get("photo", {}).get("url", "")
                    cuori_item = item.get("favourite_count", 0) or 0

                    canale = None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages:
                                canale = ch
                                break
                        if canale:
                            break

                    if canale:
                        color = 0x9b59b6 if livello == "super_mostro" else 0xff0000 if livello == "mostro" else 0x00ff88 if livello == "banger" else 0xffaa00

                        flag_text = ""
                        if flag:
                            flag_text += f"\n⚠️ {flag.replace('_', ' ')}"
                        if campione_piccolo:
                            flag_text += "\n⚠️ CAMPIONE PICCOLO 🔍"
                        if troppo_bello:
                            flag_text += "\n⚠️ VERIFICARE MANUALMENTE 👀"
                        if mercato.get("is_card"):
                            flag_text += "\n🃏 Carta: verifica variante 🎴"

                        titolo_embed = f"{emoji} {round(netto)}€ NETTI: {titolo[:45]} {emoji_cond}"
                        embed = discord.Embed(
                            title=titolo_embed,
                            description=(f"**Brand:** {brand} ({b_detect})\n"
                                        f"**Acquisto:** {prezzo}€ 🛒 | **Rivendita corretta per condizione:** {valore}€ {emoji_cond} (grezzo {valore_mercato_grezzo}€)\n"
                                        f"**NETTO: {round(netto)}€** 💰 | Sotto prezzo: {round(diff)}€ | ROI {round(roi)}% 📈\n"
                                        f"📦 {size_item} | {emoji_cond} {condizione_item} ({cond_text} x{multiplier})\n"
                                        f"❤️ Confronto su {mercato['count']} annunci (5+ cuori: {mercato['validati_cuori']})\n"
                                        f"📊 Range: {mercato['min']}-{mercato['max']}€ | Totale: {mercato['count_totali']} annunci"
                                        f"{flag_text}\n"
                                        f"[👉 PRENDI SUBITO! 🚀]({link})"),
                            color=color
                        )
                        if foto:
                            embed.set_image(url=foto)
                        embed.set_footer(text=f"🔥 V20 {emoji_cond} | {b_detect} | Netto {round(netto)}€ | Cond: {cond_text} | Cuori item: {cuori_item} ❤️")
                        await canale.send(content=ping, embed=embed)

                if len(gia_visti) % 20 == 0:
                    salva_visti()
                await discord.utils.sleep_until(datetime.datetime.now() + datetime.timedelta(milliseconds=300))
            except Exception as e_inner:
                print(f"🔍 scan err {e_inner} 😢")
                continue
        salva_visti()
    except Exception as e:
        print(f"❌ Errore scan: {e} 💥")

from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "🔥 Bot V20 EMOJI+CONDIZIONI - Cuori 5+ ❤️ | Brand match | Condizioni IT 👕 | Sotto prezzo 15€ 💰 | Controllo prezzo per condizione ✨"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

import threading
threading.Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    tok = os.getenv("DISCORD_TOKEN")
    if tok:
        bot.run(tok)
