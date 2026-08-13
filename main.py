import discord
from discord.ext import commands, tasks
import requests, statistics, os, time, re
import threading
from datetime import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG = {
    "guadagno_min_netto_base": 18,
    "guadagno_min_netto_ideale": 20,
    "guadagno_mostro": 25,
    "guadagno_super_mostro": 30,
    "spedizione": 5,
    "prezzo_max": 200,
    "prezzo_min": 3,
    "autobuy": False,
    "autobuy_min_netto": 20,
    "intelligenza_minima": 75,  # solo cose che l'AI capisce che si vendono facile
}

# === INTELLIGENZA ASSOLUTA - TANTISSIMI DATI ===
# Brand quanto piace alla gente (0-100)
BRAND_SCORE = {
    "stone island": 98, "c.p. company": 97, "cp company": 97,
    "lacoste": 92, "ralph lauren": 94, "polo ralph lauren": 94,
    "nike": 90, "jordan": 96, "nike dunk": 93, "jordan 1": 97,
    "adidas": 85, "new balance": 88, "new balance 550": 90,
    "north face": 89, "carhartt": 87, "supreme": 95, "stussy": 88,
    "tommy hilfiger": 82, "levis": 80, "fred perry": 78,
    "pokemon": 90, "charizard": 99, "psa 10": 99,
    "balenciaga": 85, "louis vuitton": 88, "moncler": 90,
}

# Colori che si vendono facilmente vs no (0-100)
COLORE_SCORE = {
    "nero": 95, "black": 95, "blu": 90, "navy": 92, "blue": 90,
    "bianco": 88, "white": 88, "grigio": 85, "grey": 85, "gray": 85,
    "verde": 75, "green": 75, "marrone": 70, "brown": 70,
    "beige": 65, "rosso": 60, "red": 60,
    "giallo": 35, "yellow": 35, "rosa": 40, "pink": 40, "arancione": 30, "orange": 30,
    "viola": 45, "purple": 45, "celeste": 50, "azzurro": 55,
}

# Taglie che si vendono di più
TAGLIA_SCORE = {
    "m": 95, "l": 92, "s": 85, "xl": 80, "xs": 60, "xxl": 55, "xxxl": 40,
    "42": 90, "43": 92, "44": 88, "41": 85, "40": 80, "45": 75, "39": 70,
}

FILTRI_UTENTE = []
gia_visti = set()
CACHE = {}
session = requests.Session()
session.headers.update({"User-Agent":"Mozilla/5.0","Accept":"application/json"})
try: session.get("https://www.vinted.it", timeout=3)
except: pass

def estrai_colore(titolo):
    t = titolo.lower()
    for colore, score in COLORE_SCORE.items():
        if colore in t:
            return colore, score
    return "non rilevato", 60  # neutro

def estrai_taglia(titolo):
    t = titolo.lower()
    # cerca taglia tipo " M " o " L " o "42"
    m = re.search(r'\b(xs|s|m|l|xl|xxl|xxxl|39|40|41|42|43|44|45)\b', t)
    if m:
        taglia = m.group(1)
        return taglia, TAGLIA_SCORE.get(taglia, 70)
    return "non rilevata", 70

def calcola_intelligenza_assoluta(titolo, brand_vinted, prezzo, fav_count, view_count, colore, taglia):
    """
    ROBOT PIU' INTELLIGENTE DEL MONDO
    Riconosce cosa si vende facile e cosa no in base a:
    - marca (quanto piace)
    - colore (nero vende, giallo no)
    - taglia (M/L vendono, XXXL no)
    - likes (quanti like ha)
    - views (quante views)
    - prezzo (troppo alto non vende)
    - tantissimi dati di mercato
    """
    testo = f"{titolo} {brand_vinted}".lower()
    score_tot = 0
    dettagli = []
    
    # 1) BRAND SCORE (40% peso) - quanto piace la gente
    brand_score = 50  # default se non conosce
    brand_trovato = None
    for b, s in BRAND_SCORE.items():
        if b in testo:
            if s > brand_score:
                brand_score = s
                brand_trovato = b
    score_tot += brand_score * 0.4
    dettagli.append(f"Marca {brand_trovato or 'sconosciuta'}: {brand_score}/100 (piace {'molto' if brand_score>=90 else 'medio' if brand_score>=70 else 'poco'})")
    
    # 2) COLORE SCORE (20% peso) - colori che vendono
    col_score = COLORE_SCORE.get(colore.lower(), 60) if colore != "non rilevato" else 60
    score_tot += col_score * 0.2
    dettagli.append(f"Colore {colore}: {col_score}/100 ({'vende facile' if col_score>=85 else 'vende medio' if col_score>=60 else 'non vende facile'})")
    
    # 3) TAGLIA SCORE (15% peso)
    taglia_score = taglia[1] if isinstance(taglia, tuple) else 70
    if isinstance(taglia, tuple):
        taglia_score = taglia[1]
        taglia_nome = taglia[0]
    else:
        taglia_nome = str(taglia)
        taglia_score = TAGLIA_SCORE.get(taglia_nome.lower(), 70)
    score_tot += taglia_score * 0.15
    dettagli.append(f"Taglia {taglia_nome}: {taglia_score}/100")
    
    # 4) LIKE/VIEWS SCORE (15% peso) - quanto piace alla gente REALMENTE
    like_score = 50
    if fav_count is not None:
        if fav_count >= 20: like_score = 95
        elif fav_count >= 10: like_score = 85
        elif fav_count >= 5: like_score = 75
        elif fav_count >= 2: like_score = 60
        else: like_score = 40
        dettagli.append(f"Like {fav_count}: {like_score}/100 (piace {'molto' if like_score>=85 else 'poco' if like_score<60 else 'medio'})")
    else:
        dettagli.append(f"Like non rilevati: 50/100")
    score_tot += like_score * 0.15
    
    # 5) PREZZO SCORE (10% peso) - prezzo troppo alto non vende
    prezzo_score = 100
    if prezzo > 150: prezzo_score = 30
    elif prezzo > 100: prezzo_score = 60
    elif prezzo > 70: prezzo_score = 80
    elif prezzo > 30: prezzo_score = 90
    else: prezzo_score = 85  # prezzo basso vende ma meno profitto
    score_tot += prezzo_score * 0.1
    dettagli.append(f"Prezzo {prezzo}€: {prezzo_score}/100")
    
    intelligenza = int(score_tot)
    vende_facile = intelligenza >= 75
    return intelligenza, vende_facile, dettagli, brand_trovato

