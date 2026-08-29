# 🔥 BOT VINTED RESELL — CONFIGURAZIONE V4 (modelli specifici, AUTO-BUY/ALERT, anti falsi-positivi)
import discord, asyncio, requests, json, os, re, time, threading, urllib.parse
from discord.ext import commands, tasks
from flask import Flask

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

VISTI_FILE = "gia_visti.json"
PREF_FILE = "preferenze_utenti.json"
gia_visti = set(); vinted_session = None; last_session_refresh = 0; ultimo_affare = None
stats = {"scaricati":0,"brand_no":0,"modello_no":0,"escluso_difetto":0,"escluso_stile":0,
         "condizione_no":0,"taglia_no":0,"seller_rischio":0,"profitto_basso":0,
         "alert":0,"auto_buy":0,"freshness_sconosciuto":0}
ultimo_report = 0
USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
               "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"]

# =========================================================================
# BRAND ALIASES — solo per riconoscere il brand nel testo (non basta da soli)
# =========================================================================
BRAND_ALIASES = {
    "carhartt wip": ["carhartt wip", "carhartt", "carharrt", "carrhartt", "carhart"],
    "the north face": ["the north face", "north face", "nort face", "northface", "tnf"],
    "arc'teryx": ["arc'teryx", "arcteryx", "arc teryx"],
    "patagonia": ["patagonia"],
    "nike": ["nike", "nikke"],
    "timberland": ["timberland", "timberlands"],
    "ralph lauren": ["ralph lauren", "polo ralph lauren", "raulph lauren", "ralf lauren"],
    "lululemon": ["lululemon", "lulu lemon"],
    "stone island": ["stone island", "stoneisland", "ston island", "stone islan"],
    "stussy": ["stussy", "stüssy", "stussy"],
}

# =========================================================================
# ESCLUSIONI GENERALI — se presenti, RIFIUTO SEMPRE, priorità assoluta
# =========================================================================
DIFETTI_ESCLUSIONE = [
    "macchia","macchie","macchiato","macchiata","sporco","sporca","sporchi","sporche",
    "scolorito","scolorita","scolorimento","strappo","strappata","strappato","buco","buchi",
    "foro","fori","zip rotta","cerniera rotta","zip difettosa","cerniera difettosa",
    "cucitura rotta","danneggiato","danneggiata","rovinato","rovinata","difetto","difetti",
    "usura evidente","molto usato","molto usata","da riparare","da sistemare","riparazione",
    "custom","personalizzato","personalizzata","modificato","modificata",
    "replica","fake","falso","falsa","contraffatto","contraffatta",
    "non originale","non autentico","non autentica","autenticità dubbia",
    "non so se originale","non so se autentico","non so se autentica",
    "non garantisco autenticità","senza garanzia di autenticità",
    "credo sia originale","sembra originale","potrebbe essere originale",
    "tarme","tarmato","tarmata","pilling forte","odore","usura forte",
    "sgonfio","sgonfia","perde piume","piume fuori","piuma fuori",
    "suola staccata","suola rotta","pelle rotta","crepe","deformata","deformato",
    "lacci mancanti","badge falso","badge non originale","trasparente",
    "tessuto consumato","gore-tex danneggiato","membrana danneggiata","riparato",
]
STILE_PATTERN = re.compile(r'\b(simile a|ispirato a|inspired by|inspired)\b', re.I)

SELLER_RISCHIO_BRANDS = ["arc'teryx","stone island","the north face","carhartt wip","stussy","nike"]

CONDIZIONI_KEYWORDS = {
    "nuovo con cartellino": ["nuovo con cartellino","new with tags","nwt"],
    "nuovo senza cartellino": ["nuovo senza cartellino","new without tags","nwot"],
    "nuovo": ["nuovo","new"],  # generico, usato da Timberland/Stone Island che non separano con/senza cartellino
    "ottime": ["ottime condizioni","ottime"],
    "buone": ["buone condizioni","buone"],
    "discrete": ["discrete condizioni","discrete","soddisfacenti"],
}

TAGLIE_RIFIUTA_GLOBALE = ["XXS"]

