"""Ermittelt den technischen Schulnamen (school=) über die offene WebUntis-Schulsuche."""
import json
import os

import requests

URL = "https://mobile.webuntis.com/ms/schoolquery2"

def suche(begriff):
    body = {"id": "wu", "method": "searchSchool",
            "params": [{"search": begriff}], "jsonrpc": "2.0"}
    r = requests.post(URL, json=body, timeout=20,
                      headers={"Content-Type": "application/json"})
    print(f"Suche '{begriff}' -> HTTP {r.status_code}")
    try:
        daten = r.json()
    except Exception:
        print("  Keine JSON-Antwort:", r.text[:300])
        return
    schulen = daten.get("result", {}).get("schools", [])
    if not schulen:
        print("  Kein Treffer.", json.dumps(daten)[:300])
    for s in schulen:
        print(f"  Anzeigename : {s.get('displayName')}")
        print(f"  loginName   : {s.get('loginName')}   <-- das ist der school=-Wert")
        print(f"  Server      : {s.get('server')}")
        print(f"  Adresse     : {s.get('address')}")
        print()

# Suchbegriffe als Argumente uebergeben, z. B.:
#   python find_school.py "Name der Schule"
import sys
begriffe = sys.argv[1:] or [os.environ.get("UNTIS_SCHOOL", "")]
for begriff in [b for b in begriffe if b]:
    suche(begriff)
