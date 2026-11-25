# -*- coding: utf-8 -*-
"""Gerçek BIST verisiyle çok yıllı karşılaştırmalı simülasyon (GitHub Actions'ta çalışır).

Her ayar seti aynı veriyle çalıştırılır; sonuçlar takvim yılına göre ayrı raporlanır ki
bir yılda iyi görünen ayarın diğer yıllarda da işe yarayıp yaramadığı görülsün (aşırı uyum kontrolü).
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

from robot import ayarlar as A  # noqa: E402
from robot.evren import evren_olustur  # noqa: E402
from robot.konsey import Konsey  # noqa: E402
from robot.motorlar import MOTORLAR  # noqa: E402
from robot.rapor import istatistik  # noqa: E402
from robot.veri import VeriYoneticisi  # noqa: E402

CIKTI = os.path.join(KOK, "analiz_sonuc")
GUN = int(os.environ.get("ANALIZ_GUN", "1000"))
N = int(os.environ.get("ANALIZ_HISSE", "120"))
TUM = os.environ.get("ANALIZ_EVREN", "tum") == "tum"   # tüm YİP dışı hisseler + o günkü likiditeye göre seçim

SETLER = {
    "varsayilan": {},
    "goreli_guc": {"goreli_guc_filtresi": True},
    "endeks_filtresiz": {"endeks_filtresi": False},
    "giris_040": {"giris_esigi": 0.40},
    "giris_020": {"giris_esigi": 0.20},
    "atr_2s": {"atr_zaman_dilimi": "2h"},
    "genis_stop": {"stop_atr_kat": 2.5, "iz_suren_atr_kat": 3.5},
    "8_pozisyon": {"max_acik_pozisyon": 8, "max_pozisyon_yuzde": 12.5},
    "adaptifsiz": {"adaptif_agirlik": False},
    "kaymasiz": {"likidite_kaymasi": False},
}

SERILER = None
ENDEKS = None
BAS = None


def _yillik(p, bas_sermaye):
    """Takvim yılı başına getiri ve maks. düşüş."""
    yil = {}
    for k in sorted(p.gunler):
        g = p.gunler[k]
        y = k[:4]
        if y not in yil:
            yil[y] = {"bas": g["bas"], "son": g["son"], "zirve": g["bas"], "mdd": 0.0, "islem": 0, "komisyon": 0.0}
        r = yil[y]
        r["son"] = g["son"]
        r["zirve"] = max(r["zirve"], g["son"])
        r["mdd"] = min(r["mdd"], g["son"] / r["zirve"] - 1)
        r["islem"] += g["islem"]
        r["komisyon"] += g["komisyon"]
    return {y: {"getiri": round((r["son"] / r["bas"] - 1) * 100, 2), "mdd": round(r["mdd"] * 100, 2),
                "islem": r["islem"], "komisyon": round(r["komisyon"])} for y, r in yil.items()}


def _endeks_yillik(k):
    yil = {}
    for T, v in k.endeks_noktalar:
        y = time.strftime("%Y", time.gmtime(T + 10800))
        yil.setdefault(y, [v, v])
        yil[y][1] = v
    return {y: round((b / a - 1) * 100, 2) for y, (a, b) in yil.items()}


def calistir(ad):
    ayar = A.dogrula(dict(SETLER[ad], evren="liste", dinamik_evren=N if TUM else 0))
    t0 = time.time()
    k = Konsey(ayar)
    k.hazirla(SERILER, ENDEKS, bas_T=BAS)
    k.son_T = max(BAS, k.ilk_T() + 45 * 86400)
    k.calistir()
    out = {"ad": ad, "fark": SETLER[ad], "sure": round(time.time() - t0)}
    for pad, p in k.portfoyler.items():
        if ad != "varsayilan" and pad != "konsey":
            continue
        st = istatistik(p)
        out[pad] = {"ist": {x: st[x] for x in ("toplam_yuzde", "yillik_getiri", "max_dusus", "sharpe", "isabet",
                                                "kar_faktoru", "islem", "komisyon", "gun_sayisi")},
                    "yillik": _yillik(p, p.sermaye)}
    out["endeks"] = _endeks_yillik(k)
    if k.endeks_noktalar:
        out["endeks_toplam"] = round((k.endeks_noktalar[-1][1] / k.portfoyler["konsey"].sermaye - 1) * 100, 2)
    return out


def main():
    global SERILER, ENDEKS, BAS
    os.makedirs(CIKTI, exist_ok=True)
    klasor = "/tmp/analiz_veri"
    os.makedirs(klasor, exist_ok=True)
    ev = evren_olustur(klasor, N if not TUM else 2000, 10e6 if not TUM else 0, log=print)
    syms = ev["hisseler"]  # TUM: hacmi olan tüm YİP dışı hisseler; seçim her gün geçmiş hacme göre yapılır
    vy = VeriYoneticisi(os.path.join(klasor, "onbellek"), "yahoo", log=print)
    t0 = time.time()
    bas = vy.guncelle(syms + ["XU100"], tam=True)
    print("veri: %d hisse, %d başarısız, %.0f sn" % (len(syms), len(bas), time.time() - t0))
    simdi = time.time()
    SERILER = {s: vy.seriler(s, simdi) for s in syms if s in vy.ham}
    ENDEKS = vy.seriler("XU100", simdi)
    BAS = simdi - GUN * 86400
    with ProcessPoolExecutor(max_workers=int(os.environ.get("ANALIZ_ISCI", "2"))) as ex:
        sonuclar = list(ex.map(calistir, list(SETLER)))
    rapor = {"tarih": time.strftime("%Y-%m-%d %H:%M"), "hisse": len(SERILER), "gun": GUN, "dinamik_evren": N if TUM else 0,
             "evren": {k: ev.get(k) for k in ("izinli_sayi", "yip_sayi", "uygun_sayi", "kaynak")},
             "basarisiz": bas, "sonuclar": sonuclar}
    with open(os.path.join(CIKTI, "analiz.json"), "w", encoding="utf-8") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1)
    # okunur özet
    sat = ["# Gerçek veriyle karşılaştırmalı simülasyon", "",
           "%s · %d hisse · %d gün · %s" % (rapor["tarih"], rapor["hisse"], GUN,
           "her gün o günkü en likit %d hisse (geleceği bilmeden)" % N if TUM else "bugünkü en likit liste (seçim yanlılığı var)"), ""]
    yillar = sorted({y for r in sonuclar for y in r["konsey"]["yillik"]})
    sat.append("| Ayar | Toplam % | " + " | ".join(yillar) + " | MaksDüş % | Sharpe | İşlem | Komisyon |")
    sat.append("|---|---|" + "---|" * len(yillar) + "---|---|---|---|")
    e = sonuclar[0]["endeks"]
    sat.append("| BIST100 al-tut | %s | " % sonuclar[0].get("endeks_toplam") + " | ".join(str(e.get(y, "")) for y in yillar) + " | | | | |")
    for r in sonuclar:
        c = r["konsey"]
        sat.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["ad"], c["ist"]["toplam_yuzde"], " | ".join(str(c["yillik"].get(y, {}).get("getiri", "")) for y in yillar),
            c["ist"]["max_dusus"], c["ist"]["sharpe"], c["ist"]["islem"], c["ist"]["komisyon"]))
    sat += ["", "## Motorlar (varsayılan ayarla, gölge portföyler)", "",
            "| Motor | Toplam % | " + " | ".join(yillar) + " | MaksDüş % | İsabet % | Kâr faktörü | İşlem |",
            "|---|---|" + "---|" * len(yillar) + "---|---|---|---|"]
    v = sonuclar[0]
    for m in ["konsey"] + MOTORLAR:
        c = v[m]
        sat.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            m, c["ist"]["toplam_yuzde"], " | ".join(str(c["yillik"].get(y, {}).get("getiri", "")) for y in yillar),
            c["ist"]["max_dusus"], c["ist"]["isabet"], c["ist"]["kar_faktoru"], c["ist"]["islem"]))
    with open(os.path.join(CIKTI, "ozet.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(sat) + "\n")
    print("\n".join(sat))


if __name__ == "__main__":
    main()
