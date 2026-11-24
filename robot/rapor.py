# -*- coding: utf-8 -*-
"""Kâr/zarar tabloları (günlük, haftalık, aylık, yıllık) ve performans istatistikleri."""
from __future__ import annotations

import math
from datetime import date

from .motorlar import MOTORLAR, MOTOR_BILGI
from .veri import yerel

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
         "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _r(x, n=2):
    return round(float(x), n)


def _tarih(s):
    y, m, d = (int(p) for p in s.split("-"))
    return date(y, m, d)


def gun_satirlari(p):
    out = []
    for k in sorted(p.gunler):
        g = dict(p.gunler[k])
        dt = _tarih(k)
        g["kz"] = _r(g["son"] - g["bas"])
        g["kz_yuzde"] = _r((g["son"] / g["bas"] - 1) * 100, 3) if g["bas"] else 0.0
        g["gun_adi"] = GUNLER[dt.weekday()]
        iy, iw, _ = dt.isocalendar()
        g["hafta"] = "%04d-H%02d" % (iy, iw)
        g["ay"] = "%04d-%02d" % (dt.year, dt.month)
        g["yil"] = "%04d" % dt.year
        out.append(g)
    return out


def _topla(satirlar, anahtar, etiket_f):
    gruplar = {}
    sira = []
    for g in satirlar:
        k = g[anahtar]
        if k not in gruplar:
            gruplar[k] = []
            sira.append(k)
        gruplar[k].append(g)
    out = []
    for k in sira:
        gs = gruplar[k]
        bas, son = gs[0]["bas"], gs[-1]["son"]
        out.append({
            "anahtar": k, "etiket": etiket_f(k, gs), "bas": bas, "son": son,
            "kz": _r(son - bas), "kz_yuzde": _r((son / bas - 1) * 100, 3) if bas else 0.0,
            "komisyon": _r(sum(g["komisyon"] for g in gs)),
            "gerceklesen": _r(sum(g["gerceklesen"] for g in gs)),
            "islem": sum(g["islem"] for g in gs), "kazanan": sum(g["kazanan"] for g in gs),
            "kaybeden": sum(g["kaybeden"] for g in gs), "gun_sayisi": len(gs),
            "ilk": gs[0]["tarih"], "son_gun": gs[-1]["tarih"],
        })
    return out


def _hafta_etiket(k, gs):
    a, b = _tarih(gs[0]["tarih"]), _tarih(gs[-1]["tarih"])
    yil, h = k.split("-H")
    if a.month == b.month:
        aralik = "%d–%d %s" % (a.day, b.day, AYLAR[a.month - 1])
    else:
        aralik = "%d %s – %d %s" % (a.day, AYLAR[a.month - 1][:3], b.day, AYLAR[b.month - 1][:3])
    return "%s. hafta (%s %s)" % (int(h), aralik, yil)


def _ay_etiket(k, gs):
    y, m = k.split("-")
    return "%s %s" % (AYLAR[int(m) - 1], y)


def tablolar(p):
    gunler = gun_satirlari(p)
    return {
        "gunler": gunler,
        "haftalar": _topla(gunler, "hafta", _hafta_etiket),
        "aylar": _topla(gunler, "ay", _ay_etiket),
        "yillar": _topla(gunler, "yil", lambda k, gs: k),
    }


def istatistik(p):
    satislar = [t for t in p.islemler if t["yon"] == "SAT"]
    kazanc = [t["kz"] for t in satislar if t["kz"] > 0]
    kayip = [t["kz"] for t in satislar if t["kz"] <= 0]
    gunler = [p.gunler[k] for k in sorted(p.gunler)]
    zirve = p.sermaye
    mdd = 0.0
    getiriler = []
    onceki = p.sermaye
    for g in gunler:
        zirve = max(zirve, g["son"])
        if zirve > 0:
            mdd = min(mdd, g["son"] / zirve - 1)
        if onceki > 0:
            getiriler.append(g["son"] / onceki - 1)
        onceki = g["son"]
    sharpe = None
    if len(getiriler) >= 10:
        ort = sum(getiriler) / len(getiriler)
        sd = math.sqrt(sum((x - ort) ** 2 for x in getiriler) / (len(getiriler) - 1))
        if sd > 0:
            sharpe = ort / sd * math.sqrt(252)
    ozk = p.ozkaynak()
    yillik = None
    if len(gunler) >= 20 and ozk > 0:
        yillik = ((ozk / p.sermaye) ** (252.0 / len(gunler)) - 1) * 100
    return {
        "ozkaynak": _r(ozk), "toplam_kz": _r(ozk - p.sermaye),
        "toplam_yuzde": _r((ozk / p.sermaye - 1) * 100, 2),
        "islem": len(p.islemler), "kapanan": len(satislar),
        "isabet": _r(len(kazanc) / len(satislar) * 100, 1) if satislar else None,
        "kar_faktoru": _r(sum(kazanc) / abs(sum(kayip)), 2) if kayip and sum(kayip) != 0 else None,
        "ort_kazanc": _r(sum(kazanc) / len(kazanc)) if kazanc else None,
        "ort_kayip": _r(sum(kayip) / len(kayip)) if kayip else None,
        "max_dusus": _r(mdd * 100, 2), "sharpe": None if sharpe is None else _r(sharpe, 2),
        "yillik_getiri": None if yillik is None else _r(yillik, 2),
        "komisyon": _r(sum(t["komisyon"] for t in p.islemler)),
        "gun_sayisi": len(gunler),
    }


def _seyrek(noktalar, maks=700):
    if len(noktalar) <= maks:
        return noktalar
    adim = len(noktalar) / float(maks)
    out = [noktalar[int(i * adim)] for i in range(maks)]
    out[-1] = noktalar[-1]
    return out