# =========================================================================
# MODELLI — ogni voce richiede BRAND + KEYWORD MODELLO insieme (mai da soli)
# auto_buy/buy_max per condizione | sell_min = SELL CONSERVATIVO basso | profit_min
# =========================================================================
MODELLI = [
    {"id":"tnf_nuptse","brand":"the north face","nome":"1996/1990 Retro Nuptse",
     "keywords":["1996 retro nuptse","nuptse 1996","1996 nuptse","1990 retro nuptse","nuptse 1990",
                 "retro nuptse","nuptse 700","700 nuptse","nupste","nuptze"],
     "escludi_se":["baltoro"],
     "condizioni":{"ottime":{"auto_buy":60,"buy_max":80},
                   "buone":{"buy_max":55},
                   "nuovo senza cartellino":{"buy_max":105},
                   "nuovo con cartellino":{"buy_max":130}},
     "sell_min":160,"sell_max":180,"profit_min":35,
     "taglie_rifiuta":["XS"],"colori":["black","nero","brown","beige","cream","khaki","olive","navy","blue"]},

    {"id":"carhartt_detroit","brand":"carhartt wip","nome":"Detroit/Michigan/Active Jacket",
     "keywords":["og detroit","detroit jacket","michigan coat","active jacket","carhartt wip detroit",
                 "carhartt detroit","hamilton brown","detroit brown"],
     "condizioni":{"ottime":{"auto_buy":50,"buy_max":65},
                   "buone":{"auto_buy":35,"buy_max":45},
                   "nuovo senza cartellino":{"buy_max":85},
                   "nuovo con cartellino":{"buy_max":110}},
     "sell_min":140,"sell_max":160,"profit_min":35,
     "taglie_rifiuta":["XS"],"colori":["hamilton brown","carhartt brown","black","dark brown","olive","navy"]},

    {"id":"arcteryx_atom_lt","brand":"arc'teryx","nome":"Atom LT",
     "keywords":["atom lt"],
     "condizioni":{"ottime":{"auto_buy":55,"buy_max":75},
                   "nuovo senza cartellino":{"buy_max":105},
                   "nuovo con cartellino":{"buy_max":125}},
     "sell_min":130,"sell_max":160,"profit_min":45},

    {"id":"arcteryx_beta_lt","brand":"arc'teryx","nome":"Beta LT",
     "keywords":["beta lt"],
     "condizioni":{"ottime":{"auto_buy":70,"buy_max":90},
                   "nuovo senza cartellino":{"buy_max":120},
                   "nuovo con cartellino":{"buy_max":145}},
     "sell_min":160,"sell_max":190,"profit_min":45},

    {"id":"arcteryx_beta_ar","brand":"arc'teryx","nome":"Beta AR",
     "keywords":["beta ar"],
     "condizioni":{"ottime":{"auto_buy":80,"buy_max":105},
                   "nuovo senza cartellino":{"buy_max":135},
                   "nuovo con cartellino":{"buy_max":160}},
     "sell_min":180,"sell_max":210,"profit_min":45},

    {"id":"arcteryx_cerium_lt","brand":"arc'teryx","nome":"Cerium LT",
     "keywords":["cerium lt","arc'teryx cerium","arcteryx cerium"],
     "condizioni":{"ottime":{"auto_buy":65,"buy_max":90},
                   "nuovo senza cartellino":{"buy_max":115},
                   "nuovo con cartellino":{"buy_max":140}},
     "sell_min":160,"sell_max":190,"profit_min":45},

    {"id":"patagonia_retrox","brand":"patagonia","nome":"Retro-X",
     "keywords":["retro-x","retro x","classic retro-x"],
     "condizioni":{"ottime":{"auto_buy":30,"buy_max":45},
                   "nuovo con cartellino":{"buy_max":60},"nuovo senza cartellino":{"buy_max":60}},
     "sell_min":75,"sell_max":95,"profit_min":35},

    {"id":"patagonia_retropile","brand":"patagonia","nome":"Retro Pile",
     "keywords":["retro pile"],
     "condizioni":{"ottime":{"auto_buy":25,"buy_max":35},
                   "nuovo con cartellino":{"buy_max":50},"nuovo senza cartellino":{"buy_max":50}},
     "sell_min":70,"sell_max":90,"profit_min":25},

    {"id":"patagonia_synchilla","brand":"patagonia","nome":"Synchilla",
     "keywords":["synchilla"],
     "condizioni":{"ottime":{"auto_buy":18,"buy_max":28},
                   "nuovo con cartellino":{"buy_max":45},"nuovo senza cartellino":{"buy_max":45}},
     "sell_min":55,"sell_max":75,"profit_min":25},

    {"id":"patagonia_bettersweater","brand":"patagonia","nome":"Better Sweater",
     "keywords":["better sweater"],
     "condizioni":{"ottime":{"auto_buy":18,"buy_max":28},
                   "nuovo con cartellino":{"buy_max":45},"nuovo senza cartellino":{"buy_max":45}},
     "sell_min":55,"sell_max":75,"profit_min":25},

    {"id":"nike_techfleece_felpa","brand":"nike","nome":"Tech Fleece Felpa",
     "keywords":["tech fleece hoodie","tech fleece felpa","tech fleece crew"],
     "escludi_se":["nocta"],
     "condizioni":{"ottime":{"auto_buy":25,"buy_max":35},
                   "nuovo con cartellino":{"buy_max":45},"nuovo senza cartellino":{"buy_max":45}},
     "sell_min":70,"sell_max":90,"profit_min":35,
     "taglie_rifiuta":["XS"],"taglia_s_solo_sotto":25,
     "colori":["black","nero","grey","dark grey","charcoal","navy"]},

    {"id":"nike_techfleece_pant","brand":"nike","nome":"Tech Fleece Pantalone",
     "keywords":["tech fleece jogger","tech fleece pant","tech fleece pantalone"],
     "escludi_se":["nocta"],
     "condizioni":{"ottime":{"auto_buy":20,"buy_max":30},
                   "nuovo con cartellino":{"buy_max":40},"nuovo senza cartellino":{"buy_max":40}},
     "sell_min":60,"sell_max":80,"profit_min":35,
     "taglie_rifiuta":["XS"],"taglia_s_solo_sotto":25},

    {"id":"nike_techfleece_tuta","brand":"nike","nome":"Tech Fleece Tuta completa",
     "keywords":["tech fleece tuta","tech fleece tracksuit","tech fleece set"],
     "escludi_se":["nocta"],
     "condizioni":{"ottime":{"auto_buy":35,"buy_max":50},
                   "nuovo con cartellino":{"buy_max":65},"nuovo senza cartellino":{"buy_max":65}},
     "sell_min":90,"sell_max":120,"profit_min":35,
     "taglie_rifiuta":["XS"],"taglia_s_solo_sotto":25},

    {"id":"nike_nocta_hoodie","brand":"nike","nome":"Nocta Hoodie",
     "keywords":["nocta hoodie","nike x nocta hoodie","nocta tech hoodie"],
     "condizioni":{"ottime":{"auto_buy":35,"buy_max":50},
                   "nuovo con cartellino":{"buy_max":70},"nuovo senza cartellino":{"buy_max":70}},
     "sell_min":90,"sell_max":120,"profit_min":35},

    {"id":"nike_nocta_pant","brand":"nike","nome":"Nocta Joggers",
     "keywords":["nocta joggers","nocta pant","nike x nocta pant"],
     "condizioni":{"ottime":{"auto_buy":25,"buy_max":40},
                   "nuovo con cartellino":{"buy_max":60},"nuovo senza cartellino":{"buy_max":60}},
     "sell_min":75,"sell_max":100,"profit_min":35},

    {"id":"nike_nocta_tuta","brand":"nike","nome":"Nocta Tracksuit completa",
     "keywords":["nocta tracksuit","nike x nocta tracksuit","nocta tuta"],
     "condizioni":{"ottime":{"auto_buy":45,"buy_max":65},
                   "nuovo con cartellino":{"buy_max":85},"nuovo senza cartellino":{"buy_max":85}},
     "sell_min":110,"sell_max":140,"profit_min":35},

    {"id":"timberland_wheat","brand":"timberland","nome":"Premium 6-Inch Wheat",
     "keywords":["premium 6-inch wheat","premium 6 inch wheat","6-inch premium","6 inch premium",
                 "wheat boot","wheat premium","yellow premium","gialla premium","gialle premium"],
     "condizioni":{"ottime":{"auto_buy":20,"buy_max":32},
                   "buone":{"buy_max":20},
                   "nuovo":{"buy_max":50}},
     "sell_min":75,"sell_max":90,"profit_min":35,
     "taglie_alert_extra":["36","37","38"],
     "colori":["wheat","giallo","yellow"],
     "discrete_eccezione":{"buy_max":15,"solo_se_pulibile":True}},

    {"id":"rl_polobear","brand":"ralph lauren","nome":"Polo Bear",
     "keywords":["polo bear","bear sweater","bear knit","polo bear knit","polo bear sweatshirt","polo bear hoodie"],
     "condizioni":{"ottime":{"auto_buy":15,"buy_max":25},
                   "nuovo con cartellino":{"buy_max":40},"nuovo senza cartellino":{"buy_max":40}},
     "sell_min":70,"sell_max":90,"profit_min":35},

    {"id":"lululemon_align","brand":"lululemon","nome":"Align Legging",
     "keywords":["align legging","align pant","align high rise","align crop"],
     "condizioni":{"ottime":{"auto_buy":12,"buy_max":20},
                   "nuovo senza cartellino":{"buy_max":25},"nuovo con cartellino":{"buy_max":30}},
     "sell_min":55,"sell_max":70,"profit_min":25},

    {"id":"lululemon_scuba","brand":"lululemon","nome":"Scuba Hoodie",
     "keywords":["scuba hoodie","scuba full zip","scuba oversized"],
     "condizioni":{"ottime":{"auto_buy":20,"buy_max":30},
                   "nuovo senza cartellino":{"buy_max":35},"nuovo con cartellino":{"buy_max":45}},
     "sell_min":65,"sell_max":85,"profit_min":25},

    {"id":"si_crewneck","brand":"stone island","nome":"Sweatshirt/Crewneck",
     "keywords":["crewneck","sweatshirt","felpa girocollo"],
     "escludi_se":["hoodie","zip","overshirt","jacket","giacca"],
     "condizioni":{"ottime":{"auto_buy":20,"buy_max":35},"nuovo":{"buy_max":55}},
     "sell_min":60,"sell_max":80,"profit_min":45},

    {"id":"si_hoodie","brand":"stone island","nome":"Hoodie",
     "keywords":["hoodie","felpa cappuccio"],
     "escludi_se":["zip"],
     "condizioni":{"ottime":{"auto_buy":25,"buy_max":40},"nuovo":{"buy_max":65}},
     "sell_min":75,"sell_max":100,"profit_min":45},

    {"id":"si_ziphoodie","brand":"stone island","nome":"Zip Hoodie",
     "keywords":["zip hoodie","felpa cappuccio zip"],
     "condizioni":{"ottime":{"auto_buy":30,"buy_max":45},"nuovo":{"buy_max":70}},
     "sell_min":85,"sell_max":110,"profit_min":45},

    {"id":"si_overshirt","brand":"stone island","nome":"Overshirt",
     "keywords":["overshirt"],
     "condizioni":{"ottime":{"auto_buy":40,"buy_max":60},"nuovo":{"buy_max":90}},
     "sell_min":110,"sell_max":140,"profit_min":45},

    {"id":"si_jacket","brand":"stone island","nome":"Jacket",
     "keywords":["jacket","giacca","giubbotto"],
     "condizioni":{"ottime":{"auto_buy":50,"buy_max":75},"nuovo":{"buy_max":105}},
     "sell_min":130,"sell_max":170,"profit_min":45},

    # Solo 8 Ball / World Tour: hoodie/crewneck Stussy "basic" (senza questi grafismi)
    # non valgono abbastanza da giustificare l'acquisto, come richiesto.
    {"id":"stussy_8ball","brand":"stussy","nome":"8 Ball / World Tour",
     "keywords":["8 ball","world tour"],
     "condizioni":{"ottime":{"auto_buy":30,"buy_max":50},"nuovo":{"buy_max":70}},
     "sell_min":80,"sell_max":110,"profit_min":35},
]

