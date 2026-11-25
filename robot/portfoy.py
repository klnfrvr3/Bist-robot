# -*- coding: utf-8 -*-
"""Sanal aracı kurum: nakit, pozisyonlar, emirler, komisyon, stoplar ve günlük kayıtlar."""
from __future__ import annotations

import math

from .veri import tarih_str, yerel


def _r(x, n=2):
    return round(float(x), n)


class Portfoy:
    def __init__(self, ad, ayar, sermaye=None):
        self.ad = ad
        self.ayar = ayar
        self.sermaye = float(sermaye if sermaye is not None else ayar["baslangic_sermayesi"])
        self.nakit = self.sermaye
        self.poz = {}            # sym -> pozisyon sözlüğü
        self.bekleyen = {}       # sym -> emir sözlüğü (bir sonraki barın açılışında gerçekleşir)
        self.islemler = []       # gerçekleşen emirler
        self.gunler = {}         # "YYYY-AA-GG" -> günlük kayıt
        self.gun = None
        self.gun_bas = self.sermaye
        self.donmus = False      # günlük zarar freni
        self.bekleme = {}        # sym -> tarih (stop olan hisseye aynı gün tekrar girilmez)
        self.son_fiyat = {}
        self.noktalar = []       # [[T, özkaynak], ...]
        self.bolunme_islenen = []

    # ------------------------------------------------------------ maliyetler
    def kom_orani(self):
        oran = float(self.ayar["komisyon_binde"]) / 1000.0
        if self.ayar.get("bsmv_dahil", True):
            oran *= 1.05
        return oran

    def komisyon(self, deger):
        if deger <= 0:
            return 0.0
        return max(deger * self.kom_orani(), float(self.ayar.get("min_komisyon_tl", 0) or 0))

    def kayma(self, sym=None):
        """Temel kayma + likiditeye bağlı ek kayma (sığ hissede alış-satış makası ve fiyat etkisi büyür):
        günlük 50 milyon TL hacimde +%0,10; 10 milyonda ~+%0,22; 500 milyonda ~+%0,03; en fazla +%0,50."""
        k = float(self.ayar.get("kayma_yuzde", 0.05)) / 100.0
        if sym and self.ayar.get("likidite_kaymasi", True):
            h = getattr(self, "likidite", {}).get(sym)
            if h:
                k += min(0.005, 0.001 * math.sqrt(5e7 / max(h, 1e6)))
        return k

    # ------------------------------------------------------------ değerleme
    def poz_degeri(self):
        return sum(p["adet"] * self.son_fiyat.get(s, p["giris"]) for s, p in self.poz.items())

    def ozkaynak(self):
        return self.nakit + self.poz_degeri()

    def rezerv(self):
        return sum(e.get("rezerv", 0.0) for e in self.bekleyen.values() if e["yon"] == "AL")

    def bekleyen_al(self):
        return sum(1 for e in self.bekleyen.values() if e["yon"] == "AL")

    # ------------------------------------------------------------ gün yönetimi
    def gun_kontrol(self, T):
        d = tarih_str(T)
        if d == self.gun:
            return False
        if self.gun is not None and self.gun in self.gunler:
            self.gunler[self.gun]["son"] = _r(self.ozkaynak())
        self.gun = d
        eq = self.ozkaynak()
        self.gun_bas = eq
        self.donmus = False
        self.gunler[d] = {"tarih": d, "bas": _r(eq), "son": _r(eq), "islem": 0, "al": 0, "sat": 0,
                          "komisyon": 0.0, "gerceklesen": 0.0, "kazanan": 0, "kaybeden": 0}
        return True

    def gun_guncelle(self):
        if self.gun in self.gunler:
            self.gunler[self.gun]["son"] = _r(self.ozkaynak())

    def zarar_freni(self):
        limit = float(self.ayar.get("gunluk_zarar_limiti_yuzde", 3.0) or 0)
        if limit > 0 and self.gun_bas > 0 and not self.donmus:
            if (self.ozkaynak() - self.gun_bas) / self.gun_bas * 100.0 <= -limit:
                self.donmus = True
        return self.donmus

    def nokta(self, T):
        eq = _r(self.ozkaynak())
        if self.noktalar and self.noktalar[-1][0] // 3600 == T // 3600:
            self.noktalar[-1] = [T, eq]
        else:
            self.noktalar.append([T, eq])

    # ------------------------------------------------------------ emir
    def boyut(self, fiyat, atr, sym=None):
        if not fiyat or not atr or atr <= 0:
            return 0
        a = self.ayar
        ozk = self.ozkaynak()
        risk_tl = ozk * float(a["islem_basina_risk_yuzde"]) / 100.0
        mesafe = float(a["stop_atr_kat"]) * atr
        a1 = math.floor(risk_tl / mesafe) if mesafe > 0 else 0
        a2 = math.floor(ozk * float(a["max_pozisyon_yuzde"]) / 100.0 / fiyat)
        kullanilabilir = self.nakit - self.rezerv()
        a3 = math.floor(kullanilabilir / (fiyat * (1 + self.kom_orani() + 2 * self.kayma(sym))))
        adet = max(0, min(a1, a2, a3))
        if adet * fiyat < float(a.get("min_islem_tl", 1000)):
            return 0
        return adet

    def emir(self, sym, yon, adet, sebep, T, skor=None, fiyat=None, atr=None):
        if adet <= 0 or sym in self.bekleyen:
            return False
        e = {"yon": yon, "adet": int(adet), "sebep": sebep, "T": T, "skor": skor, "atr": atr}
        if yon == "AL" and fiyat:
            e["rezerv"] = adet * fiyat * (1 + self.kom_orani() + 2 * self.kayma(sym))
        self.bekleyen[sym] = e
        return True

    def _kayit(self, T):
        d = tarih_str(T)
        if d not in self.gunler:
            self.gun_kontrol(T)
        return self.gunler[d]

    def _al_gerceklestir(self, sym, e, o, T, atr):
        p = o * (1 + self.kayma(sym))
        adet = e["adet"]
        k = self.komisyon(adet * p)
        if adet * p + k > self.nakit:
            adet = math.floor(self.nakit / (p * (1 + self.kom_orani())))
            k = self.komisyon(adet * p)
            while adet > 0 and adet * p + k > self.nakit:
                adet -= 1
                k = self.komisyon(adet * p)
        if adet <= 0:
            return
        maliyet = adet * p + k
        self.nakit -= maliyet
        atr0 = e.get("atr") or atr or p * 0.02
        stop = p - float(self.ayar["stop_atr_kat"]) * atr0
        self.poz[sym] = {"adet": adet, "giris": p, "maliyet": maliyet, "T": T, "stop": stop,
                         "ilk_stop": stop, "en_yuksek": p, "atr_giris": atr0, "skor": e.get("skor")}
        g = self._kayit(T)
        g["islem"] += 1
        g["al"] += 1
        g["komisyon"] = _r(g["komisyon"] + k)
        self.islemler.append({"T": T, "sembol": sym, "yon": "AL", "adet": adet, "fiyat": _r(p, 4),
                              "tutar": _r(adet * p), "komisyon": _r(k), "sebep": e["sebep"],
                              "skor": None if e.get("skor") is None else _r(e["skor"], 3)})

    def _sat_gerceklestir(self, sym, fiyat, T, sebep):
        ps = self.poz.pop(sym, None)
        if not ps:
            return
        p = fiyat * (1 - self.kayma(sym))
        deger = ps["adet"] * p
        k = self.komisyon(deger)
        self.nakit += deger - k
        kz = deger - k - ps["maliyet"]
        g = self._kayit(T)
        g["islem"] += 1
        g["sat"] += 1
        g["komisyon"] = _r(g["komisyon"] + k)
        g["gerceklesen"] = _r(g["gerceklesen"] + kz)
        if kz > 0:
            g["kazanan"] += 1
        else:
            g["kaybeden"] += 1
        self.islemler.append({"T": T, "sembol": sym, "yon": "SAT", "adet": ps["adet"], "fiyat": _r(p, 4),
                              "tutar": _r(deger), "komisyon": _r(k), "sebep": sebep,
                              "kz": _r(kz), "kz_yuzde": _r(kz / ps["maliyet"] * 100.0, 2),
                              "giris_fiyat": _r(ps["giris"], 4), "giris_T": ps["T"],
                              "sure_saat": _r((T - ps["T"]) / 3600.0, 1)})
        if sebep.startswith("Stop") or sebep.startswith("İz"):
            self.bekleme[sym] = tarih_str(T)

    def bar_isle(self, sym, o, h, l, c, T, atr, ts=None):
        """Bir sembolün yeni kapanan barı: bekleyen emirler açılışta (ts), stoplar bar içinde."""
        acilis = ts if ts is not None else T
        e = self.bekleyen.pop(sym, None)
        if e:
            if e["yon"] == "AL" and sym not in self.poz:
                self._al_gerceklestir(sym, e, o, acilis, atr)
            elif e["yon"] == "SAT" and sym in self.poz:
                self._sat_gerceklestir(sym, o, acilis, e["sebep"])
        ps = self.poz.get(sym)
        if ps:
            if l <= ps["stop"]:
                fiyat = min(o, ps["stop"])
                sebep = "İz süren stop" if ps["stop"] > ps["ilk_stop"] + 1e-9 else "Stop-loss"
                self._sat_gerceklestir(sym, fiyat, T, sebep)
            else:
                ps["en_yuksek"] = max(ps["en_yuksek"], c)
                a = self.ayar
                if atr and atr > 0:
                    yeni = ps["en_yuksek"] - float(a["iz_suren_atr_kat"]) * atr
                    if c >= ps["giris"] + float(a["basabas_atr_kat"]) * ps["atr_giris"]:
                        basabas = ps["giris"] * (1 + 2 * self.kom_orani() + 2 * self.kayma(sym))
                        yeni = max(yeni, basabas)
                    if yeni > ps["stop"]:
                        ps["stop"] = yeni
        self.son_fiyat[sym] = c

    def bolunme_uygula(self, sym, t_bol, oran):
        """Canlı modda bedelsiz/bölünme sonrası adet ve fiyatları düzelt."""
        anahtar = "%s@%s" % (sym, t_bol)
        if anahtar in self.bolunme_islenen or oran <= 0:
            return False
        ps = self.poz.get(sym)
        degisti = False
        if ps and ps["T"] < t_bol:
            ps["adet"] = int(math.floor(ps["adet"] * oran + 1e-9))
            for k in ("giris", "stop", "ilk_stop", "en_yuksek", "atr_giris"):
                ps[k] = ps[k] / oran
            if sym in self.son_fiyat:
                self.son_fiyat[sym] /= oran
            degisti = True
        e = self.bekleyen.get(sym)
        if e and e["T"] < t_bol:
            e["adet"] = int(math.floor(e["adet"] * oran + 1e-9))
            degisti = True
        self.bolunme_islenen.append(anahtar)
        return degisti

    # ------------------------------------------------------------ kalıcılık
    def to_dict(self):
        return {k: getattr(self, k) for k in (
            "ad", "sermaye", "nakit", "poz", "bekleyen", "islemler", "gunler", "gun", "gun_bas",
            "donmus", "bekleme", "son_fiyat", "noktalar", "bolunme_islenen")}

    @classmethod
    def from_dict(cls, d, ayar):
        p = cls(d["ad"], ayar, d["sermaye"])
        for k, v in d.items():
            setattr(p, k, v)
        return p

    def pozisyon_listesi(self):
        out = []
        for s, ps in sorted(self.poz.items()):
            f = self.son_fiyat.get(s, ps["giris"])
            deger = ps["adet"] * f
            kz = deger - self.komisyon(deger) - ps["maliyet"]
            out.append({"sembol": s, "adet": ps["adet"], "giris": _r(ps["giris"], 4), "fiyat": _r(f, 4),
                        "deger": _r(deger), "kz": _r(kz), "kz_yuzde": _r(kz / ps["maliyet"] * 100, 2),
                        "stop": _r(ps["stop"], 4), "giris_zamani": yerel(ps["T"]).strftime("%d.%m.%Y %H:%M"),
                        "skor": ps.get("skor")})
        return out
