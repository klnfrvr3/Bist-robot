# -*- coding: utf-8 -*-
"""Gerçek Yahoo yanıt örneğiyle ayrıştırma, temizleme, kapanmış bar ve 2s/4s kova testleri."""
import json, os, sys
from datetime import datetime
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
from robot import veri as V

ornek = json.load(open(os.path.join(os.path.dirname(__file__), "ornek_yahoo_thyao_1h.json")))
V._http_json = lambda url, zaman_asimi=25: ornek
rows, bol = V.yahoo_cek("THYAO", "1h", "2d")
assert len(rows) == 19, len(rows)
t = V.temizle(rows)
assert len(t) == 18, "18:00 anlık görüntü barı atılmalı: %d" % len(t)
f = lambda x: datetime.fromtimestamp(x, V.TZ).strftime("%d %H:%M")
print("ilk", f(t[0][0]), "son", f(t[-1][0]))

def tz(gun, sa, dk):
    return datetime(2026, 11, gun, sa, dk, tzinfo=V.TZ).timestamp()

# Seans içinde (24 Kasım 12:50): 12:30 barı oluşmakta -> kesilmeli
kesik = [r for r in t if r[0] <= tz(24, 12, 30)]
k = V.kapali_barlar(kesik, tz(24, 12, 50))
assert f(k[-1][0]) == "24 11:30", f(k[-1][0])
s1 = V.Seri.satirlardan("1h", k)
s2 = V.ust_zaman_dilimi(s1, 120, tz(24, 12, 50))
s4 = V.ust_zaman_dilimi(s1, 240, tz(24, 12, 50))
print("2s kovalar:", [(f(a), f(b)) for a, b in zip(s2.ts, s2.te)])
print("4s kovalar:", [(f(a), f(b)) for a, b in zip(s4.ts, s4.te)])
assert f(s2.te[-1]) == "24 11:30"          # 09:30+10:30 kovası tamam, 11:30 kovası eksik -> yok
assert f(s4.te[-1]) == "23 18:10"          # bugünün 4s kovası henüz bitmedi
# Seans sonrası: hepsi tamam
s1b = V.Seri.satirlardan("1h", V.kapali_barlar(t, tz(24, 21, 0)))
s2b = V.ust_zaman_dilimi(s1b, 120, tz(24, 21, 0))
s4b = V.ust_zaman_dilimi(s1b, 240, tz(24, 21, 0))
assert len(s2b) == 8 and len(s4b) == 4, (len(s2b), len(s4b))
assert f(s1b.te[-1]) == "24 18:10"
assert abs(s4b.c[-1] - 320.25) < 1e-9 and abs(s4b.o[2] - 321.5) < 1e-9
print("4s barları (açılış, yüksek, düşük, kapanış):", list(zip(s4b.o, s4b.h, s4b.l, s4b.c)))
print("TAMAM: veri testleri geçti")
