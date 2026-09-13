"""JS-Bundles ohne Auth-Header vom CDN holen und nach dem Hausaufgaben-Endpunkt suchen."""
import os, re, requests
from dotenv import load_dotenv
load_dotenv()

cdn = requests.Session()   # SAUBERE Sitzung: kein Token an fremde Hosts
cdn.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Referer": f"https://{os.environ['UNTIS_SERVER']}/",
    "Accept": "*/*",
})

BASIS_CDN = "https://content.webuntis.com/WebUntis/static/2027.0.2"
start = [f"{BASIS_CDN}/js/webuntis/main.js", f"{BASIS_CDN}/js/untis/wrapper.js",
         f"{BASIS_CDN}/js/untis/webpack.js"]

besucht, alle, treffer = set(), set(), set()
warteschlange = list(start)
runde = 0
while warteschlange and runde < 4:
    runde += 1
    naechste = []
    for url in warteschlange:
        if url in besucht:
            continue
        besucht.add(url)
        try:
            r = cdn.get(url, timeout=60)
        except Exception as e:
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}  {url.split('/')[-1][:50]}")
            continue
        txt = r.text
        print(f"  OK {len(txt):>9}  {url.split('/')[-1][:50]}")
        for t in re.findall(r'["\'`](/?(?:WebUntis/)?api/[A-Za-z0-9_\-/{}.$]{3,})', txt):
            alle.add(t)
            if "homework" in t.lower():
                treffer.add(t)
        for m in re.finditer(r'homework[a-zA-Z]*', txt, re.I):
            u = txt[max(0,m.start()-150):m.start()+150].replace("\n"," ")
            if "api" in u or "/" in u:
                treffer.add("KONTEXT: " + u)
        if runde <= 2:
            for c in set(re.findall(r'["\']([a-zA-Z0-9_\-]+\.[a-f0-9]{8,}\.js)["\']', txt)):
                naechste.append(f"{BASIS_CDN}/js/webuntis/{c}")
            for c in set(re.findall(r'["\']\./([a-zA-Z0-9_\-/]+\.js)["\']', txt)):
                naechste.append(f"{BASIS_CDN}/js/webuntis/{c}")
    warteschlange = naechste

print(f"\n{len(alle)} api-Pfade, {len(treffer)} Hausaufgaben-Treffer\n")
print("--- Hausaufgaben ---")
for t in sorted(treffer)[:20]:
    print("  ", t[:350], "\n")
print("--- api-Pfade (Auswahl) ---")
for p in sorted(alle):
    if any(w in p.lower() for w in ("home","work","exam","lesson","classreg","note","text")):
        print("  ", p)