# Condizioni ammesse "buone" SOLO per questi modelli (regola 4/29 configurazione)
BUONE_AMMESSE = {"tnf_nuptse","carhartt_detroit","timberland_wheat"}
# Solo Timberland accetta eccezionalmente "discrete"
DISCRETE_AMMESSE = {"timberland_wheat"}

app = Flask(__name__)
@app.route("/")
def home(): return "Bot Vinted V4 - config modelli specifici AUTO-BUY/ALERT"
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

def match_brand(testo):
    tl=testo.lower()
    trovati=[]
    for brand_ufficiale, alias_list in BRAND_ALIASES.items():
        for alias in alias_list:
            if alias in tl:
                trovati.append(brand_ufficiale); break
    return trovati

def ha_difetto(tl):
    return any(d in tl for d in DIFETTI_ESCLUSIONE)

def ha_pattern_stile(tl, brand):
    # "stile Carhartt", "tipo Arc'teryx", "simile a Stone Island", "inspired North Face" -> rifiuta
    if STILE_PATTERN.search(tl):
        for alias in BRAND_ALIASES.get(brand, []):
            if alias in tl:
                return True
    return False

# Colore BLOCCANTE solo dove il colore è il modello stesso (punto 3 richiesto).
# Per tutti gli altri modelli il colore resta soft (mostrato ma non bloccante).
COLORE_BLOCCANTE = {
    "timberland_wheat": {"richiedi_uno": ["wheat","yellow","giallo","gialla","grano"]},
    "carhartt_detroit": {"se_keyword_in": ["hamilton brown","detroit brown"],
                          "rifiuta_se_contiene": ["black","nero","blue","navy"]},
}