def _karar(sk, p, sym, ayar, endeks_ok=True):
    s = sk.get("konsey")
    if s is None:
        return "VERİ YOK"
    if sym in p.bekleyen:
        return "EMİR: " + p.bekleyen[sym]["yon"]
    if sym in p.poz:
        return "SAT" if s <= ayar["cikis_esigi"] else "TUT"
    if s >= ayar["giris_esigi"]:
        if not sk.get("rejim"):
            return "AL sinyali · rejim engeli"
        if not endeks_ok:
            return "AL sinyali · BIST100 engeli"
        if p.donmus:
            return "AL sinyali · zarar freni"
        if p.bekleme.get(sym) == p.gun:
            return "AL sinyali · bugün stop oldu"
        if len(p.poz) + p.bekleyen_al() >= int(ayar["max_acik_pozisyon"]):
            return "AL sinyali · pozisyon sınırı"
        if p.boyut(sk.get("fiyat"), sk.get("atr")) <= 0:
            return "AL sinyali · nakit yetersiz"
        return "AL"
    return "BEKLE"


def panel_verisi(k, ayar, mod, durum=None):
    p = k.portfoyler["konsey"]
    t = tablolar(p)
    st = istatistik(p)
    gunler = t["gunler"]
    bugun = gunler[-1] if gunler else None
    hafta = t["haftalar"][-1] if t["haftalar"] else None
    ay = t["aylar"][-1] if t["aylar"] else None
    yil = t["yillar"][-1] if t["yillar"] else None
    ozet = dict(st)
    ozet.update({
        "nakit": _r(p.nakit), "poz_degeri": _r(p.poz_degeri()), "acik_poz": len(p.poz),
        "sermaye": p.sermaye,
        "bugun_tarih": bugun["tarih"] if bugun else None,
        "bugun_kz": bugun["kz"] if bugun else 0.0, "bugun_yuzde": bugun["kz_yuzde"] if bugun else 0.0,
        "hafta_kz": hafta["kz"] if hafta else 0.0, "hafta_yuzde": hafta["kz_yuzde"] if hafta else 0.0,
        "ay_kz": ay["kz"] if ay else 0.0, "ay_yuzde": ay["kz_yuzde"] if ay else 0.0,
        "yil_kz": yil["kz"] if yil else 0.0, "yil_yuzde": yil["kz_yuzde"] if yil else 0.0,
        "zarar_freni": p.donmus,
        "baslangic": yerel(k.baslangic_T).strftime("%d.%m.%Y %H:%M") if k.baslangic_T else None,
        "son_bar": yerel(k.son_T).strftime("%d.%m.%Y %H:%M") if k.son_T else None,
    })
    if k.endeks_noktalar:
        ozet["endeks_yuzde"] = _r((k.endeks_noktalar[-1][1] / p.sermaye - 1) * 100, 2)

    islemler = []
    for x in reversed(p.islemler[-1500:]):
        y = dict(x)
        y["zaman"] = yerel(x["T"]).strftime("%d.%m.%Y %H:%M")
        y["tarih"] = yerel(x["T"]).strftime("%Y-%m-%d")
        islemler.append(y)

    sinyaller = []
    for sym in sorted(k.son_skorlar):
        sk = k.son_skorlar[sym]
        sinyaller.append({
            "sembol": sym, "fiyat": sk.get("fiyat"), "konsey": None if sk.get("konsey") is None else _r(sk["konsey"], 3),
            "tf": {tf: (None if v is None else _r(v, 3)) for tf, v in (sk.get("tf") or {}).items()},
            "motor": {m: (None if v is None else _r(v, 3)) for m, v in (sk.get("motor") or {}).items()},
            "rejim": sk.get("rejim"), "karar": _karar(sk, p, sym, ayar, getattr(k, "son_endeks_ok", True)),
            "zaman": yerel(sk["T"]).strftime("%d.%m %H:%M") if sk.get("T") else None,
        })
    sinyaller.sort(key=lambda r: -(r["konsey"] if r["konsey"] is not None else -9))

    motorlar = []
    for ad in ["konsey"] + MOTORLAR:
        pp = k.portfoyler[ad]
        bilgi = MOTOR_BILGI.get(ad, {"ad": "Konsey (5 motor x 4 zaman dilimi)", "aile": "Birleşik",
                                     "nasil": "", "kar": ""})
        motorlar.append({"kod": ad, "bilgi": bilgi, "ist": istatistik(pp),
                         "agirlik": None if ad == "konsey" else _r(k.agirlik.get(ad, 0) * 100, 1)})

    egri = {ad: _seyrek(pp.noktalar) for ad, pp in k.portfoyler.items()}
    egri["endeks"] = _seyrek(k.endeks_noktalar)

    bekleyen = [{"sembol": s, "yon": e["yon"], "adet": e["adet"], "sebep": e["sebep"],
                 "zaman": yerel(e["T"]).strftime("%d.%m %H:%M")} for s, e in p.bekleyen.items()]

    ozet["endeks_ok"] = getattr(k, "son_endeks_ok", True)
    return {"mod": mod, "ozet": ozet, "gunler": gunler, "haftalar": t["haftalar"], "aylar": t["aylar"],
            "yillar": t["yillar"], "pozisyonlar": p.pozisyon_listesi(), "bekleyen": bekleyen,
            "islemler": islemler, "sinyaller": sinyaller, "motorlar": motorlar, "egri": egri,
            "agirlik": {m: _r(w * 100, 1) for m, w in k.agirlik.items()},
            "durum": durum or {}}
