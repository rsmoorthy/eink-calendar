import logging
from datetime import date as dt_date
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-IN,en-US;q=0.9,en-GB;q=0.8,en;q=0.7",
    "referer": "https://vyasarajamatha.org/panchanga.php",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
}

TITHI_NORMALIZATION = {
    "PRATHAMA": "Prathama",
    "PRATHAME": "Prathama",
    "PADYAMI": "Prathama",
    "PRATIPADA": "Prathama",
    "DVITIYA": "Dvitiya",
    "DWITIYA": "Dvitiya",
    "BIDIGE": "Dvitiya",
    "TRITIYA": "Tritiya",
    "TRITEEYAA": "Tritiya",
    "TADIGE": "Tritiya",
    "CHATURTHI": "Chaturthi",
    "CHAUTHI": "Chaturthi",
    "PANCHAMI": "Panchami",
    "SHASHTHI": "Shashthi",
    "SHASTHI": "Shashthi",
    "SAPTAMI": "Saptami",
    "ASHTAMI": "Ashtami",
    "NAVAMI": "Navami",
    "DASHAMI": "Dashami",
    "EKADASHI": "Ekadashi",
    "DWADASHI": "Dwadashi",
    "DVADASHI": "Dwadashi",
    "TRAYODASHI": "Trayodashi",
    "CHATURDASHI": "Chaturdashi",
    "POORNIMA": "Purnima",
    "PURNIMA": "Purnima",
    "HUNNIME": "Purnima",
    "AMAVASYA": "Amavasya",
    "AMAVASYE": "Amavasya",
}


def normalize_tithi(raw_tithi: str, paksha: str = "") -> str:
    if not raw_tithi:
        return ""
    if "/" in raw_tithi:
        parts = [normalize_tithi(p.strip(), paksha) for p in raw_tithi.split("/") if p.strip()]
        return "/".join(parts)
    cleaned = raw_tithi.strip().upper().split()[0] if raw_tithi else ""
    # Strip trailing punctuation
    cleaned = cleaned.rstrip(":,.-")
    norm = TITHI_NORMALIZATION.get(cleaned, raw_tithi.strip().title())
    if norm in ("Purnima", "Amavasya"):
        return norm
    if "15" in raw_tithi or "POORNIMA" in raw_tithi.upper() or "PURNIMA" in raw_tithi.upper():
        return "Purnima"
    if "AMAVASYA" in raw_tithi.upper():
        return "Amavasya"
    return norm


def fetch_online_panchanga(target_date: dt_date) -> dict:
    """
    Fetches panchanga details for a given date from the online endpoint.
    Returns normalized dictionary.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://vyasarajamatha.org/panchanga_ajax.php?selected_date={date_str}"

    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200 and "list-group" in res.text:
            soup = BeautifulSoup(res.text, "html.parser")
            data = {}
            for li in soup.find_all("li"):
                head = li.strong.get_text(strip=True).rstrip(":") if li.strong else ""
                value = "".join([str(s).strip() for s in li.find_all(string=True, recursive=False)]).strip()
                if head:
                    data[head.lower()] = value

            masa = data.get("masa", "").title()
            paksha = data.get("paksha", "").title()
            # Extract Shraddha Tithi for Tithi; fallback to regular Tithi if missing or SHRADDHABHAVA
            shraddha_tithi = data.get("shraddha tithi", "").strip()
            if shraddha_tithi and shraddha_tithi.upper() != "SHRADDHABHAVA":
                raw_tithi = shraddha_tithi
            else:
                raw_tithi = data.get("tithi", "").strip()

            tithi = normalize_tithi(raw_tithi, paksha)
            nakshatra = data.get("nakshatra", "").title()

            return {
                "lunar_masa": masa,
                "lunar_paksha": paksha,
                "lunar_tithi": tithi,
                "nakshatra": nakshatra,
                "success": True,
            }
        else:
            logger.warning(f"No panchanga data returned for {date_str}")
    except Exception as e:
        logger.error(f"Failed to fetch panchanga for {date_str}: {e}")

    # Default fallback values
    return {
        "lunar_masa": "",
        "lunar_paksha": "Shukla",
        "lunar_tithi": "Prathama",
        "nakshatra": "",
        "success": False,
    }