def colore_ok(modello_id, tl, keyword_matchata):
    regola = COLORE_BLOCCANTE.get(modello_id)
    if not regola:
        return True  # soft per tutti gli altri modelli, come da richiesta
    if "richiedi_uno" in regola:
        return any(c in tl for c in regola["richiedi_uno"])
    if "se_keyword_in" in regola:
        if keyword_matchata in regola["se_keyword_in"]:
            if any(c in tl for c in regola["rifiuta_se_contiene"]):
                return False
        return True
    return True

def rileva_condizione(item, tl):
    status = (item.get("status") or "").lower()
    testo = status + " " + tl
    # ordine: più specifico prima
    for cond in ["nuovo con cartellino","nuovo senza cartellino","nuovo","ottime","buone","discrete"]:
        for kw in CONDIZIONI_KEYWORDS[cond]:
            if kw in testo:
                return cond
    return None

def seller_rischioso(item):
    # Campi reali /api/v2/catalog/items: feedback_count, positive_feedback_count,
    # feedback_reputation, item_count. NIENTE created_at (richiederebbe una chiamata
    # extra a /users/id che non facciamo, per non aumentare il rischio ban).
    # Fail-safe: se i dati non ci sono, NON blocchiamo (meglio un ALERT in più che
    # bloccare tutto per un campo mancante).
    user = item.get("user") or {}
    fb = user.get("feedback_count")
    item_count = user.get("item_count")
    reputation = user.get("feedback_reputation")
    if fb is None and item_count is None:
        return False  # nessun dato utile: non possiamo giudicare, non blocchiamo
    try:
        fb = int(fb) if fb is not None else 0
        item_count = int(item_count) if item_count is not None else 0
        reputation = float(reputation) if reputation is not None else 1.0
        if fb == 0 and item_count < 5:
            return True
        if fb < 3 and reputation < 0.8 and item_count < 10:
            return True
    except:
        return False  # campo malformato: non blocchiamo, meglio un falso negativo che un crash
    return False

