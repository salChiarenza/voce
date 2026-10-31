"""Il punto verde di "LeaderAI." e' quello del logo ufficiale (Sal, 24/09/2026).

Sal: «Il puntino è troppo grande in questo caso. [...] Bianco. Con il puntino
verde. Questo dovrebbe essere uno standard.» Nel logo ufficiale il punto e' 35 px
su una L alta 145: circa 0,24 dell'altezza delle maiuscole. Voce lo aveva a 0,34.
Mac e Windows restano gemelli.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_punto_del_mac_come_nel_logo():
    s = (ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    m = re.search(r"LATO_PUNTO = round\(FONT_MARCHIO\.capHeight\(\) \* ([0-9.]+), 1\)", s)
    assert m and 0.22 <= float(m.group(1)) <= 0.26


def test_punto_di_windows_gemello_del_mac():
    s = (ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    m = re.search(r"lato, spazio = cap \* ([0-9.]+), cap \* 0\.12", s)
    assert m and 0.22 <= float(m.group(1)) <= 0.26
