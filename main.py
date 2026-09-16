# FIX per main.py Vinted Bot V5.3
# Sostituisci la funzione crea_sessione_vinted() nel tuo main.py con questa.
# L'errore che hai in Render e' una parentesi ')' di troppo dopo launch_persistent_context().

async def crea_sessione_vinted():
    """Avvia un browser Chrome reale e mantiene una sessione persistente.

    Non usa token/cookie forniti dall'utente e non tenta bypass di CAPTCHA
    o sistemi anti-bot. Se Vinted blocca la sessione, il bot si ferma
    temporaneamente e riprova piu' tardi.
    """
    global vinted_browser, vinted_context, vinted_page, vinted_browser_ready

    if vinted_page is not None and not vinted_page.is_closed():
        return vinted_page

    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    pw = await async_playwright().start()

    try:
        vinted_context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            channel="chrome",
            headless=True,
            viewport={"width": 1440, "height": 900},
            locale="it-IT",
            user_agent=USER_AGENT,
            args=["--disable-notifications"],
        )
    except Exception:
        # Fallback al Chromium installato da Playwright. Nessun bypass.
        vinted_context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=os.getenv(
                "VINTED_HEADLESS", "false"
            ).strip().lower() == "true",
            viewport={"width": 1440, "height": 900},
            locale="it-IT",
            user_agent=USER_AGENT,
            args=["--disable-notifications"],
        )

    vinted_browser = pw
    vinted_page = (
        vinted_context.pages[0]
        if vinted_context.pages
        else await vinted_context.new_page()
    )
    vinted_browser_ready = False

    try:
        response = await vinted_page.goto(
            "https://www.vinted.it/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        status = response.status if response else 0

        if status in (401, 403, 429):
            log.warning(
                "Vinted homepage HTTP %s: sessione browser non pronta.",
                status,
            )
        else:
            vinted_browser_ready = True
            log.info(
                "Sessione browser Vinted pronta | homepage=%s",
                status,
            )

    except PlaywrightTimeoutError:
        log.warning("Timeout caricamento homepage Vinted.")

    except Exception as exc:
        log.warning(
            "Errore apertura homepage Vinted: %s",
            exc,
        )

    return vinted_page
