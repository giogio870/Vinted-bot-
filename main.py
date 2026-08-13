import discord
from discord.ext import commands, tasks
import requests, statistics, json, os, io
from PIL import Image, ImageEnhance
import datetime, random

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

FILTRI_FILE = "filtri.json"
CONFIG_FILE = "config.json"
CHAT_FILE = "chat_storico.json"
gia_visti = set()

BRANDS_LUXURY = ["balenciaga","louis vuitton","lv","gucci","prada","dior","fendi","off white","moncler","canada goose","chrome hearts"]
BRANDS_HYPE = ["stone island","c.p. company","cp company","nike","jordan","adidas","yeezy","north face","arcteryx","carhartt","new balance","barbour","supreme","stussy","palace","trapstar","nocta","tech fleece"]
BRANDS_CASUAL = ["lacoste","ralph lauren","tommy","levis","fred perry","lyle","dickies","patagonia","ea7","boss"]
BRANDS_CARTE = ["pokemon","charizard","psa","pikachu","panini","funko","lego"]

TUTTI = BRANDS_LUXURY + BRANDS_HYPE + BRANDS_CASUAL + BRANDS_CARTE + ["runner","lv skate","trainer","dunk","550","2002r","jordan 1","jordan 4"]

def carica_config():
    default = {
        "guadagno_min_netto_base": 18,
        "guadagno_min_netto_ideale": 20,
        "guadagno_mostro": 25,
        "guadagno_super_mostro": 30,
        "sconto_min": 42,
        "spedizione": 5,
        "autobuy": False,
        "autobuy_min_netto": 20
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                default.update(cfg)
                return default
        except:
            return default
    return default

def salva_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

CONFIG = carica_config()

def carica_filtri():
    if os.path.exists(FILTRI_FILE):
        try:
            with open(FILTRI_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def salva_filtri(f):
    with open(FILTRI_FILE, "w") as f2:
        json.dump(f, f2, indent=2)

def carica_chat():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def salva_chat(ch):
    with open(CHAT_FILE, "w") as f:
        json.dump(ch, f, indent=2)

def is_conosciuto(titolo, brand):
    t = (titolo + " " + brand).lower()
    filtri = carica_filtri()
    if filtri:
        for fl in filtri:
            if fl["keyword"] in t:
                return True
        return False
    return any(b in t for b in TUTTI)

def analizza_mercato_vendita(titolo):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        search = "%20".join(titolo.split()[:3])
        url = f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=25"
        r = requests.get(url, headers=headers, timeout=8)
        prezzi = []
        for it in r.json().get("items", []):
            p = it.get("price", {}).get("amount")
            try:
                if p and float(p) > 0:
                    prezzi.append(float(p))
            except:
                pass
        if len(prezzi) < 3:
            search2 = "%20".join(titolo.split()[:2])
            url2 = f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=25"
            r2 = requests.get(url2, headers=headers, timeout=7)
            prezzi2 = [float(i.get("price",{}).get("amount")) for i in r2.json().get("items",[]) if i.get("price",{}).get("amount")]
            if len(prezzi2) > len(prezzi):
                prezzi = prezzi2
        if len(prezzi) == 0:
            return None
        prezzi.sort()
        pu = prezzi[2:-2] if len(prezzi) >= 8 else prezzi
        mediana = statistics.median(pu)
        minimo = min(pu)
        massimo = max(pu)
        media = statistics.mean(pu)
        return {"valore": round(mediana,2), "media": round(media,2), "min": round(minimo,2), "max": round(massimo,2), "count": len(prezzi)}
    except:
        return None

def analizza_mostro(titolo, brand_input):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        search = "%20".join(titolo.split()[:3])
        url = f"https://www.vinted.it/api/v2/catalog/items?search_text={search}&per_page=30"
        r = requests.get(url, headers=headers, timeout=8)
        prezzi = []
        for it in r.json().get("items", []):
            p = it.get("price", {}).get("amount")
            try:
                if p and float(p) > 0:
                    prezzi.append(float(p))
            except:
                pass
        if len(prezzi) < 3:
            search2 = "%20".join(titolo.split()[:2])
            url2 = f"https://www.vinted.it/api/v2/catalog/items?search_text={search2}&per_page=30"
            r2 = requests.get(url2, headers=headers, timeout=7)
            prezzi2 = [float(i.get("price",{}).get("amount")) for i in r2.json().get("items",[]) if i.get("price",{}).get("amount")]
            if len(prezzi2) > len(prezzi):
                prezzi = prezzi2
        if len(prezzi) == 0:
            return None
        t_low = (titolo + " " + brand_input).lower()
        is_lux = any(b in t_low for b in BRANDS_LUXURY + ["jordan","dunk","balenciaga runner","lv skate","charizard","psa 10"])
        cnt = len(prezzi)
        if cnt <= 2 and not any(b in t_low for b in TUTTI):
            return None
        prezzi.sort()
        pu = prezzi[2:-2] if len(prezzi) >= 8 else prezzi
        mediana = statistics.median(pu)
        minimo = min(pu)
        massimo = max(pu)
        media = statistics.mean(pu)
        try:
            dev = statistics.stdev(pu) if len(pu)>=2 else 0
            instabile = dev > (media * 0.55)
            if is_lux:
                instabile = dev > (media * 0.65)
        except:
            instabile = False
        if instabile:
            return None
        return {"valore": round(mediana,2), "media": round(media,2), "min": round(minimo,2), "max": round(massimo,2), "count": cnt, "raro": cnt <= 3 and is_lux, "is_lux": is_lux, "confidenza_alta": cnt >= 5}
    except:
        return None

def genera_descrizione_vendita(nome_oggetto, brand_detected=""):
    nome_lower = nome_oggetto.lower()
    brand = brand_detected
    for b in TUTTI:
        if b in nome_lower:
            brand = b
            break
    mercato = analizza_mercato_vendita(nome_oggetto)
    if mercato:
        prezzo_consigliato = mercato["valore"]
        prezzo_veloce = round(prezzo_consigliato * 0.92, 2)
        prezzo_massimo = round(prezzo_consigliato * 1.05, 2)
    else:
        prezzo_consigliato = None
        prezzo_veloce = None
        prezzo_massimo = None
    titolo_seo = nome_oggetto.title()
    if brand and brand.lower() not in nome_lower:
        titolo_seo = f"{brand.title()} {titolo_seo}"
    descrizione = f"""🔥 {titolo_seo} - CONDIZIONI PERFETTE 🔥

✅ Brand: {brand.title() if brand else "Vedi foto"}
✅ Taglia: [Inserisci taglia]
✅ Condizioni: 9/10 - Usato pochissimo, nessun difetto
✅ Autenticità: 100% Originale

📦 Spedizione tracciata 24h
💨 Vendo per inutilizzo

#streetwear #hype #vinted"""
    return {"titolo_seo": titolo_seo, "descrizione": descrizione, "prezzo_consigliato": prezzo_consigliato, "prezzo_veloce": prezzo_veloce, "prezzo_massimo": prezzo_massimo, "mercato": mercato, "brand": brand}

def risposta_chat_infinita(user_id, messaggio, ha_foto=False):
    # Chat infinita - assistente reseller
    msg_lower = messaggio.lower()
    storico = carica_chat()
    user_history = storico.get(str(user_id), [])
    
    # Salva messaggio utente
    user_history.append({"role": "user", "content": messaggio, "time": str(datetime.datetime.now())})
    
    risposta = ""
    
    # Analizza intent
    if any(x in msg_lower for x in ["ciao","buongiorno","buonasera","ehi","hey"]):
        risposta = f"Ciao! 👋 Sono il tuo assistente reseller MOSTRO! \n\nPosso fare per te all'infinito:\n📦 **Vendere:** mandami foto + nome e ti faccio descrizione + prezzo\n💰 **Prezzo:** `!prezzo Stone Island` per sapere quanto vale\n📸 **Foto:** `!migliora` + foto per migliorare foto\n💥 **Affari:** ti notifico solo banger da 20€+ netti\n\nDimmi pure cosa vuoi vendere o chiedimi qualsiasi cosa su Vinted!"
    
    elif any(x in msg_lower for x in ["quanto vale","quanto posso","prezzo","quanto lo vendo","quanto lo metto"]):
        # Estrai oggetto
        oggetto = messaggio.replace("quanto vale","").replace("quanto posso vendere","").strip()
        if len(oggetto) < 3:
            oggetto = "oggetto"
        mercato = analizza_mercato_vendita(oggetto if len(oggetto)>2 else "Stone Island")
        if mercato:
            risposta = f"💰 **{oggetto} vale {mercato['valore']}€** (range {mercato['min']}-{mercato['max']}€ su {mercato['count']} annunci)\n\nConsiglio:\n• Veloce (24-48h): **{round(mercato['valore']*0.92,2)}€**\n• Normale: **{mercato['valore']}€**\n• Massimo: **{round(mercato['valore']*1.05,2)}€**\n\nVuoi che ti faccio descrizione pronta? Scrivi `!vendi {oggetto}`"
        else:
            risposta = "Dimmi nome preciso es: 'Stone Island felpa nera L' e ti dico prezzo al volo! Usa `!prezzo nome oggetto`"
    
    elif any(x in msg_lower for x in ["descrizione","descrivimi","fai descrizione","testo per vinted"]):
        oggetto = messaggio.replace("descrizione","").replace("fai","").strip()
        if len(oggetto) < 3:
            oggetto = "oggetto"
        result = genera_descrizione_vendita(oggetto)
        risposta = f"📦 **Descrizione pronta per {result['titolo_seo']}:**\n\n```{result['descrizione'][:1000]}```\n\nTitolo SEO: `{result['titolo_seo']}`\nPrezzo consigliato: {result['prezzo_veloce']}€ veloce"
    
    elif any(x in msg_lower for x in ["foto","immagine","migliora foto","foto brutta"]):
        risposta = "📸 Mandami foto con `!migliora` e te la miglioro subito!\n\nConsigli foto perfette Vinted:\n• Sfondo bianco/pavimento chiaro\n• Luce naturale finestra\n• 4 foto: fronte, retro, etichetta, dettaglio\n• Quadrata 1:1 vende di più!\n• Niente filtri, foto vere!"
    
    elif any(x in msg_lower for x in ["come vendere","consigli","trucchi","vendere veloce"]):
        risposta = "🚀 **TRUCCHI PER VENDERE VELOCE - Da mostro:**\n\n1. **Titolo:** Brand + modello + colore + taglia (es: Stone Island Felpa Nera L)\n2. **Foto:** 4 foto min, prima foto migliore\n3. **Prezzo:** 8% sotto media per vendere in 24h\n4. **Descrizione:** corta, con emoji, taglia, condizioni\n5. **Orario:** pubblica 18-21, più gente online\n6. **Boost:** dopo 2 giorni abbassa di 2€\n\nVuoi che ti analizzo un oggetto specifico?"
    
    elif any(x in msg_lower for x in ["guadagno","profitto","quanto guadagno","margine"]):
        cfg = carica_config()
        risposta = f"💰 **FILTRI GUADAGNO ATTUALI:**\n• Minimo flessibile: {cfg['guadagno_min_netto_base']}-{cfg['guadagno_min_netto_ideale']}€ netti (18-19 solo se super sicuro)\n• Banger: 20€+ verde\n• Mostro rosso: {cfg['guadagno_mostro']}€+\n• Super mostro viola: {cfg['guadagno_super_mostro']}€+\n• Sconto minimo: {cfg['sconto_min']}%\n• Spedizione: {cfg['spedizione']}€\n\nPuoi cambiare tutto con `!imposta guadagno 20` ecc. Vuoi alzare/abbassare?"
    
    elif ha_foto:
        risposta = "📸 Foto ricevuta! Dimmi nome oggetto es: 'Lacoste polo bianca M' e ti faccio descrizione + prezzo al volo! Oppure usa `!vendi nome` + foto o `!migliora` per migliorare foto!"
    
    else:
        # Risposta generica intelligente infinita
        risposte_random = [
            f"Interessante! Dimmi di più su '{messaggio[:30]}' - vuoi sapere prezzo, descrizione o consigli per venderlo?",
            f"Ok per '{messaggio[:30]}' posso aiutarti! Vuoi che ti dico quanto vale con `!prezzo` o ti faccio descrizione con `!vendi`?",
            f"Capito! Per '{messaggio[:30]}' ti consiglio di mandarmi foto + nome preciso e ti faccio analisi completa mercato + descrizione perfetta!",
            f"Sono qui per te all'infinito! Chiedimi qualsiasi cosa su Vinted: prezzi, descrizioni, foto, trucchi vendita, filtri guadagno... cosa vuoi sapere su '{messaggio[:30]}'?"
        ]
        risposta = random.choice(risposte_random) + "\n\n**Comandi veloci:**\n`!vendi nome + foto` | `!prezzo nome` | `!migliora + foto` | `!config`"
    
    # Salva risposta
    user_history.append({"role": "assistant", "content": risposta, "time": str(datetime.datetime.now())})
    # Tieni solo ultimi 20 messaggi per non appesantire
    if len(user_history) > 20:
        user_history = user_history[-20:]
    storico[str(user_id)] = user_history
    salva_chat(storico)
    
    return risposta

@bot.event
async def on_ready():
    cfg = carica_config()
    print(f"Bot ULTRA MOSTRO V13 CHAT INFINITA - ATB={cfg.get('autobuy')} {bot.user}")
    controllo_vinted.start()

@bot.command()
async def filtro(ctx, azione=None, *, args=""):
    filtri = carica_filtri()
    if azione == "add":
        parti = args.rsplit(" ", 1)
        if len(parti) != 2:
            await ctx.send("Usa: !filtro add balenciaga runner 100")
            return
        kw, pr = parti[0].lower(), parti[1]
        try: pr=float(pr)
        except: return
        filtri.append({"keyword":kw,"max":pr})
        salva_filtri(filtri)
        await ctx.send(f"Aggiunto: {kw} sotto {pr} euro")
    elif azione == "lista" or azione is None:
        cfg = carica_config()
        atb_status = "🟢 ATB SI sopra 20€ netti" if cfg.get("autobuy") else "🔴 ATB NO"
        await ctx.send(f"ULTRA MOSTRO V13 CHAT INFINITA:\n- Sniping: 18-20€ min, 25 ROSSO, 30 VIOLA\n- Chat privata infinita: chiedimi qualsiasi cosa!\n- Vendita: !vendi !prezzo !migliora\n{atb_status}")

@bot.command()
async def filtri(ctx):
    await ctx.invoke(bot.get_command("filtro"), azione="lista")

@bot.command()
async def atb(ctx, stato=None):
    cfg = carica_config()
    if stato is None:
        status = "SI sopra 20€ netti 🤖" if cfg.get("autobuy") else "NO 🔕"
        await ctx.send(f"ATB: **{status}** - Usa !atb si / !atb no")
        return
    stato = stato.lower()
    if stato in ["si","sì","yes","on"]:
        cfg["autobuy"] = True
        cfg["autobuy_min_netto"] = 20
        salva_config(cfg)
        await ctx.send("✅ **ATB SI** - Compra da solo sopra 20€ netti")
    elif stato in ["no","off"]:
        cfg["autobuy"] = False
        salva_config(cfg)
        await ctx.send("🔴 **ATB NO**")
    elif "soglia" in ctx.message.content:
        try:
            parts = ctx.message.content.split()
            soglia = float(parts[2])
            cfg["autobuy_min_netto"] = soglia
            salva_config(cfg)
            await ctx.send(f"Soglia Auto Buy: {soglia}€ netti")
        except:
            await ctx.send("Usa: !atb soglia 20")

@bot.command()
async def autobuy(ctx, stato=None):
    await ctx.invoke(bot.get_command("atb"), stato=stato)

@bot.command()
async def imposta(ctx, cosa=None, valore=None):
    cfg = carica_config()
    if cosa=="guadagno" and valore:
        try:
            netto=float(valore)
            cfg["guadagno_min_netto_ideale"]=netto
            cfg["guadagno_min_netto_base"]=netto-2
            salva_config(cfg)
            await ctx.send(f"Ora minimo {netto-2}-{netto}€ netti - Puoi chattare all'infinito per cambiare quando vuoi!")
        except:
            pass
    elif cosa=="sconto" and valore:
        try:
            cfg["sconto_min"]=float(valore)
            salva_config(cfg)
            await ctx.send(f"Sconto minimo {valore}%")
        except:
            pass
    elif cosa=="spedizione" and valore:
        try:
            cfg["spedizione"]=float(valore)
            salva_config(cfg)
            await ctx.send(f"Spedizione {valore}€")
        except:
            pass
    else:
        atb_txt = "SI" if cfg.get("autobuy") else "NO"
        await ctx.send(f"⚙️ FILTRI FACILI (cambi all'infinito in chat):\nGuadagno: {cfg['guadagno_min_netto_base']}-{cfg['guadagno_min_netto_ideale']} netti\nMostro rosso: {cfg['guadagno_mostro']}€\nViola: {cfg['guadagno_super_mostro']}€\nSconto: {cfg['sconto_min']}%\nATB: {atb_txt}\n\nComandi: !imposta guadagno 20, !imposta sconto 45, !atb si/no")

@bot.command()
async def config(ctx):
    await ctx.invoke(bot.get_command("imposta"))

@bot.command()
async def vendi(ctx, *, nome_oggetto=""):
    if len(ctx.message.attachments) == 0 and nome_oggetto == "":
        await ctx.send("📸 **MANDAMI FOTO + NOME**\nEs: `!vendi Stone Island maglia nera L` + foto\nOppure chatta con me all'infinito in privato!")
        return
    if len(ctx.message.attachments) > 0 and nome_oggetto == "":
        nome_oggetto = "oggetto da vendere"
    result = genera_descrizione_vendita(nome_oggetto)
    embed = discord.Embed(title=f"📦 VENDITA: {result['titolo_seo'][:50]}", description=f"**Titolo SEO:** `{result['titolo_seo']}`\n\n**Descrizione:**\n```{result['descrizione'][:1500]}```", color=0x00ff88)
    if result["mercato"]:
        embed.add_field(name="💰 Mercato", value=f"{result['mercato']['valore']}€ (range {result['mercato']['min']}-{result['mercato']['max']}€)", inline=False)
        embed.add_field(name="⚡ Veloce", value=f"{result['prezzo_veloce']}€", inline=True)
        embed.add_field(name="💎 Max", value=f"{result['prezzo_massimo']}€", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def prezzo(ctx, *, nome_oggetto=""):
    if nome_oggetto == "":
        await ctx.send("Usa: `!prezzo Stone Island maglia`")
        return
    await ctx.send(f"🔍 Cerco prezzo per: {nome_oggetto}...")
    mercato = analizza_mercato_vendita(nome_oggetto)
    if not mercato:
        await ctx.send("❌ Non trovato, prova nome più generico - chatta con me per aiuto!")
        return
    embed = discord.Embed(title=f"💰 PREZZO: {nome_oggetto[:40]}", description=f"**Valore:** {mercato['valore']}€\n**Range:** {mercato['min']}-{mercato['max']}€\n**Veloce:** {round(mercato['valore']*0.92,2)}€\n**Massimo:** {round(mercato['valore']*1.05,2)}€", color=0xffaa00)
    await ctx.send(embed=embed)

@bot.command()
async def migliora(ctx):
    if len(ctx.message.attachments) == 0:
        await ctx.send("📸 Allega foto con `!migliora` e te la miglioro!")
        return
    await ctx.send("✨ Miglioro foto...")
    try:
        attachment = ctx.message.attachments[0]
        img_data = await attachment.read()
        img = Image.open(io.BytesIO(img_data))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.1)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.3)
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.15)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        buffer.seek(0)
        file = discord.File(buffer, filename="foto_migliorata.jpg")
        embed = discord.Embed(title="✨ FOTO MIGLIORATA!", description="✅ Contrasto +20%\n✅ Luce +10%\n✅ Nitidezza +30%\n✅ Colori +15%\n\nConsigli: sfondo chiaro, luce naturale, 4 foto!", color=0x9b59b6)
        await ctx.send(embed=embed, file=file)
    except Exception as e:
        await ctx.send(f"Errore: {e}")

