# -*- coding: utf-8 -*-
"""Canlı modu gün içinde adım adım (15 dk gecikmeli veriyle) çalıştırıp tek seferlik çalıştırmayla karşılaştırır."""
import json, os, sys, time
from datetime import date, datetime, timedelta
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sentetik
from robot import ayarlar as A
from robot.konsey import Konsey
from robot.veri import VeriYoneticisi, temizle, TZ

SEM = ["AAA", "BBB", "CCC", "DDD", "EEE"]
ayar = A.dogrula({}); ayar["hisseler"] = SEM
ham = {}
for i, s in enumerate(SEM + ["XU100"]):
    r15, r1 = sentetik.uret(s, date(2024, 6, 3), date(2026, 11, 24), tohum=40 + i, endeks=(s == "XU100"), fiyat0=60 + 9 * i, drift_olcek=0.3)
    ham[s] = {"15m": temizle(r15), "1h": temizle(r1), "bol": []}

def vy_an(simdi, gecikme=900):
    vy = VeriYoneticisi("/tmp/bist_canli_test", log=lambda *a: None)
    for s, d in ham.items():
        vy.ham[s] = {"15m": [r for r in d["15m"] if r[0] <= simdi - gecikme],
                     "1h": [r for r in d["1h"] if r[0] <= simdi - gecikme], "bol": []}
    return vy

bas = datetime(2026, 11, 16, 9, 0, tzinfo=TZ).timestamp()
son = datetime(2026, 11, 24, 21, 0, tzinfo=TZ).timestamp()

def seriler_al(vy, simdi):
    return {s: vy.seriler(s, simdi) for s in SEM}, vy.seriler("XU100", simdi)

# A: tek sefer
vy = vy_an(son, 0); sr, en = seriler_al(vy, son)
kA = Konsey(ayar); kA.hazirla(sr, en); kA.son_T = bas; kA.calistir()

# B: her 10 dakikada bir (seans içi) canlı adım, kalıcılık turu dahil
kB = Konsey(ayar); kB.son_T = bas; kB.baslangic_T = bas
t = bas; adim = 0; ihlal = 0
while t <= son:
    d = datetime.fromtimestamp(t, TZ)
    if d.weekday() < 5 and (9 * 60 + 40) <= d.hour * 60 + d.minute <= (18 * 60 + 40) or d.hour == 20:
        vy = vy_an(t); sr, en = seriler_al(vy, t)
        kB = Konsey.from_dict(json.loads(json.dumps(kB.to_dict())), ayar)
        kB.hazirla(sr, en)
        onceki = len(kB.portfoyler["konsey"].islemler)
        kB.calistir(T_son=kB.ortak_son_T())
        for x in kB.portfoyler["konsey"].islemler[onceki:]:
            if x["T"] > t - 900 + 1:   # veri gecikmesi nedeniyle işlem zamanı 'şimdi - 15 dk'dan sonra olamaz
                ihlal += 1
        adim += 1
    t += 600
fA = kA.portfoyler["konsey"].ozkaynak(); fB = kB.portfoyler["konsey"].ozkaynak()
print("tek sefer özk %.2f | canlı adım adım özk %.2f | adım %d | işlem A %d B %d | zaman ihlali %d" % (
    fA, fB, adim, len(kA.portfoyler["konsey"].islemler), len(kB.portfoyler["konsey"].islemler), ihlal))
esit = abs(fA - fB) < 1e-6 and len(kA.portfoyler["konsey"].islemler) == len(kB.portfoyler["konsey"].islemler)
print("EŞİT" if esit else "FARKLI")
sys.exit(0 if esit and ihlal == 0 else 1)
