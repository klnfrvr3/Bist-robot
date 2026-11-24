# -*- coding: utf-8 -*-
"""Uçtan uca test: sentetik veriyle simülasyon + tutarlılık kontrolleri."""
import os
import sys
import time
from datetime import date, datetime

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot import ayarlar as A  # noqa: E402
from robot.konsey import Konsey  # noqa: E402
from robot.rapor import panel_verisi, tablolar  # noqa: E402
from robot.veri import VeriYoneticisi, temizle, TZ  # noqa: E402
import sentetik  # noqa: E402

SEMBOLLER = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]


def veri_hazirla(simdi_tarih, drift=1.0):
    vy = VeriYoneticisi("/tmp/bist_test_cache", log=lambda *a: None)
    for i, s in enumerate(SEMBOLLER + ["XU100"]):
        r15, r1 = sentetik.uret(s, date(2023, 12, 25), simdi_tarih, tohum=i + 7, endeks=(s == "XU100"),
                                fiyat0=50 + 20 * i, drift_olcek=drift)
        vy.ham_ata(s, r15, r1, kaynak="sentetik")
    return vy


def kontrol(k, ayar):
    hatalar = []
    for ad, p in k.portfoyler.items():
        if p.nakit < -1e-6:
            hatalar.append("%s nakit negatif: %s" % (ad, p.nakit))
        t = tablolar(p)
        top_gun = sum(g["kz"] for g in t["gunler"])
        toplam = p.ozkaynak() - p.sermaye
        if abs(top_gun - toplam) > 1.0:
            hatalar.append("%s günlük toplam %.2f != toplam %.2f" % (ad, top_gun, toplam))
        top_ay = sum(g["kz"] for g in t["aylar"])
        if abs(top_ay - toplam) > 1.0:
            hatalar.append("%s aylık toplam %.2f != toplam %.2f" % (ad, top_ay, toplam))
        top_yil = sum(g["kz"] for g in t["yillar"])
        if abs(top_yil - toplam) > 1.0:
            hatalar.append("%s yıllık toplam uyuşmuyor" % ad)
        # nakit muhasebesi: sermaye - alış maliyetleri + satış gelirleri
        nakit = p.sermaye
        for x in p.islemler:
            if x["yon"] == "AL":
                nakit -= x["tutar"] + x["komisyon"]
            else:
                nakit += x["tutar"] - x["komisyon"]
        if abs(nakit - p.nakit) > 0.5 + 0.01 * len(p.islemler):
            hatalar.append("%s nakit muhasebesi %.2f != %.2f" % (ad, nakit, p.nakit))
        if len(p.poz) > ayar["max_acik_pozisyon"]:
            hatalar.append("%s pozisyon sınırı aşıldı" % ad)
        # komisyon oranı kontrolü
        oran = ayar["komisyon_binde"] / 1000 * (1.05 if ayar["bsmv_dahil"] else 1)
        for x in p.islemler[:50]:
            if abs(x["komisyon"] - x["tutar"] * oran) > 0.02:
                hatalar.append("%s komisyon hatalı %s" % (ad, x))
                break
    return hatalar


def main():
    ayar = A.dogrula({})
    ayar["hisseler"] = SEMBOLLER
    ayar["evren"] = "liste"
    ayar["simulasyon_gun"] = 365
    simdi_tarih = date(2026, 11, 24)
    simdi = datetime(2026, 11, 24, 21, 0, tzinfo=TZ).timestamp()
    drift = float(os.environ.get('DRIFT', '1'))
    vy = veri_hazirla(simdi_tarih, drift)
    seriler = {s: vy.seriler(s, simdi) for s in SEMBOLLER}
    endeks = vy.seriler("XU100", simdi)
    for tf in ("15m", "1h", "2h", "4h"):
        s = seriler["AAA"][tf]
        print(tf, len(s), "ilk", datetime.fromtimestamp(s.ts[0], TZ), "son te", datetime.fromtimestamp(s.te[-1], TZ))
    t0 = time.time()
    k = Konsey(ayar)
    k.hazirla(seriler, endeks)
    k.son_T = simdi - ayar["simulasyon_gun"] * 86400
    adim = k.calistir()
    print("adım:", adim, "süre: %.1f sn" % (time.time() - t0))
    for ad, p in k.portfoyler.items():
        sat = [x for x in p.islemler if x["yon"] == "SAT"]
        print("%-11s özk=%12.2f işlem=%4d kapanan=%4d açık=%d" % (ad, p.ozkaynak(), len(p.islemler), len(sat), len(p.poz)))
    print("ağırlık:", {m: round(w, 3) for m, w in k.agirlik.items()})
    h = kontrol(k, ayar)
    print("HATALAR:", h if h else "yok")
    pv = panel_verisi(k, ayar, "simulasyon")
    import json
    js = json.dumps(pv, ensure_ascii=False)
    print("panel json boyutu: %.0f KB" % (len(js) / 1024))
    print("özet:", {kk: pv["ozet"][kk] for kk in ("ozkaynak", "toplam_yuzde", "bugun_kz", "hafta_kz", "ay_kz", "yil_kz", "isabet", "max_dusus", "sharpe")})
    print("son hafta:", pv["haftalar"][-1]["etiket"], pv["haftalar"][-1]["kz"])
    print("aylar:", [(a["etiket"], a["kz"]) for a in pv["aylar"][-3:]])
    sebepler = {}
    for x in k.portfoyler["konsey"].islemler:
        if x["yon"] == "SAT":
            sebepler[x["sebep"].split(" (")[0]] = sebepler.get(x["sebep"].split(" (")[0], 0) + 1
    print("satış sebepleri:", sebepler)

    # kalıcılık: to_dict -> from_dict -> devam
    import copy
    d = json.loads(json.dumps(k.to_dict()))
    k2 = Konsey.from_dict(d, ayar)
    k2.hazirla(seriler, endeks)
    print("geri yükleme sonrası adım:", k2.calistir(), "özk eşit:", abs(k2.portfoyler["konsey"].ozkaynak() - k.portfoyler["konsey"].ozkaynak()) < 1e-6)

    # artımlı çalıştırma = tek seferde çalıştırma olmalı
    k3 = Konsey(ayar)
    k3.hazirla(seriler, endeks)
    k3.son_T = simdi - ayar["simulasyon_gun"] * 86400
    son = k3.son_veri_T()
    ara = son - 20 * 86400
    k3.calistir(T_son=ara)
    d3 = json.loads(json.dumps(k3.to_dict()))
    k4 = Konsey.from_dict(d3, ayar)
    k4.hazirla(seriler, endeks)
    k4.calistir()
    fark = abs(k4.portfoyler["konsey"].ozkaynak() - k.portfoyler["konsey"].ozkaynak())
    print("artımlı = tek sefer:", fark < 1e-6, "fark", fark)
    return 0 if not h and fark < 1e-6 else 1


if __name__ == "__main__":
    sys.exit(main())