@bot.command()
async def chat(ctx, *, messaggio=""):
    if messaggio == "":
        await ctx.send("💬 Chat infinita! Scrivimi qualsiasi cosa: prezzi, descrizioni, consigli, filtri...")
        return
    risposta = risposta_chat_infinita(ctx.author.id, messaggio, False)
    await ctx.send(risposta)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # CHAT INFINITA IN PRIVATO
    if isinstance(message.channel, discord.DMChannel):
        # Se è comando, processa comando
        if message.content.startswith("!"):
            await bot.process_commands(message)
            return
        
        # Altrimenti chat infinita
        ha_foto = len(message.attachments) > 0
        if ha_foto:
            # Foto + testo
            nome = message.content if message.content else "oggetto in foto"
            await message.channel.send("📸 Foto ricevuta! Analizzo e ti rispondo...")
            result = genera_descrizione_vendita(nome)
            risposta = risposta_chat_infinita(message.author.id, nome + " foto", True)
            embed = discord.Embed(title=f"📦 Analizzato: {result['titolo_seo'][:40]}", description=risposta[:1800], color=0x00ff88)
            if result["mercato"]:
                embed.add_field(name="Prezzo veloce", value=f"{result['prezzo_veloce']}€", inline=True)
            await message.channel.send(embed=embed)
            return
        else:
            # Solo testo - chat infinita
            risposta = risposta_chat_infinita(message.author.id, message.content, False)
            await message.channel.send(risposta)
            return
    
    # Se nel server e menziona bot
    if bot.user in message.mentions and not message.content.startswith("!"):
        risposta = risposta_chat_infinita(message.author.id, message.content, len(message.attachments)>0)
        await message.channel.send(f"{message.author.mention} {risposta}")
        return
    
    await bot.process_commands(message)

