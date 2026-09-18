import requests
import time

BASE = "https://www.vinted.it"
API = f"{BASE}/api/v2/catalog/items"

def main():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    })

    print("=== TEST VINTED HTTP ===")
    print("1) Homepage Vinted...")
    try:
        r = s.get(BASE, timeout=20, allow_redirects=True)
        print(f"   Homepage: HTTP {r.status_code}")
        print(f"   URL finale: {r.url}")
        print(f"   access_token_web presente: {'access_token_web' in s.cookies}")
        print(f"   Cookie ricevuti: {len(s.cookies)}")
    except Exception as e:
        print(f"   ERRORE homepage: {type(e).__name__}: {e}")
        return

    time.sleep(1)
    print("\n2) Catalog API con ricerca 'the north face nuptse'...")
    headers = {
        "User-Agent": s.headers["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Referer": f"{BASE}/catalog?search_text=the%20north%20face%20nuptse",
        "Origin": BASE,
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {"search_text": "the north face nuptse", "order": "newest_first", "per_page": 5, "page": 1}

    try:
        r = s.get(API, params=params, headers=headers, timeout=20)
        print(f"   Catalog: HTTP {r.status_code}")
        print(f"   URL chiamata: {r.url}")
        print(f"   Content-Type: {r.headers.get('Content-Type', '')}")
        if r.status_code == 200:
            try:
                data = r.json()
                items = data.get("items", []) if isinstance(data, dict) else []
                print(f"   ANNUNCI TROVATI: {len(items)}")
                for i, item in enumerate(items[:5], 1):
                    title = item.get("title", "?")
                    item_id = item.get("id", "?")
                    price = item.get("price", {})
                    print(f"   {i}. ID={item_id} | {title} | prezzo={price}")
                print("\nRISULTATO: VINTED API RISPONDE CORRETTAMENTE.")
            except Exception as e:
                print(f"   HTTP 200 ma JSON non leggibile: {type(e).__name__}: {e}")
                print(f"   Prime 3000 caratteri risposta:\n{r.text[:3000]}")
        else:
            print("\nRISULTATO: VINTED API NON RESTITUISCE GLI ANNUNCI.")
            print("Questo test NON prova che i brand siano il problema.")
            if r.status_code in (401, 403):
                print("Indicazione: autenticazione/sessione o protezione anti-bot.")
            elif r.status_code == 404:
                print("Indicazione: endpoint catalogo non disponibile/compatibile da questo ambiente.")
            else:
                print("Indicazione: risposta HTTP anomala da Vinted.")
    except Exception as e:
        print(f"\nRISULTATO: ERRORE DI RETE: {type(e).__name__}: {e}")
    print("\n=== FINE TEST ===")

if __name__ == "__main__":
    main()
