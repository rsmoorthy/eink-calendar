import sys
from datetime import date as dt_date
import requests
from bs4 import BeautifulSoup

headers = {
        "accept": "*/*",
        "accept-language": "en-IN,en-US;q=0.9,en-GB;q=0.8,en;q=0.7",
        "priority": "u=1, i",
        "referer": "https://vyasarajamatha.org/panchanga.php",
        "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    }


def fetch(date=None):
    if not date:
        date = dt_date.today().strftime("%Y-%m-%d")
    out = requests.get(
        f"https://vyasarajamatha.org/panchanga_ajax.php?selected_date={date}",
        headers=headers
    )
    if out.status_code == 200:
        soup = BeautifulSoup(out.text, "html.parser")
        # print(out.text)
        data = []
        for li in soup.find_all("li"):
            head = li.strong.get_text(strip=True) if li.strong else ""

            value = "".join(
                [str(s).strip() for s in li.find_all(string=True, recursive=False)]
            )

            data.append((head, value))

        print(data)
        return data


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    fetch(target_date)

