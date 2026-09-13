"""Chunk 'basic/studenthomeworks' laden und den darin verwendeten API-Pfad auslesen."""
import re, requests, os
from dotenv import load_dotenv
load_dotenv()

cdn = requests.Session()
cdn.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/140.0",
                    "Referer": f"https://{os.environ['UNTIS_SERVER']}/"})
BASE = "https://content.webuntis.com/WebUntis/static/2027.0.2"

wp = cdn.get(f"{BASE}/js/untis/webpack.js", timeout=60).text
print(f"webpack.js: {len(wp)} Zeichen")

# Webpack baut Chunk-URLs ueber eine Hash-Tabelle. Diese suchen.
kandidaten = re.findall(r'\.u\s*=\s*([^;]{0,4000})', wp)
for k in kandidaten[:3]:
    print("\n--- URL-Bauer ---")
    print(k[:600])

# Hash-Tabelle: {5736:"abc123",...}
hashes = {}
for m in re.finditer(r'\{((?:\s*\d+\s*:\s*"[a-f0-9]{6,}"\s*,?){20,})\}', wp):
    for cid, h in re.findall(r'(\d+)\s*:\s*"([a-f0-9]{6,})"', m.group(1)):
        hashes[cid] = h
print(f"\n{len(hashes)} Chunk-Hashes gefunden. 5736 -> {hashes.get('5736')}")

zielhash = hashes.get("5736")
versuche = []
if zielhash:
    versuche = [f"{BASE}/js/webuntis/5736.{zielhash}.js",
                f"{BASE}/js/untis/5736.{zielhash}.js",
                f"{BASE}/js/5736.{zielhash}.js"]

for u in versuche:
    r = cdn.get(u, timeout=60)
    print(f"\n{r.status_code}  {u}")
    if r.status_code != 200:
        continue
    txt = r.text
    print(f"  {len(txt)} Zeichen")
    pfade = set(re.findall(r'["\'`](/?(?:WebUntis/)?api/[A-Za-z0-9_\-/{}.$?=&]{3,})', txt))
    print("  API-Pfade im Chunk:")
    for p in sorted(pfade):
        print("    ", p)
    for m in re.finditer(r'homework', txt, re.I):
        print("    KONTEXT:", txt[max(0,m.start()-200):m.start()+200].replace("\n"," ")[:400])
        break
    break