def analizza_mercato_completo(titolo, brand_input=""):
    key = " ".join(titolo.lower().split()[:3])
    now = time.time()
    if key in CACHE:
        val, ts = CACHE[key]
        if now - ts < 300: return val
    try:
        search = "%20".join(titolo.split()[:3])
        url = f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=40"
        r = session.get(url, timeout=7)
        items = r.json().get("items", [])
        prezzi = [float(i.get("price",{}).get("amount",0)) for i in items if i.get("price",{}).get("amount")]
        if len(prezzi) < 4:
            search2 = "%20".join(titolo.split()[:2])
            url2 = f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=40"
            r2 = session.get(url2, timeout=6)
            prezzi2 = [float(i.get("price",{}).get("amount",0)) for i in r2.json().get("items",[]) if i.get("price",{}).get("amount")]
            if len(prezzi2) > len(prezzi): prezzi = prezzi2
        if len(prezzi) < 3: return None
        prezzi.sort()
        pu = prezzi[1:-1] if len(prezzi)>=6 else prezzi
        mediana = statistics.median(pu)
        media = statistics.mean(pu)
        minimo = min(pu)
        massimo = max(pu)
        try:
            q1 = statistics.quantiles(pu, n=4)[0]
            q3 = statistics.quantiles(pu, n=4)[2]
        except:
            q1 = pu[len(pu)//4]
            q3 = pu[3*len(pu)//4]
        dev = statistics.stdev(pu) if len(pu)>=2 else 0
        molto_ricercato = len(prezzi) >= 5 and dev < (media * 0.50)
        raro_ricercato = len(prezzi) <= 3 and any(b in titolo.lower() for b in ["charizard","psa 10","jordan","balenciaga"])
        sicuro = dev < (media * 0.45) and len(prezzi) >= 6
        result = {
            "valore": round(mediana,2), "media": round(media,2),
            "min": round(minimo,2), "max": round(massimo,2),
            "q1": round(q1,2), "q3": round(q3,2),
            "count": len(prezzi), "dev": round(dev,2),
            "sicuro": sicuro, "molto_ricercato": molto_ricercato, "raro_ricercato": raro_ricercato
        }
        CACHE[key] = (result, now)
        return result
    except: return None

@bot.event
async def on_ready():
    print(f"✅ V22 INTELLIGENZA ASSOLUTA - ROBOT PIU' INTELLIGENTE DEL MONDO - {bot.user}")
    controllo_vinted.start()

@bot.command()
async def filtro(ctx, keyword: str, max_prezzo: float):
    FILTRI_UTENTE.append({"keyword": keyword.lower(), "max": max_prezzo})
    await ctx.send(f"✅ Filtro: {keyword} max {max_prezzo}€")

@bot.command()
async def intelligenza(ctx):
    await ctx.send(
        f"🤖 **V22 INTELLIGENZA ASSOLUTA - ROBOT PIU' INTELLIGENTE DEL MONDO**\n"
        f"Riconosce cosa si vende facile e cosa no in base a:\n"
        f"• **Marca** (Stone Island 98/100 piace molto, EA7 50/100 piace poco)\n"
        f"• **Colore** (nero 95/100 vende facile, giallo 35/100 non vende)\n"
        f"• **Taglia** (M 95/100 vende facile, XXXL 40/100 no)\n"
        f"• **Likes** (20 like = 95/100 piace molto)\n"
        f"• **Prezzo** + **tantissimi dati** di mercato\n"
        f"Score >=75 = si vende facile! Lui fa tutto da solo!"
    )

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.guild is None and not message.content.startswith("!"):
        await message.channel.send(f"🤖 V22 INTELLIGENZA ASSOLUTA! Io riconosco da solo cosa si vende facile e cosa no in base a colori, marca, quanto piace alla gente, tantissimi dati! Sono il robot più intelligente del mondo per vestiti di mercato! Scrivi !intelligenza")
        return
    await bot.process_commands(message)

@tasks.loop(seconds=0.9)
async def controllo_vinted():
    try:
        url="https://www.vinted.it/api/v2/catalog/items?order=newest_first&per_page=60"
        r=session.get(url, timeout=8)
        for item in r.json().get("items",[]):
            iid=str(item["id"])
            if iid in gia_visti: continue
            gia_visti.add(iid)
            titolo=item.get("title","")
            brand=item.get("brand_title","")
            desc=item.get("description","")[:200]
            try: prezzo=float(item.get("price",{}).get("amount"))
            except: continue
            if prezzo<CONFIG["prezzo_min"] or prezzo>CONFIG["prezzo_max"]: continue

            # Dati per intelligenza
            fav_count = item.get("favourite_count") or item.get("favourites_count") or 0
            view_count = item.get("view_count") or 0
            colore, col_score = estrai_colore(titolo + " " + desc)
            taglia_nome, taglia_score = estrai_taglia(titolo + " " + desc)
            
            # INTELLIGENZA ASSOLUTA - calcola se si vende facile
            intelligenza, vende_facile, dettagli_int, brand_trovato = calcola_intelligenza_assoluta(
                titolo, brand, prezzo, fav_count, view_count, colore, (taglia_nome, taglia_score)
            )
            
            # Se non si vende facile, scarta! Lui fa tutto da solo!
            if intelligenza < CONFIG["intelligenza_minima"]:
                continue

            if FILTRI_UTENTE:
                if not any(f["keyword"] in titolo.lower() for f in FILTRI_UTENTE): continue

            mercato=analizza_mercato_completo(titolo, brand)
            if not mercato: continue
            if not (mercato["molto_ricercato"] or mercato["raro_ricercato"] or mercato["count"]>=4): continue

            valore=mercato["valore"]
            netto=(valore-prezzo)-CONFIG["spedizione"]
            if netto < CONFIG["guadagno_min_netto_base"]: continue

            link=f"https://www.vinted.it/items/{iid}"
            foto=item.get("photo",{}).get("url","")
            canale=None
            for g in bot.guilds:
                for ch in g.text_channels:
                    if ch.permissions_for(g.me).send_messages:
                        canale=ch; break
                if canale: break
            if canale:
                if netto>=30: color=0x9b59b6; emoji="🟣"
                elif netto>=25: color=0xff0000; emoji="🔴"
                elif netto>=20: color=0x00ff88; emoji="💥"
                else: color=0xffaa00; emoji="💧"

                dettagli_txt = "\n".join([f"• {d}" for d in dettagli_int[:4]])
                embed=discord.Embed(
                    title=f"{emoji} {round(netto)}€ NETTI - AI {intelligenza}/100 VENDE FACILE - {titolo[:35]}",
                    description=(
                        f"**🤖 INTELLIGENZA ASSOLUTA {intelligenza}/100 - {'VENDE FACILE' if vende_facile else 'NON VENDE FACILE'}**\n"
                        f"{dettagli_txt}\n\n"
                        f"**Brand:** {brand_trovato or brand} | **Colore:** {colore} | **Taglia:** {taglia_nome}\n"
                        f"**Like:** {fav_count} | **Views:** {view_count}\n"
                        f"**Acquisto:** {prezzo}€\n"
                        f"📊 **Sicurezza statistica su {mercato['count']} pezzi:**\n"
                        f"Rivendita **TRA {mercato['q1']}€ e {mercato['q3']}€** (mediana {mercato['valore']}€)\n"
                        f"**ESEMPIO:** compri a {prezzo}€, rivendi tra {mercato['q1']}-{mercato['q3']}€ → **+{round(netto)}€ NETTI**\n"
                        f"[👉 PRENDI!]({link})"
                    ),
                    color=color
                )
                if foto: embed.set_image(url=foto)
                embed.set_footer(text=f"V22 INTELLIGENZA ASSOLUTA - {intelligenza}/100 - {mercato['count']} pezzi - Netto {round(netto)}€ - Fa tutto lui!")
                content = "@everyone 🟣" if netto>=30 else "@here 🔴" if netto>=25 else ""
                await canale.send(content=content, embed=embed)
    except Exception as e:
        print(f"Errore V22: {e}")

from flask import Flask
app=Flask(__name__)
@app.route("/")
def home(): return f"V22 INTELLIGENZA ASSOLUTA - Robot più intelligente del mondo - Visti {len(gia_visti)}"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
threading.Thread(target=run_flask, daemon=True).start()

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok: bot.run(tok)