def stone_island_manca_certilogo(descrizione):
    d = descrizione.lower()
    marcatori = ["art.","art number","articolo","numero articolo","codice articolo","codice prodotto","certilogo","clg"]
    if any(m in d for m in marcatori): return False
    if re.search(r'\b\d{6}\b', d): return False
    return True

async def valuta_articolo(item):
    titolo = item.get("title","") or ""
    brand_field = item.get("brand_title","") or ""
    descrizione = item.get("description","") or ""
    size = item.get("size_title","") or ""
    testo_completo = f"{titolo} {brand_field} {descrizione}"
    tl = testo_completo.lower()

    try: prezzo = float(item.get("price",{}).get("amount"))
    except: return None

    # 1. ESCLUSIONI GENERALI - priorità assoluta
    if ha_difetto(tl):
        stats["escluso_difetto"]+=1
        return None

    brands_trovati = match_brand(testo_completo)
    if not brands_trovati:
        stats["brand_no"]+=1
        return None

    if any(ha_pattern_stile(tl, b) for b in brands_trovati):
        stats["escluso_stile"]+=1
        return None

    # 2. MODELLO - deve matchare brand + keyword specifica insieme
    modello_trovato = None
    keyword_matchata = None
    for m in MODELLI:
        if m["brand"] not in brands_trovati: continue
        kw_trovata = next((k for k in m["keywords"] if k in tl), None)
        if kw_trovata is None: continue
        if any(e in tl for e in m.get("escludi_se",[])): continue
        modello_trovato = m
        keyword_matchata = kw_trovata
        break
    if not modello_trovato:
        stats["modello_no"]+=1
        return None

    # 2b. COLORE BLOCCANTE (solo Timberland Wheat e Carhartt Brown, tutto il resto è soft)
    if not colore_ok(modello_trovato["id"], tl, keyword_matchata):
        stats["modello_no"]+=1
        return None

    # 3. AUTENTICITA' - brand a rischio, seller senza storico
    if modello_trovato["brand"] in SELLER_RISCHIO_BRANDS and seller_rischioso(item):
        stats["seller_rischio"]+=1
        return None

    # 4. CONDIZIONE
    condizione = rileva_condizione(item, tl)
    if condizione is None:
        stats["condizione_no"]+=1
        return None
    if condizione == "buone" and modello_trovato["id"] not in BUONE_AMMESSE:
        stats["condizione_no"]+=1
        return None
    if condizione == "discrete":
        if modello_trovato["id"] not in DISCRETE_AMMESSE:
            stats["condizione_no"]+=1
            return None
        # eccezione Timberland: solo se sporco/macchia pulibile dichiarato, niente danni strutturali
        ecc = modello_trovato.get("discrete_eccezione")
        if not ecc:
            stats["condizione_no"]+=1
            return None
        cond_block = {"buy_max": ecc["buy_max"]}  # mai auto_buy
    else:
        cond_block = modello_trovato["condizioni"].get(condizione)
        if cond_block is None:
            # "nuovo" generico per modelli che non separano con/senza cartellino
            if condizione in ("nuovo con cartellino","nuovo senza cartellino") and "nuovo" in modello_trovato["condizioni"]:
                cond_block = modello_trovato["condizioni"]["nuovo"]
            else:
                stats["condizione_no"]+=1
                return None

    buy_max = cond_block.get("buy_max")
    auto_buy_soglia = cond_block.get("auto_buy")  # None se questa condizione non prevede mai AUTO-BUY

    if prezzo > buy_max:
        return None  # IGNORA silenzioso, prezzo troppo alto: normale, non è un errore

    # 5. TAGLIA
    taglie_rifiuta = modello_trovato.get("taglie_rifiuta", []) + TAGLIE_RIFIUTA_GLOBALE
    if size.upper() in [t.upper() for t in taglie_rifiuta]:
        stats["taglia_no"]+=1
        return None
    # Taglia S ammessa solo sotto una certa soglia di prezzo, dove previsto (es. Nike Tech Fleece: <25€)
    soglia_s = modello_trovato.get("taglia_s_solo_sotto")
    if soglia_s is not None and size.upper() == "S" and prezzo >= soglia_s:
        stats["taglia_no"]+=1
        return None

    # 6. PROFITTO NETTO (formula conservativa: sell*0.95 - buy, niente doppia sottrazione spedizione)
    sell_min = modello_trovato["sell_min"]
    profitto_netto = round(sell_min*0.95 - prezzo, 2)
    profit_min_richiesto = modello_trovato["profit_min"]
    if profitto_netto < profit_min_richiesto:
        stats["profitto_basso"]+=1
        return None

    # 7. TIER: AUTO-BUY o ALERT
    tier = "ALERT"
    if auto_buy_soglia is not None and prezzo <= auto_buy_soglia:
        tier = "AUTO-BUY"

    # Regola speciale Stone Island: senza Art/Certilogo sotto 30€, mai AUTO-BUY
    if modello_trovato["brand"] == "stone island" and prezzo < 30 and stone_island_manca_certilogo(descrizione):
        tier = "ALERT"

    if tier == "AUTO-BUY": stats["auto_buy"]+=1
    else: stats["alert"]+=1

    return {
        "modello": modello_trovato, "tier": tier, "condizione": condizione,
        "prezzo": prezzo, "buy_max": buy_max, "auto_buy_soglia": auto_buy_soglia,
        "profitto_netto": profitto_netto, "size": size, "titolo": titolo, "brand_field": brand_field,
    }

