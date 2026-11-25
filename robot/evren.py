# -*- coding: utf-8 -*-
"""Hisse evreni: Borsa İstanbul'daki tüm paylar (Yakın İzleme Pazarı hariç), likiditeye göre süzülmüş.

1. KAP'tan Yıldız, Ana ve Alt Pazar listeleri alınır (Yakın İzleme Pazarı çıkarılır).
2. TradingView tarama servisinden son 30 günlük ortalama işlem hacmi (TL) alınır.
3. Asgari hacmi geçenler arasından en likit N hisse seçilir. Liste günde bir yenilenir.
Sığ (az işlem gören) hisselerde 15 dakikalık barlar boşluklu olur ve sanal dolumlar
gerçekçi olmaz; bu yüzden likidite süzgeci vardır.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

from . import evren_yedek
from .veri import UA, _ssl_baglam, tarih_str

KAP_URL = "https://kap.org.tr/tr/Pazarlar"
TV_URL = "https://scanner.tradingview.com/turkey/scan"
IZINLI_PAZARLAR = ("YILDIZ PAZAR", "ANA PAZAR", "ALT PAZAR")
YIP = "YAKIN İZLEME PAZARI"


def _get(url, veri=None, zaman_asimi=40):
    hd = {"User-Agent": UA}
    if veri is not None:
        hd["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=veri, headers=hd)
    with urllib.request.urlopen(req, timeout=zaman_asimi, context=_ssl_baglam()) as r:
        return r.read().decode("utf-8", errors="ignore")


def kap_pazarlar():
    """{pazar adı: set(kod)}"""
    h = _get(KAP_URL).replace('\\"', '"')
    out = {}
    for parca in re.split(r'"marketName":"', h)[1:]:
        ad = parca[:parca.index('"')]
        if ad in out:
            continue
        kodlar = set()
        for s in re.findall(r'"stockCode":"([^"]*)"', parca):
            kodlar.update(x.strip().upper() for x in s.split(",") if x.strip())
        out[ad] = kodlar
    if not out.get("YILDIZ PAZAR") or not out.get("ANA PAZAR"):
        raise ValueError("KAP sayfası beklenen biçimde değil")
    return out


def tv_hacim():
    """{kod: (ortalama günlük TL hacim, son fiyat)}"""
    istek = {"columns": ["name", "average_volume_30d_calc", "close"],
             "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
             "range": [0, 2000]}
    d = json.loads(_get(TV_URL, json.dumps(istek).encode("utf-8")))
    out = {}
    for r in d.get("data", []):
        try:
            kod, hacim, fiyat = r["d"][0], r["d"][1], r["d"][2]
            if kod and hacim and fiyat:
                out[str(kod).upper()] = (float(hacim) * float(fiyat), float(fiyat))
        except (KeyError, IndexError, TypeError, ValueError):
            pass
    if len(out) < 100:
        raise ValueError("TradingView taraması eksik döndü")
    return out


def yahoo_hacim(kodlar, log=print):
    """Yedek: Yahoo günlük barlarından 20 günlük ortalama TL hacim."""
    from concurrent.futures import ThreadPoolExecutor
    from .veri import yahoo_cek, temizle
    out = {}

    def is_(k):
        try:
            rows = temizle(yahoo_cek(k, "1d", "1mo")[0])
            son = rows[-20:]
            if son:
                out[k] = (sum(r[4] * r[5] for r in son) / len(son), son[-1][4])
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(is_, kodlar))
    return out


def evren_olustur(klasor, max_hisse=100, min_hacim_tl=20e6, log=print, zorla=False):
    yol = os.path.join(klasor, "evren.json")
    bugun = tarih_str(time.time())
    try:
        with open(yol, "r", encoding="utf-8") as f:
            onceki = json.load(f)
        if not zorla and onceki.get("tarih") == bugun and onceki.get("max_hisse") == max_hisse \
                and onceki.get("min_hacim_tl") == min_hacim_tl and onceki.get("hisseler"):
            return onceki
    except Exception:
        onceki = None

    kaynak = []
    try:
        pz = kap_pazarlar()
        izinli = set().union(*(pz.get(p, set()) for p in IZINLI_PAZARLAR))
        yip = pz.get(YIP, set())
        kaynak.append("KAP")
    except Exception as e:
        log("UYARI KAP pazar listesi alınamadı (%s); %s tarihli yedek liste kullanılıyor." % (e, evren_yedek.TARIH))
        izinli, yip = set(evren_yedek.IZINLI), set(evren_yedek.YAKIN_IZLEME)
        kaynak.append("yedek liste " + evren_yedek.TARIH)
    izinli -= yip

    try:
        hacim = tv_hacim()
        kaynak.append("TradingView hacim")
    except Exception as e:
        log("UYARI TradingView hacim taraması başarısız (%s); Yahoo günlük verisi kullanılıyor." % e)
        hacim = yahoo_hacim(sorted(izinli), log)
        kaynak.append("Yahoo hacim")

    adaylar = sorted(((hacim[k][0], k) for k in izinli if k in hacim and hacim[k][0] >= min_hacim_tl),
                     reverse=True)
    secilen = [k for _, k in adaylar[:int(max_hisse)]]
    if not secilen and onceki and onceki.get("hisseler"):
        log("UYARI hisse evreni oluşturulamadı; önceki liste kullanılıyor.")
        return onceki
    d = {"tarih": bugun, "kaynak": " + ".join(kaynak), "max_hisse": max_hisse, "min_hacim_tl": min_hacim_tl,
         "izinli_sayi": len(izinli), "yip_sayi": len(yip), "yip": sorted(yip), "izinli": sorted(izinli), "uygun_sayi": len(adaylar),
         "hisseler": secilen,
         "hacim": {k: round(hacim[k][0]) for k in secilen}}
    tmp = yol + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, yol)
    log("Hisse evreni: %d pazarda %d pay (YİP'teki %d pay hariç); günlük hacmi %.0f milyon TL üstünde %d pay; "
        "en likit %d tanesi seçildi (%s)." % (len(izinli) + len(yip), len(izinli), len(yip), min_hacim_tl / 1e6,
                                              len(adaylar), len(secilen), d["kaynak"]))
    return d
