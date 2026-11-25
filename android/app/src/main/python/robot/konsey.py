# -*- coding: utf-8 -*-
"""Konsey motoru: 5 motor x 4 zaman dilimi oylarını birleştirip sanal portföyü yönetir.

Aynı veriyle her motor kendi 'gölge' portföyünde de tek başına işlem yapar. Gölge
portföylerin son N gündeki performansı, Konsey'deki oy ağırlıklarını belirler
(adaptif ağırlık): son dönemde piyasaya uyan motorun sözü daha çok geçer.
"""
from __future__ import annotations

import math
import time
from bisect import bisect_left, bisect_right

from .motorlar import MOTORLAR, sinyal_hesapla
from .portfoy import Portfoy
from .veri import tarih_str, Seri

ZAMAN_DILIMLERI = ["15m", "1h", "2h", "4h"]


def _son(seri, n=None, t0=None):
    """Seriyi son n bara ve/veya t0 anından sonrasına kırp (bellek ve hız)."""
    k = 0
    if t0 is not None:
        k = bisect_left(seri.ts, t0)
    if n is not None and len(seri) - k > n:
        k = len(seri) - n
    return seri if k == 0 else seri.dilim(k)


def _nan(x):
    return x is None or x != x


class Konsey:
    def __init__(self, ayar):
        self.ayar = ayar
        self.portfoyler = {"konsey": Portfoy("konsey", ayar)}
        for m in MOTORLAR:
            self.portfoyler[m] = Portfoy(m, ayar)
        self.agirlik = {m: 1.0 / len(MOTORLAR) for m in MOTORLAR}
        self.agirlik_gecmis = []
        self.son_T = None
        self.baslangic_T = None
        self.gun = None
        self.endeks_bas = None
        self.endeks_noktalar = []
        self.son_skorlar = {}
        self.son_endeks_ok = True
        self.veri = {}
        self.sig = {}
        self.endeks = None
        self.endeks_sig = None
        self.olaylar = []

    # ------------------------------------------------------------ hazırlık
    def hazirla(self, seriler, endeks=None, son_bar=None, bas_T=None):
        """seriler: sym -> {tf: Seri}. son_bar: canlı modda her seriden son N bar.
        bas_T: simülasyon başlangıcı; bundan 70 gün öncesi (gösterge ısınması) dışındaki veri atılır."""
        t0 = None if bas_T is None else bas_T - 70 * 86400
        self.veri = {}
        self.sig = {}
        for sym, d in seriler.items():
            if not d or len(d.get("1h") or []) == 0:
                continue
            d = {tf: _son(d[tf], son_bar, t0) for tf in ZAMAN_DILIMLERI}
            if len(d["1h"]) == 0:
                continue
            self.veri[sym] = d
            self.sig[sym] = {tf: sinyal_hesapla(d[tf]) for tf in ZAMAN_DILIMLERI}
        self.endeks = None
        self.endeks_sig = None
        if endeks and len(endeks.get("1h") or []) > 0:
            self.endeks = {tf: _son(endeks[tf], son_bar, t0) for tf in ZAMAN_DILIMLERI}
            self.endeks_sig = {tf: sinyal_hesapla(self.endeks[tf]) for tf in ("1h", "4h")}
        # likidite: o günden ÖNCEKİ 20 işlem gününün ortalama günlük TL hacmi (yalnız kayma maliyeti için;
        # geleceği kullanmaz, canlı ve simülasyon aynı sonucu verir)
        from .veri import gun_no
        self.lik_gun = {}
        for sym, d in self.veri.items():
            s1 = d["1h"]
            gunluk = {}
            for j in range(len(s1)):
                g = gun_no(s1.ts[j])
                gunluk[g] = gunluk.get(g, 0.0) + s1.c[j] * s1.v[j]
            gunler = sorted(gunluk)
            degerler = []
            for k in range(len(gunler)):
                onceki = [gunluk[x] for x in gunler[max(0, k - 20):k]]
                degerler.append(sum(onceki) / len(onceki) if len(onceki) >= 5 else 0.0)
            self.lik_gun[sym] = (gunler, degerler)
        for p in self.portfoyler.values():
            p.likidite = {}
        olaylar = []
        for sym, d in self.veri.items():
            s15, s1 = d["15m"], d["1h"]
            ilk15 = s15.ts[0] if len(s15) else None
            for i in range(len(s1)):
                if ilk15 is None or s1.te[i] <= ilk15:
                    olaylar.append((s1.te[i], sym, "1h", i))
            for i in range(len(s15)):
                olaylar.append((s15.te[i], sym, "15m", i))
        olaylar.sort()
        self.olaylar = olaylar

    def ortak_son_T(self, tolerans=3600):
        """Canlı mod: tüm hisselerin kapanmış barlarının ulaştığı ortak an (veri çekim zamanlaması
        farklı olduğunda bir hissenin barı atlanmasın diye). 1 saatten fazla geride kalan hisse
        (işlem durdurma vb.) beklenmez."""
        sonlar = []
        for d in self.veri.values():
            s = d["15m"] if len(d["15m"]) else d["1h"]
            if len(s):
                sonlar.append(s.te[-1])
        if not sonlar:
            return None
        mx = max(sonlar)
        return min(t for t in sonlar if t >= mx - tolerans)

    def ilk_T(self):
        return self.olaylar[0][0] if self.olaylar else None

    def son_veri_T(self):
        return self.olaylar[-1][0] if self.olaylar else None

    # ------------------------------------------------------------ yardımcılar
    def _idx(self, seri, T):
        return bisect_right(seri.te, T) - 1

    def _deger(self, sym, tf, ad, T):
        s = self.veri[sym][tf]
        i = self._idx(s, T)
        if i < 0:
            return None
        v = self.sig[sym][tf][ad][i]
        return None if v != v else v

    def _skor(self, sym, T, fiyat):
        W = self.ayar["zaman_dilimleri"]
        d, sg = self.veri[sym], self.sig[sym]
        motor_top = {m: 0.0 for m in MOTORLAR}
        motor_w = {m: 0.0 for m in MOTORLAR}
        tf_skor = {}
        ham = {}
        for tf in ZAMAN_DILIMLERI:
            w = float(W.get(tf, 0))
            i = self._idx(d[tf], T)
            if i < 0 or w <= 0:
                tf_skor[tf] = None
                continue
            ust, alt = 0.0, 0.0
            ham[tf] = {}
            for m in MOTORLAR:
                v = sg[tf][m][i]
                if v != v:
                    ham[tf][m] = None
                    continue
                ham[tf][m] = v
                motor_top[m] += w * v
                motor_w[m] += w
                if m in self._aktif():
                    ust += self.agirlik[m] * v
                    alt += self.agirlik[m]
            tf_skor[tf] = (ust / alt) if alt > 0 else None
        motor_skor = {m: (motor_top[m] / motor_w[m] if motor_w[m] > 0 else None) for m in MOTORLAR}
        aktif = self._aktif()
        ust = sum(self.agirlik[m] * s for m, s in motor_skor.items() if s is not None and m in aktif)
        alt = sum(self.agirlik[m] for m, s in motor_skor.items() if s is not None and m in aktif)
        konsey = ust / alt if alt > 0 else None

        rejim = True
        if self.ayar.get("rejim_filtresi", True):
            for tf in ("4h", "2h"):
                i = self._idx(d[tf], T)
                if i >= 0 and not _nan(sg[tf]["ema50"][i]):
                    rejim = d[tf].c[i] > sg[tf]["ema50"][i]
                    break
        atr = self._deger(sym, self.ayar.get("atr_zaman_dilimi", "4h"), "atr", T) or self._deger(sym, "1h", "atr", T)
        if self.ayar.get("goreli_guc_filtresi", False) and rejim and self.endeks:
            rejim = self._goreli_guc(sym, T) is not False
        return {"konsey": konsey, "motor": motor_skor, "tf": tf_skor, "rejim": rejim,
                "atr": atr, "fiyat": fiyat, "T": T}

    def _aktif(self):
        """Konsey'de oy kullanan motorlar (kapalı motorlar gölge portföyde çalışmaya devam eder)."""
        a = self.ayar.get("aktif_motorlar") or MOTORLAR
        return set(a)

    def _goreli_guc(self, sym, T, n=20):
        """Hisse son n adet 4 saatlik barda BIST100'den iyi mi? Veri yoksa None."""
        s, e = self.veri[sym]["4h"], self.endeks["4h"]
        i, j = self._idx(s, T), self._idx(e, T)
        if i < n or j < n or not s.c[i - n] or not e.c[j - n]:
            return None
        return s.c[i] / s.c[i - n] > e.c[j] / e.c[j - n]

    def _endeks_ok(self, T):
        if not self.ayar.get("endeks_filtresi", True) or not self.endeks:
            return True
        s4 = self.endeks["4h"]
        i = self._idx(s4, T)
        if i >= 0 and not _nan(self.endeks_sig["4h"]["ema50"][i]):
            if s4.c[i] > self.endeks_sig["4h"]["ema50"][i]:
                return True
            s1 = self.endeks["1h"]
            j = self._idx(s1, T)
            return j >= 0 and self.endeks_sig["1h"]["st_yon"][j] == 1
        return True

    def _endeks_kapanis(self, T):
        if not self.endeks:
            return None
        best = None
        for tf in ("15m", "1h"):
            s = self.endeks[tf]
            i = self._idx(s, T)
            if i >= 0 and (best is None or s.te[i] > best[0]):
                best = (s.te[i], s.c[i])
        return best[1] if best else None

    def _agirlik_guncelle(self):
        if not self.ayar.get("adaptif_agirlik", True):
            self.agirlik = {m: 1.0 / len(MOTORLAR) for m in MOTORLAR}
            return
        L = int(self.ayar.get("adaptif_pencere_gun", 20))
        perf = {}
        for m in MOTORLAR:
            g = self.portfoyler[m].gunler
            gunler = sorted(g)
            if len(gunler) < 5:
                return
            pencere = gunler[-L:]
            bas = g[pencere[0]]["bas"]
            son = g[pencere[-1]]["son"]
            perf[m] = (son / bas - 1.0) if bas > 0 else 0.0
        tau = 0.02
        mx = max(perf.values())
        ex = {m: math.exp((p - mx) / tau) for m, p in perf.items()}
        top = sum(ex.values())
        E = len(MOTORLAR)
        self.agirlik = {m: 0.5 / E + 0.5 * ex[m] / top for m in MOTORLAR}
        self.agirlik_gecmis.append([self.gun, {m: round(w, 4) for m, w in self.agirlik.items()}])
        if len(self.agirlik_gecmis) > 800:
            self.agirlik_gecmis = self.agirlik_gecmis[-800:]

    # ------------------------------------------------------------ çalıştırma
    def calistir(self, T_son=None, ilerleme=None):
        if not self.olaylar:
            return 0
        bas_i = 0
        if self.son_T is not None:
            bas_i = bisect_right(self.olaylar, (self.son_T, "￿", "", 1 << 60))
        son_i = len(self.olaylar)
        if T_son is not None:
            son_i = bisect_right(self.olaylar, (T_son, "￿", "", 1 << 60))
        if self.baslangic_T is None:
            self.baslangic_T = self.olaylar[bas_i][0] if bas_i < son_i else self.son_T
        adim = 0
        i = bas_i
        toplam = max(1, son_i - bas_i)
        son_bildirim = time.time()
        while i < son_i:
            T = self.olaylar[i][0]
            j = i
            while j < son_i and self.olaylar[j][0] == T:
                j += 1
            self._adim(T, self.olaylar[i:j])
            self.son_T = T
            adim += 1
            i = j
            if ilerleme and time.time() - son_bildirim > 0.5:
                son_bildirim = time.time()
                ilerleme((i - bas_i) / toplam)
        for p in self.portfoyler.values():
            p.gun_guncelle()
        return adim

    def _adim(self, T, grup):
        a = self.ayar
        d = tarih_str(T)
        if d != self.gun:
            if self.gun is not None:
                self._agirlik_guncelle()
            self.gun = d
        for p in self.portfoyler.values():
            p.gun_kontrol(T)
        lik = {}
        from .veri import gun_no
        g0 = gun_no(T)
        for (_, sym, _tf, _i) in grup:
            gl = getattr(self, "lik_gun", {}).get(sym)
            if gl:
                k = bisect_right(gl[0], g0) - 1
                if k >= 0 and gl[1][k] > 0:
                    lik[sym] = gl[1][k]
        for p in self.portfoyler.values():
            if not hasattr(p, "likidite"):
                p.likidite = {}
            p.likidite.update(lik)
        # dinamik evren: o gün itibarıyla (geçmiş 20 gün hacmine göre) en likit N hisse
        dn = int(self.ayar.get("dinamik_evren", 0) or 0)
        if dn > 0 and getattr(self, "_evren_gun", None) != g0:
            self._evren_gun = g0
            sira = []
            for sym2, gl in getattr(self, "lik_gun", {}).items():
                k = bisect_right(gl[0], g0) - 1
                if k >= 0 and gl[1][k] >= float(self.ayar.get("min_gunluk_hacim_tl", 0)):
                    sira.append((gl[1][k], sym2))
            sira.sort(reverse=True)
            self._evren_set = {x for _, x in sira[:dn]}

        # 1) yeni barlar: emirler açılışta gerçekleşir, stoplar kontrol edilir
        skorlar = {}
        for (_, sym, tf, i) in grup:
            s = self.veri[sym][tf]
            atr = self._deger(sym, a.get("atr_zaman_dilimi", "4h"), "atr", T) or self._deger(sym, "1h", "atr", T)
            for p in self.portfoyler.values():
                p.bar_isle(sym, s.o[i], s.h[i], s.l[i], s.c[i], T, atr, s.ts[i])
            skorlar[sym] = self._skor(sym, T, s.c[i])

        # 2) kararlar
        endeks_ok = self._endeks_ok(T)
        self.son_endeks_ok = endeks_ok
        giris = float(a["giris_esigi"])
        cikis = float(a["cikis_esigi"])
        maks = int(a["max_acik_pozisyon"])
        for ad, p in self.portfoyler.items():
            def S(sk):
                return sk["konsey"] if ad == "konsey" else sk["motor"].get(ad)

            for sym, sk in skorlar.items():
                s = S(sk)
                if sym in p.poz and sym not in p.bekleyen and s is not None and s <= cikis:
                    p.emir(sym, "SAT", p.poz[sym]["adet"], "Sinyal (skor %.2f)" % s, T, s)
            if p.zarar_freni() or not endeks_ok:
                continue
            adaylar = []
            for sym, sk in skorlar.items():
                s = S(sk)
                if s is None or s < giris or not sk["rejim"] or not sk["atr"]:
                    continue
                if sym in p.poz or sym in p.bekleyen or p.bekleme.get(sym) == d:
                    continue
                if int(a.get("dinamik_evren", 0) or 0) > 0 and sym not in getattr(self, "_evren_set", ()):
                    continue
                adaylar.append((s, sym))
            adaylar.sort(reverse=True)
            for s, sym in adaylar:
                if len(p.poz) + p.bekleyen_al() >= maks:
                    break
                sk = skorlar[sym]
                adet = p.boyut(sk["fiyat"], sk["atr"], sym)
                if adet > 0:
                    p.emir(sym, "AL", adet, "Sinyal (skor %.2f)" % s, T, s, sk["fiyat"], sk["atr"])

        for p in self.portfoyler.values():
            p.gun_guncelle()
            p.nokta(T)

        # 3) karşılaştırma: BIST100 al-tut
        ek = self._endeks_kapanis(T)
        if ek:
            if self.endeks_bas is None:
                self.endeks_bas = ek
            deger = round(self.portfoyler["konsey"].sermaye * ek / self.endeks_bas, 2)
            if self.endeks_noktalar and self.endeks_noktalar[-1][0] // 3600 == T // 3600:
                self.endeks_noktalar[-1] = [T, deger]
            else:
                self.endeks_noktalar.append([T, deger])

        for sym, sk in skorlar.items():
            self.son_skorlar[sym] = sk

    def skorlari_tazele(self, T=None):
        """İşlem yapmadan, her hissenin en son kapanmış barına göre güncel skorunu hesapla (panel için)."""
        for sym, d in self.veri.items():
            adaylar = []
            for tf in ("15m", "1h"):
                s = d[tf]
                i = len(s) - 1 if T is None else self._idx(s, T)
                if i >= 0:
                    adaylar.append((s.te[i], s.c[i]))
            if not adaylar:
                continue
            te, c = max(adaylar)
            self.son_skorlar[sym] = self._skor(sym, te, c)
            self.son_endeks_ok = self._endeks_ok(te)

    def bolunmeleri_uygula(self, bolunmeler):
        """bolunmeler: sym -> [(t, oran)] (yalnız canlı mod)."""
        for sym, liste in bolunmeler.items():
            for t, oran in liste:
                for p in self.portfoyler.values():
                    p.bolunme_uygula(sym, t, oran)

    # ------------------------------------------------------------ kalıcılık
    def to_dict(self):
        return {"portfoyler": {k: p.to_dict() for k, p in self.portfoyler.items()},
                "agirlik": self.agirlik, "agirlik_gecmis": self.agirlik_gecmis,
                "son_T": self.son_T, "baslangic_T": self.baslangic_T, "gun": self.gun,
                "endeks_bas": self.endeks_bas, "endeks_noktalar": self.endeks_noktalar,
                "son_skorlar": self.son_skorlar, "son_endeks_ok": self.son_endeks_ok}

    @classmethod
    def from_dict(cls, d, ayar):
        k = cls(ayar)
        k.portfoyler = {ad: Portfoy.from_dict(pd, ayar) for ad, pd in d["portfoyler"].items()}
        for kk in ("agirlik", "agirlik_gecmis", "son_T", "baslangic_T", "gun", "endeks_bas",
                   "endeks_noktalar", "son_skorlar", "son_endeks_ok"):
            if kk in d:
                setattr(k, kk, d[kk])
        return k