@tasks.loop(seconds=1.2)
async def controllo_vinted():
    try:
        cfg = carica_config()
        url="https://www.vinted.it/api/v2/catalog/items?order=newest_first&per_page=35"
        headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
        r=requests.get(url,headers=headers,timeout=8)
        for item in r.json().get("items",[]):
            iid=str(item["id"])
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
            if prezzo<3 or prezzo>800:
                continue
            if not is_conosciuto(titolo, brand):
                continue
            filtri=carica_filtri()
            if filtri:
                if not any(f["keyword"] in titolo_low and prezzo <= f["max"] for f in filtri):
                    continue
            mercato=analizza_mostro(titolo, brand)
            if not mercato:
                continue
            valore=mercato["valore"]
            diff=valore-prezzo
            netto=diff-cfg["spedizione"]
            sconto=(diff/valore*100) if valore>0 else 0
            roi=(diff/prezzo*100) if prezzo>0 else 0
            ok=False
            livello="normale"
            if netto >= 30:
                if sconto >= 30:
                    ok=True
                    livello="super_mostro"
            elif netto >= 25:
                if sconto >= 35:
                    ok=True
                    livello="mostro"
            elif netto >= 20:
                if sconto >= 42:
                    ok=True
                    livello="banger"
            elif netto >= 18:
                if sconto >= 50 and mercato.get("confidenza_alta"):
                    ok=True
                    livello="accettabile"
            if not ok:
                continue
            if netto < cfg["guadagno_min_netto_base"]:
                continue
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
                atb_attivo = cfg.get("autobuy", False)
                soglia_atb = cfg.get("autobuy_min_netto", 20)
                auto_buy_msg = ""
                if atb_attivo and netto >= soglia_atb:
                    successo, msg = tenta_autobuy(iid, titolo, prezzo)
                    auto_buy_msg = f"\n🤖 **AUTO BUY:** {msg}"
                if livello == "super_mostro":
                    color=0x9b59b6
                    titolo_embed=f"🟣 MOSTRO ASSOLUTO {round(netto)}€ NETTI 🟣: {titolo[:40]}"
                    desc_extra="🟣🟣🟣 **VIOLA - SUPER MOSTRO 30€+!** 🟣🟣🟣\n"
                elif livello == "mostro":
                    color=0xff0000
                    titolo_embed=f"🔴 MOSTRO {round(netto)}€ NETTI: {titolo[:45]}"
                    desc_extra="🔴 **ROSSO - MOSTRO 25€+!**\n"
                elif livello == "banger":
                    color=0x00ff88
                    titolo_embed=f"💥 BANGER {round(netto)}€ NETTI: {titolo[:45]}"
                    desc_extra=""
                else:
                    color=0xffaa00
                    titolo_embed=f"💧 BUONO {round(netto)}€ NETTI: {titolo[:45]}"
                    desc_extra="(18-19€ super sicuro)\n"
                fake_warning=""
                if mercato.get("is_lux") and sconto>75:
                    fake_warning="⚠️ Possibile fake!\n"
                atb_info = f"\nATB: {'🟢 SI sopra 20€' if atb_attivo else '🔴 NO'} {auto_buy_msg}"
                embed=discord.Embed(title=titolo_embed, description=f"{desc_extra}**Brand:** {brand}\n**Acquisto:** {prezzo}€\n**Rivendita:** **{valore}€** (range {mercato['min']}-{mercato['max']}€ su {mercato['count']})\n**LORDO:** {round(diff)}€ → **NETTO: {round(netto)}€** ✅\n**Sconto:** {round(sconto)}%\n**ROI:** {round(roi)}%\n{fake_warning}{atb_info}\n[👉 PRENDI!]({link})", color=color)
                if foto:
                    embed.set_image(url=foto)
                embed.set_footer(text=f"V13 CHAT INFINITA | Netto {round(netto)}€ | ROI {round(roi)}%")
                content = "@everyone 🟣 VIOLA 30€+!" if livello=="super_mostro" else "@here 🔴 MOSTRO 25€+!" if livello=="mostro" else ""
                await canale.send(content=content, embed=embed)
    except Exception as e:
        print(f"Errore: {e}")

from flask import Flask
app=Flask(__name__)
@app.route("/")
def home():
    return "Bot ULTRA MOSTRO V13 - Chat infinita!"
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
import threading
threading.Thread(target=run_flask, daemon=True).start()

if __name__=="__main__":
    tok=os.getenv("DISCORD_TOKEN")
    if tok:
        bot.run(tok)