@bot.event
async def on_ready():
    carica_visti()
    print(f"Bot V4 online {bot.user} | {len(MODELLI)} modelli configurati")
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

# Query FISSE (8) — sempre cercate ogni ciclo, sono i modelli a priorità più alta/più cercati
QUERY_FISSE = [
    "carhartt wip detroit", "north face nuptse", "arc'teryx atom lt", "nike tech fleece",
    "timberland premium 6-inch wheat", "ralph lauren polo bear", "patagonia better sweater",
    "lululemon scuba",
]
# Query SECONDARIE (17) — a rotazione, 2 per ciclo, così in ~9 cicli (~72 sec) le copri tutte
QUERY_SECONDARIE = [
    "arc'teryx beta lt", "arc'teryx beta ar", "arc'teryx cerium lt",
    "patagonia retro-x", "patagonia retro pile", "patagonia synchilla", "lululemon align",
    "nike tech fleece jogger", "nike tech fleece tracksuit",
    "nike nocta",  # 1 query generica al posto delle 3 (hoodie/joggers/tracksuit li smista già valuta_articolo)
    "stussy 8 ball", "stussy world tour",  # slot liberati da Nocta, priorità #8 nel doc originale
    "stone island crewneck", "stone island hoodie", "stone island zip hoodie",
    "stone island overshirt", "stone island jacket",
]
rotazione_idx = 0  # avanza di 2 ogni ciclo, wrap su len(QUERY_SECONDARIE)

