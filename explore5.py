"""Gezielte Suche nach dem Hausaufgaben-Endpunkt in den JS-Bundles der Oberflaeche."""
import os, re, requests
from dotenv import load_dotenv
load_dotenv()
S, SC = os.environ["UNTIS_SERVER"], os.environ["UNTIS_SCHOOL"]
B = f"https://{S}"
sess = requests.Session()
sess.headers["User-Agent"] = "Mozilla/5.0 untis-gcal-sync/explore"
sess.post(f"{B}/WebUntis/j_spring_security_check",
          data={"school": SC, "j_username": os.environ["UNTIS_USER"],
                "j_password": os.environ["UNTIS_PASSWORD"], "token": ""},
          timeout=30, allow_redirects=False)
jwt = sess.get(f"{B}/WebUntis/api/token/new", timeout=30).text.strip()
sess.headers["Authorization"] = f"Bearer {jwt}"

r = sess.get(f"{B}/WebUntis/index.do", timeout=30)
skripte = re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', r.text)
print("Skripte auf index.do:")
for g in skripte:
    print("  ", g)

besucht, warteschlange = set(), [g if g.startswith("http") else B + ("" if g.startswith("/") else "/") + g for g in skripte]
alle_pfade, hausaufgaben = set(), set()
runde = 0
while warteschlange and runde < 3:
    runde += 1
    naechste = []
    for url in warteschlange:
        if url in besucht:
            continue
        besucht.add(url)
        try:
            rr = sess.get(url, timeout=60)
        except Exception as e:
            print(f"  FEHLER {url}: {type(e).__name__}")
            continue
        if rr.status_code != 200:
            print(f"  HTTP {rr.status_code} {url}")
            continue
        txt = rr.text
        print(f"  OK {len(txt):>9} Zeichen  {url.split('/')[-1][:60]}")
        for t in re.findall(r'["\'`](/?(?:WebUntis/)?api/[A-Za-z0-9_\-/{}.$]{3,})', txt):
            alle_pfade.add(t)
            if "homework" in t.lower():
                hausaufgaben.add(t)
        # Chunk-Dateinamen einsammeln (Webpack-Style)
        if runde == 1:
            for chunk in set(re.findall(r'["\']([a-zA-Z0-9_\-./]+\.[a-f0-9]{8,}\.js)["\']', txt)):
                naechste.append(B + "/WebUntis/static/" + chunk.lstrip("./"))
        # Direkttreffer auf das Wort homework
        for m in re.finditer(r'homework', txt, re.I):
            umfeld = txt[max(0, m.start()-120):m.start()+120]
            if "/" in umfeld:
                hausaufgaben.add("KONTEXT: ..." + umfeld.replace("\n", " ") + "...")
    warteschlange = naechste

print(f"\n{len(alle_pfade)} API-Pfade gefunden.")
print("\n--- Hausaufgaben-Treffer ---")
for h in sorted(hausaufgaben)[:25]:
    print("  ", h[:400])
if not hausaufgaben:
    print("   (keine)")
print("\n--- Alle api/-Pfade ---")
for p in sorted(alle_pfade)[:80]:
    print("  ", p)
