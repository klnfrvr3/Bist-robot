# -*- coding: utf-8 -*-
"""Test için Yahoo biçiminde sentetik BIST verisi üretir (gerçek veri DEĞİLDİR)."""
import math
import random
from datetime import datetime, timedelta

from robot.veri import TZ


def is_gunleri(bas, son):
    d = bas
    while d <= son:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def uret(sembol, bas_tarih, son_tarih, tohum, endeks=False, son15_gun=60, fiyat0=100.0, drift_olcek=1.0):
    rnd = random.Random(tohum)
    gunler = list(is_gunleri(bas_tarih, son_tarih))
    fiyat = fiyat0
    rejim_drift = 0.0
    rows15 = []
    for gi, g in enumerate(gunler):
        if rnd.random() < 0.03:  # rejim değişimi
            rejim_drift = rnd.choice([-1, 0, 0, 1, 1]) * rnd.uniform(0.0002, 0.0012) * drift_olcek
        gece = rnd.gauss(0, 0.008)
        fiyat *= math.exp(gece)
        for k in range(35):  # 09:30 ... 18:00
            t = datetime(g.year, g.month, g.day, 9, 30, tzinfo=TZ) + timedelta(minutes=15 * k)
            o = fiyat
            r = rejim_drift + rnd.gauss(0, 0.004)
            c = o * math.exp(r)
            h = max(o, c) * (1 + abs(rnd.gauss(0, 0.0015)))
            l = min(o, c) * (1 - abs(rnd.gauss(0, 0.0015)))
            v = 0 if endeks else int(rnd.uniform(1e5, 1e6))
            if k == 34:  # 18:00 kapanış seansı tek fiyat
                h = l = o = c
            rows15.append((int(t.timestamp()), round(o, 2), round(h, 2), round(l, 2), round(c, 2), v))
            fiyat = c
    # 1 saatlik: 09:30-10:30, ... 17:30-18:10
    rows1 = []
    kova = {}
    for r in rows15:
        dt = datetime.fromtimestamp(r[0], TZ)
        dk = dt.hour * 60 + dt.minute
        b = (dk - 570) // 60
        b = min(b, 8)
        anahtar = (dt.date(), b)
        kova.setdefault(anahtar, []).append(r)
    for (d, b), rs in sorted(kova.items()):
        t0 = datetime(d.year, d.month, d.day, 9, 30, tzinfo=TZ) + timedelta(hours=b)
        rows1.append((int(t0.timestamp()), rs[0][1], max(x[2] for x in rs), min(x[3] for x in rs), rs[-1][4],
                      sum(x[5] for x in rs) if not endeks else 0))
    # 15 dk yalnız son N iş günü
    sinir = gunler[-son15_gun]
    sinir_t = int(datetime(sinir.year, sinir.month, sinir.day, tzinfo=TZ).timestamp())
    rows15 = [r for r in rows15 if r[0] >= sinir_t]
    # birkaç None (Yahoo'daki boş barlar gibi)
    for _ in range(5):
        i = rnd.randrange(len(rows15) - 5)
        t = rows15[i][0]
        rows15[i] = (t, None, None, None, None, None)
    # son anlık görüntü barı
    son = rows1[-1]
    rows1.append((son[0] + 1800, son[4], son[4], son[4], son[4], 0))
    return rows15, rows1