@tasks.loop(seconds=8)
async def controllo_vinted():
    global ultimo_affare, ultimo_report, rotazione_idx
    try:
        sess=get_session()
        headers={"User-Agent":USER_AGENTS[0],"Accept":"application/json","Referer":"https://www.vinted.it/"}
        pref=carica_pref()
        blacklist_globale=[]
        for data in pref.values():
            blacklist_globale.extend([b.lower() for b in data.get("blacklist_titoli",[]) if b and len(b)>=4])
        blacklist_globale=list(set(blacklist_globale))

        # 8 fisse + 2 a rotazione = max 10 query per ciclo, come richiesto
        secondarie_ciclo = [QUERY_SECONDARIE[(rotazione_idx+i) % len(QUERY_SECONDARIE)] for i in range(2)]
        rotazione_idx = (rotazione_idx + 2) % len(QUERY_SECONDARIE)
        queries_ciclo = QUERY_FISSE + secondarie_ciclo

        for term in queries_ciclo:
            q=urllib.parse.quote(term)
            url=f"https://www.vinted.it/api/v2/catalog/items?search_text={q}&order=newest_first&per_page=20"
            try:
                r=sess.get(url,headers=headers,timeout=10)
                if r.status_code!=200: continue
                for item in r.json().get("items",[]):
                    iid=str(item.get("id"))
                    if iid in gia_visti: continue
                    gia_visti.add(iid)
                    stats["scaricati"]+=1

                    # Freshness 180s: se il timestamp esiste ed è valido lo usiamo,
                    # se manca/è malformato NON scartiamo (fail-safe, imparato a nostre spese prima)
                    # ma lo contiamo, così nel report vediamo quanto spesso succede
                    cts = item.get("created_at_ts") or item.get("photo",{}).get("high_resolution",{}).get("timestamp")
                    try:
                        cts_val = float(cts)
                        if cts_val > 1e10: cts_val/=1000
                        if time.time() - cts_val > 180:
                            continue
                    except:
                        stats["freshness_sconosciuto"]+=1

                    titolo=item.get("title","")
                    if blacklist_globale and any(b in titolo.lower() for b in blacklist_globale):
                        continue

                    ris = await valuta_articolo(item)
                    if not ris: continue

                    m=ris["modello"]; tier=ris["tier"]; prezzo=ris["prezzo"]
                    link=f"https://www.vinted.it/items/{iid}"; foto=item.get("photo",{}).get("url","")
                    ultimo_affare={"titolo":ris["titolo"],"id":iid,"prezzo":prezzo}

                    emoji = "🟢" if tier=="AUTO-BUY" else "🟡"
                    titolo_embed = f"{emoji} {tier} — {m['brand'].upper()} {m['nome']} | {prezzo}€ | netto stimato +{round(ris['profitto_netto'])}€"
                    desc = (f"**{ris['titolo']}**\n\n"
                            f"Modello: {m['nome']}\nCondizione: {ris['condizione']}\nTaglia: {ris['size']}\n"
                            f"💰 Prezzo: {prezzo}€ (AUTO-BUY≤{ris['auto_buy_soglia']}€ | BUY MAX {ris['buy_max']}€)\n"
                            f"💸 SELL conservativo: {m['sell_min']}-{m['sell_max']}€\n"
                            f"📈 Profitto netto stimato: +{round(ris['profitto_netto'])}€ (min richiesto {m['profit_min']}€)\n"
                            f"⚠️ Verifica sempre le foto reali prima di comprare (rischio autenticità)\n"
                            f"[🚀 VAI ALL'ANNUNCIO]({link})")
                    canale=None
                    for g in bot.guilds:
                        for ch in g.text_channels:
                            if ch.permissions_for(g.me).send_messages: canale=ch; break
                        if canale: break
                    if canale:
                        colore = 0x2ecc71 if tier=="AUTO-BUY" else 0xf1c40f
                        emb=discord.Embed(title=titolo_embed,description=desc,color=colore)
                        if foto: emb.set_image(url=foto)
                        ping = "@everyone 🟢 AUTO-BUY!" if tier=="AUTO-BUY" else "@here 🟡 ALERT"
                        await canale.send(content=ping,embed=emb)
                await asyncio.sleep(0.8)
            except Exception as e:
                print(f"err {e}"); continue
        salva_visti()

        if time.time() - ultimo_report > 600:
            ultimo_report = time.time()
            canale=None
            for g in bot.guilds:
                for ch in g.text_channels:
                    if ch.permissions_for(g.me).send_messages: canale=ch; break
                if canale: break
            if canale:
                r = (f"🧪 **DEBUG 10 min** — scaricati:{stats['scaricati']} brand_no:{stats['brand_no']} "
                     f"modello_no:{stats['modello_no']} difetto:{stats['escluso_difetto']} stile:{stats['escluso_stile']} "
                     f"condizione_no:{stats['condizione_no']} taglia_no:{stats['taglia_no']} seller_rischio:{stats['seller_rischio']} "
                     f"profitto_basso:{stats['profitto_basso']} freshness_sconosciuto:{stats['freshness_sconosciuto']} "
                     f"ALERT:{stats['alert']} AUTO-BUY:{stats['auto_buy']}")
                await canale.send(r)
                for k in stats: stats[k]=0
    except Exception as e:
        print(e)

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        threading.Thread(target=run_flask,daemon=True).start()
        print("🔥 Avvio Bot Vinted V4 - modelli specifici, AUTO-BUY/ALERT")
        bot.run(tok)
