"""Haalt Nederlandse en internationale financiële nieuwsfeeds en koersen op
en schrijft alles naar nieuws.json. Gebruikt alleen standaard-Python."""
import json, re, html, time, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (financieel-nieuws-dashboard; GitHub Actions)"}

BRONNEN = {
    "nos": "https://feeds.nos.nl/nosnieuwseconomie",
    "nu": "https://www.nu.nl/rss/Economie",
    "tel": "https://www.telegraaf.nl/financieel/rss",
    "mw": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "mwm": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "wsj": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
}
KOERSEN = {"AEX": "^AEX", "DAX": "^GDAXI", "S&P 500": "^GSPC", "Nasdaq": "^IXIC",
           "Goud ($/oz)": "GC=F", "Brent-olie ($)": "BZ=F", "EUR/USD": "EURUSD=X"}


def haal(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def schoon(tekst):
    tekst = html.unescape(re.sub(r"<[^>]+>", " ", tekst or ""))
    return re.sub(r"\s+", " ", tekst).strip()


def iso(datum):
    if not datum:
        return ""
    try:
        return parsedate_to_datetime(datum).astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(datum.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except Exception:
            return datum


def lees_feed(xml_bytes, google=False, maximum=30):
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    uit = []
    for it in items[:maximum]:
        def g(naam):
            el = it.find(naam)
            if el is None:
                el = it.find("{http://www.w3.org/2005/Atom}" + naam)
            return (el.text or "") if el is not None else ""
        link = g("link")
        if not link:
            el = it.find("{http://www.w3.org/2005/Atom}link")
            link = el.get("href", "") if el is not None else ""
        titel, bron = schoon(g("title")), ""
        if google:
            m = re.match(r"^(.*) - ([^-]+)$", titel)
            if m:
                titel, bron = m.group(1).strip(), m.group(2).strip()
        uit.append({"titel": titel, "desc": schoon(g("description") or g("summary"))[:240],
                    "link": link.strip(), "datum": iso(g("pubDate") or g("published") or g("updated")),
                    "bronNaam": bron})
    return uit


def zoektermen():
    try:
        with open("zoektermen.txt", encoding="utf-8") as f:
            return [r.strip() for r in f if r.strip() and not r.startswith("#")]
    except FileNotFoundError:
        return ["AEX beurs"]


def koers(sym):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) + "?range=1d&interval=1d"
    meta = json.loads(haal(url))["chart"]["result"][0]["meta"]
    prijs = meta["regularMarketPrice"]
    vorig = meta.get("chartPreviousClose") or meta.get("previousClose")
    return {"prijs": prijs, "ch": (prijs / vorig - 1) * 100 if vorig else None}


def main():
    nu = datetime.now(timezone.utc).isoformat()
    data = {"bijgewerkt": nu, "bronnen": {}, "markten": {}, "zoektermen": zoektermen()}
    for bid, url in BRONNEN.items():
        try:
            data["bronnen"][bid] = {"items": lees_feed(haal(url)), "ok": True}
        except Exception as e:
            data["bronnen"][bid] = {"items": [], "ok": False, "fout": str(e)[:120]}
        time.sleep(0.5)
    google = []
    for term in data["zoektermen"]:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(term + " when:2d")
               + "&hl=nl&gl=NL&ceid=NL:nl")
        try:
            google += [dict(i, zoekterm=term) for i in lees_feed(haal(url), google=True, maximum=10)]
        except Exception:
            pass
        time.sleep(0.5)
    data["bronnen"]["gnews"] = {"items": google, "ok": bool(google)}
    for naam, sym in KOERSEN.items():
        try:
            data["markten"][naam] = koers(sym)
        except Exception:
            data["markten"][naam] = None
    # Als niets gelukt is, het oude bestand laten staan
    if not any(b["items"] for b in data["bronnen"].values()):
        print("Geen enkele bron gelukt; nieuws.json niet overschreven")
        return
    with open("nieuws.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Klaar:", {k: len(v["items"]) for k, v in data["bronnen"].items()})


if __name__ == "__main__":
    main()
