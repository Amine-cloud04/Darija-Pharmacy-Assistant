import re
import sqlite3
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ammps.gov.ma/recherche-medicaments"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

def clean_text(element):
    if not element:
        return None
    text = element.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()

def extract_labeled_field(container, label_pattern):
    """Finds text following a label like 'DOSAGE :', 'EPI :', etc."""
    if not container:
        return None
    match = re.search(rf"{label_pattern}\s*:\s*([^<\n]+)", container.get_text(), re.IGNORECASE)
    return match.group(1).strip() if match else None

def parse_card_and_modal(card, soup):
    # Extract ID from data-bs-target (e.g., '#medicamentModal5021' -> '5021')
    target_modal_id = card.get("data-bs-target", "").replace("#", "")
    modal = soup.find("div", id=target_modal_id) if target_modal_id else None

    # 1. Title / Specialite
    title_el = card.select_one(".medicament-title")
    specialite = clean_text(title_el)

    # 2. Substance Active
    substance_el = card.select_one(".medicament-substance")
    substance = clean_text(substance_el)
    if substance:
        substance = re.sub(r"^SUBSTANCE ACTIVE\s*:\s*", "", substance, flags=re.IGNORECASE)

    # 3. Presentation
    pres_el = card.select_one(".medicament-presentation")
    presentation = clean_text(pres_el)
    if presentation:
        presentation = re.sub(r"^PR[ÉE]SENTATION\s*:\s*", "", presentation, flags=re.IGNORECASE)

    # 4. Forme
    forme_el = card.select_one(".medicament-forme")
    forme = clean_text(forme_el)

    # 5. Prices (PPV and PH)
    price_row = card.select_one(".medicament-price-row")
    ppv, ph = None, None
    if price_row:
        price_text = price_row.get_text(" ")
        ppv_match = re.search(r"PPV\s*([\d\.\,\s]+DH)", price_text, re.IGNORECASE)
        ph_match = re.search(r"PH\s*([\d\.\,\s]+DH)", price_text, re.IGNORECASE)
        ppv = ppv_match.group(1).strip() if ppv_match else None
        ph = ph_match.group(1).strip() if ph_match else None

    # 6. Dosage, EPI, and Statut (from Modal or Card fallback)
    dosage, epi, statut = None, None, None
    
    # Check card text for inline dosage
    dosage = extract_labeled_field(card, "DOSAGE")
    
    if modal:
        if not dosage:
            dosage = extract_labeled_field(modal, "DOSAGE")
        epi = extract_labeled_field(modal, "EPI")
        
        # Check statut badge in modal
        badge = modal.find(class_=lambda c: c and "badge" in c.lower())
        if badge:
            statut = clean_text(badge)
        elif "commercialisé" in modal.get_text().lower():
            statut = "Commercialisé" if "non" not in modal.get_text().lower() else "Non commercialisé"
    else:
        # Fallback if modal container is absent
        if "commercialisé" in card.get_text().lower():
            statut = "Commercialisé" if "non" not in card.get_text().lower() else "Non commercialisé"

    return {
        "id": target_modal_id.replace("medicamentModal", ""),
        "specialite": specialite,
        "substance_active": substance,
        "dosage": dosage,
        "forme": forme,
        "presentation": presentation,
        "epi": epi,
        "statut": statut,
        "ppv": ppv,
        "ph": ph
    }

def run_scraper(start_page=1, max_pages=10, db_name="pharmacy.db"):
    session = requests.Session()
    all_data = []

    print(f"[*] Starting scraper: pages {start_page} to {max_pages}...")

    for page in range(start_page, max_pages + 1):
        url = f"{BASE_URL}?page={page}"
        try:
            res = session.get(url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                print(f"[-] Page {page} returned status {res.status_code}. Stopping.")
                break

            soup = BeautifulSoup(res.content, "html.parser")
            cards = soup.select(".medicament-card")

            if not cards:
                print(f"[-] No cards found on page {page}. Reached the end.")
                break

            for card in cards:
                item = parse_card_and_modal(card, soup)
                all_data.append(item)

            print(f"[+] Page {page:03d}: Extracted {len(cards)} cards (Total: {len(all_data)})")
            time.sleep(0.4)

        except Exception as e:
            print(f"[!] Error on page {page}: {e}")
            time.sleep(2)
            continue

    if all_data:
        df = pd.DataFrame(all_data).drop_duplicates(subset=["id", "specialite"])
        
        # Save to SQLite
        conn = sqlite3.connect(db_name)
        df.to_sql("medications", conn, if_exists="replace", index=False)
        conn.close()
        
        # Save to CSV
        df.to_csv("moroccan_medications.csv", index=False, encoding="utf-8-sig")
        print(f"\n[DONE] Successfully saved {len(df)} records to '{db_name}' and 'moroccan_medications.csv'.")
    else:
        print("[-] No records extracted.")

if __name__ == "__main__":
    # Test with 3 pages first, then increase max_pages to crawl the full catalog
    run_scraper(start_page=1, max_pages=826)