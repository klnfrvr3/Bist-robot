# -*- coding: utf-8 -*-
"""BIST veri katmanı.

Kaynaklar:
  * yahoo   : Yahoo Finance grafik servisi (ek kütüphane gerekmez, ~15 dk gecikmeli)
  * borsapy : saidsurucu/borsapy (Borsa MCP'nin kullandığı kütüphane; TradingView kaynaklı)
  * otomatik: önce yahoo, olmazsa borsapy

15 dk ve 1 saatlik barlar doğrudan çekilir; 2 ve 4 saatlik barlar 1 saatlik
barlardan, BIST seansına hizalı olarak üretilir (seans 09:30 açılış emri,
10:00-18:00 sürekli işlem, 18:10 kapanış).
"""
from __future__ import annotations

import json
import math
import os
import threading
from array import array
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=3))          # Türkiye: kalıcı UTC+3
TABAN_DK = 9 * 60 + 30                      # 2s/4s kovaları için gün tabanı (09:30)
SEANS_SONU_DK = 18 * 60 + 10                # 18:10 kapanış seansı sonu
GUN_BITTI_DK = 18 * 60 + 15                 # bu saatten sonra günün son barı kesinleşmiş sayılır

ARALIK_SN = {"15m": 900, "1h": 3600}
TAM_ARALIK = {"15m": "60d", "1h": "730d"}   # Yahoo sınırları: 15dk ~60 gün, 1s ~730 gün
KISA_ARALIK = {"15m": "5d", "1h": "1mo"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ----------------------------------------------------------------- zaman

def yerel(t):
    return datetime.fromtimestamp(t, TZ)


def gun_no(t):
    """Yerel takvim günü (sıra numarası)."""
    return yerel(t).date().toordinal()


def dakika(t):
    d = yerel(t)
    return d.hour * 60 + d.minute


def gun_epoch(t, dk):
    """t'nin yerel gününde, gece yarısından dk dakika sonrasının epoch'u."""
    d = yerel(t)
    gece = datetime(d.year, d.month, d.day, tzinfo=TZ)
    return int(gece.timestamp()) + dk * 60


def gun_bitti_mi(t, simdi):
    """t'nin ait olduğu işlem günü, simdi itibarıyla kapanmış mı?"""
    if gun_no(simdi) > gun_no(t):
        return True
    return dakika(simdi) >= GUN_BITTI_DK


def tarih_str(t):
    return yerel(t).strftime("%Y-%m-%d")


# ----------------------------------------------------------------- seri

class Seri:
    """Bir sembol/zaman dilimi için OHLCV barları (bellek için sayı dizileri).

    ts: bar başlangıcı (epoch sn), te: barın kapandığı an (karar anı).
    """

    __slots__ = ("aralik", "ts", "te", "o", "h", "l", "c", "v")

    def __init__(self, aralik, ts, o, h, l, c, v, te=None):
        self.aralik = aralik
        self.ts = ts if isinstance(ts, array) else array("q", ts)
        self.o = o if isinstance(o, array) else array("d", o)
        self.h = h if isinstance(h, array) else array("d", h)
        self.l = l if isinstance(l, array) else array("d", l)
        self.c = c if isinstance(c, array) else array("d", c)
        self.v = v if isinstance(v, array) else array("d", v)
        if te is None:
            sn = ARALIK_SN.get(aralik, 3600)
            te = [min(t + sn, gun_epoch(t, SEANS_SONU_DK)) for t in self.ts]
        self.te = te if isinstance(te, array) else array("q", te)

    def __len__(self):
        return len(self.ts)

    @classmethod
    def satirlardan(cls, aralik, rows):
        if not rows:
            return cls(aralik, [], [], [], [], [], [])
        ts, o, h, l, c, v = (list(x) for x in zip(*rows))
        return cls(aralik, [int(t) for t in ts], o, h, l, c, v)

    def satirlar(self):
        return list(zip(self.ts, self.o, self.h, self.l, self.c, self.v))

    def dilim(self, a, b=None):
        return Seri(self.aralik, self.ts[a:b], self.o[a:b], self.h[a:b], self.l[a:b], self.c[a:b],
                    self.v[a:b], self.te[a:b])

    def ilk_n(self, n):
        return self.dilim(0, n)


def temizle(rows):
    """None değerleri at, sırala, tekrarları sil, son 'anlık görüntü' barını at."""
    temiz = {}
    for r in rows:
        if r is None or len(r) < 5:
            continue
        t, o, h, l, c = r[:5]
        v = r[5] if len(r) > 5 else 0
        if t is None or o is None or h is None or l is None or c is None:
            continue
        try:
            t = int(t)
            o, h, l, c = float(o), float(h), float(l), float(c)
            v = float(v or 0)
        except (TypeError, ValueError):
            continue
        if c <= 0 or o <= 0:
            continue
        hi = max(o, h, l, c)
        lo = min(o, h, l, c)
        temiz[t] = (t, o, hi, lo, c, v)
    out = [temiz[k] for k in sorted(temiz)]
    # Yahoo, seans sonunda 18:00 damgalı, hacmi 0 ve tek fiyatlı bir 'anlık görüntü' barı ekler.
    while out:
        t, o, h, l, c, v = out[-1]
        if dakika(t) >= 18 * 60 and v == 0 and h == l:
            out.pop()
        else:
            break
    return out


def kapali_barlar(seri, simdi):
    """Canlı modda henüz oluşmakta olan son barı çıkar (bakış-ileri hatasını önler). Seri ya da satır listesi alır."""
    satir = not isinstance(seri, Seri)
    if satir:
        seri = Seri.satirlardan("15m", seri) if seri else Seri("15m", [], [], [], [], [], [])
    n = len(seri)
    while n and seri.ts[n - 1] > simdi:
        n -= 1
    if n and not gun_bitti_mi(seri.ts[n - 1], simdi):
        n -= 1
    out = seri if n == len(seri) else seri.dilim(0, n)
    return out.satirlar() if satir else out


def ust_zaman_dilimi(s1h, dk, simdi):
    """1 saatlik seriden 2s (dk=120) veya 4s (dk=240) seri üret. Yalnız tamamlanmış kovalar."""
    kova_say = max(1, (SEANS_SONU_DK - TABAN_DK) // dk)
    gruplar = []          # [(gun, kova, [indeksler])]
    for i, t in enumerate(s1h.ts):
        g = gun_no(t)
        k = (dakika(t) - TABAN_DK) // dk
        k = 0 if k < 0 else (kova_say - 1 if k > kova_say - 1 else k)
        if gruplar and gruplar[-1][0] == g and gruplar[-1][1] == k:
            gruplar[-1][2].append(i)
        else:
            gruplar.append((g, k, [i]))
    ts, te, o, h, l, c, v = [], [], [], [], [], [], []
    for n, (g, k, idx) in enumerate(gruplar):
        son_te = max(s1h.te[j] for j in idx)
        t0 = s1h.ts[idx[0]]
        if k < kova_say - 1:
            nominal = gun_epoch(t0, TABAN_DK + (k + 1) * dk)
        else:
            nominal = gun_epoch(t0, SEANS_SONU_DK)
        tamam = (son_te >= nominal) or (n < len(gruplar) - 1) or gun_bitti_mi(t0, simdi)
        if not tamam:
            continue
        ts.append(t0)
        te.append(son_te)
        o.append(s1h.o[idx[0]])
        h.append(max(s1h.h[j] for j in idx))
        l.append(min(s1h.l[j] for j in idx))
        c.append(s1h.c[idx[-1]])
        v.append(sum(s1h.v[j] for j in idx))
    ad = "2h" if dk == 120 else ("4h" if dk == 240 else "%dm" % dk)
    return Seri(ad, ts, o, h, l, c, v, te)


# ----------------------------------------------------------------- kaynaklar

class VeriHatasi(Exception):
    pass


_SSL = None


def _ssl_baglam():
    """Sistem sertifikalarıyla HTTPS bağlamı. Android'de (Chaquopy) sistem CA dizinini de yükler."""
    global _SSL
    if _SSL is not None:
        return _SSL
    import re
    import ssl
    ctx = ssl.create_default_context()
    try:
        import certifi  # varsa
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    pem = []
    for d in ("/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts"):
        if os.path.isdir(d):
            for ad in os.listdir(d):
                try:
                    with open(os.path.join(d, ad), "r", encoding="ascii", errors="ignore") as f:
                        pem += re.findall(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", f.read(), re.S)
                except Exception:
                    pass
    if pem:
        try:
            ctx.load_verify_locations(cadata="\n".join(pem))
        except Exception:
            pass
    _SSL = ctx
    return ctx


def _http_json(url, zaman_asimi=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=zaman_asimi, context=_ssl_baglam()) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo_cek(sembol, aralik, rng):
    """(satırlar, bölünmeler) döndürür. Satır: (ts, o, h, l, c, v)."""
    ysem = urllib.parse.quote(sembol + ".IS")
    son_hata = None
    for deneme in range(4):
        host = "query1.finance.yahoo.com" if deneme % 2 == 0 else "query2.finance.yahoo.com"
        url = ("https://%s/v8/finance/chart/%s?interval=%s&range=%s"
               "&includePrePost=false&events=div%%7Csplit" % (host, ysem, aralik, rng))
        try:
            j = _http_json(url)
            ch = j.get("chart") or {}
            if not ch.get("result"):
                hata = ch.get("error") or {}
                raise VeriHatasi("%s %s: %s" % (sembol, aralik, hata.get("description") or hata))
            res = ch["result"][0]
            ts = res.get("timestamp") or []
            q = (res.get("indicators") or {}).get("quote") or [{}]
            q = q[0]
            n = len(ts)

            def kol(ad):
                x = q.get(ad) or []
                return list(x) + [None] * (n - len(x))

            rows = list(zip(ts, kol("open"), kol("high"), kol("low"), kol("close"), kol("volume")))
            bol = []
            for s in ((res.get("events") or {}).get("splits") or {}).values():
                try:
                    oran = float(s["numerator"]) / float(s["denominator"])
                    if oran > 0 and abs(oran - 1) > 1e-9:
                        bol.append((int(s["date"]), oran))
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    pass
            return rows, bol
        except VeriHatasi:
            raise
        except urllib.error.HTTPError as e:
            son_hata = e
            if e.code in (400, 404, 422):
                raise VeriHatasi("%s %s: HTTP %s" % (sembol, aralik, e.code))
        except Exception as e:  # ağ hatası, zaman aşımı, bozuk JSON
            son_hata = e
        time.sleep(1.5 * (deneme + 1))
    raise VeriHatasi("%s %s: Yahoo'ya ulaşılamadı (%s)" % (sembol, aralik, son_hata))


_BP_PERIYOT = {"15m": ["3mo", "1mo", "5d"], "1h": ["2y", "1y", "6mo", "3mo"]}
_BP_KISA = {"15m": ["5d", "1mo"], "1h": ["1mo", "3mo"]}


def borsapy_var_mi():
    try:
        import borsapy  # noqa: F401
        return True
    except Exception:
        return False


def borsapy_cek(sembol, aralik, kisa=False):
    try:
        import borsapy as bp
    except Exception:
        raise VeriHatasi("borsapy kurulu değil (pip install borsapy)")
    nesne = bp.Index(sembol) if sembol.upper().startswith("XU") else bp.Ticker(sembol)
    son_hata = None
    for per in (_BP_KISA if kisa else _BP_PERIYOT)[aralik]:
        try:
            df = nesne.history(period=per, interval=aralik)
            if df is None or len(df) == 0:
                continue
            kolon = {k.lower(): k for k in df.columns}
            rows = []
            for idx, r in df.iterrows():
                if getattr(idx, "tzinfo", None) is not None:
                    t = int(idx.timestamp())
                else:  # saat dilimi yoksa İstanbul saati kabul et
                    t = int(idx.timestamp()) - 3 * 3600
                rows.append((t, r[kolon["open"]], r[kolon["high"]], r[kolon["low"]],
                             r[kolon["close"]], r[kolon["volume"]] if "volume" in kolon else 0))
            return rows, []
        except Exception as e:
            son_hata = e
    raise VeriHatasi("%s %s: borsapy veri döndürmedi (%s)" % (sembol, aralik, son_hata))


# ----------------------------------------------------------------- yönetici

_hiz_kilit = threading.Lock()
_son_istek = [0.0]


def _hiz_siniri(aralik_sn=0.12):
    """Sunuculara saniyede ~8 istekten fazla gitme."""
    with _hiz_kilit:
        bekle = _son_istek[0] + aralik_sn - time.time()
        if bekle > 0:
            time.sleep(bekle)
        _son_istek[0] = time.time()


SAKLA_GUN = {"15m": 62, "1h": 800}


def _aralik_sec(aralik, son_ts, simdi):
    """Önbellekteki son bara göre ne kadar geriye gidileceğini seç (gereksiz indirmeyi önler)."""
    if son_ts is None:
        return TAM_ARALIK[aralik], True
    bosluk = simdi - son_ts
    if tarih_str(son_ts) == tarih_str(simdi):
        return "1d", False
    if bosluk <= 4 * 86400:
        return "5d", False
    if bosluk <= 25 * 86400:
        return "1mo", False
    return TAM_ARALIK[aralik], True


class VeriYoneticisi:
    """Önbellekli, artımlı veri çekici. Yalnız eksik kısmı indirir; bölünme görülürse hisseyi baştan çeker."""

    def __init__(self, klasor, kaynak="otomatik", log=print, isci=6):
        self.klasor = klasor
        self.kaynak = kaynak
        self.log = log
        self.isci = isci
        os.makedirs(klasor, exist_ok=True)
        self.ham = {}          # sym -> {"15m": Seri, "1h": Seri, "bol": [...], "kaynak": str}
        self.kilit = threading.Lock()
        self.son_kaynak = None

    def ham_ata(self, sym, rows15, rows1, bol=None, kaynak="?"):
        self.ham[sym] = {"15m": Seri.satirlardan("15m", temizle(rows15)), "1h": Seri.satirlardan("1h", temizle(rows1)),
                         "bol": [tuple(b) for b in (bol or [])], "kaynak": kaynak}

    # -- önbellek
    def _yol(self, sym, aralik):
        return os.path.join(self.klasor, "%s_%s.json" % (sym, aralik))

    def _oku(self, sym, aralik):
        try:
            with open(self._yol(sym, aralik), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _yaz(self, sym, aralik, rows, bol, kaynak):
        d = {"zaman": time.time(), "kaynak": kaynak, "rows": rows, "bol": bol}
        tmp = self._yol(sym, aralik) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, separators=(",", ":"))
        os.replace(tmp, self._yol(sym, aralik))

    # -- tek çekim
    def _cek(self, sym, aralik, rng, tam):
        sira = {"yahoo": ["yahoo"], "borsapy": ["borsapy"]}.get(self.kaynak, ["yahoo", "borsapy"])
        hatalar = []
        for k in sira:
            try:
                _hiz_siniri()
                if k == "yahoo":
                    rows, bol = yahoo_cek(sym, aralik, rng)
                else:
                    if not borsapy_var_mi():
                        hatalar.append("borsapy kurulu değil")
                        continue
                    rows, bol = borsapy_cek(sym, aralik, kisa=not tam)
                return rows, bol, k
            except Exception as e:
                hatalar.append(str(e))
        raise VeriHatasi("; ".join(hatalar))

    def _sembol_guncelle(self, sym, tam):
        sonuc = {"bol": []}
        simdi = time.time()
        for aralik in ("15m", "1h"):
            on = None if tam else self._oku(sym, aralik)
            eski = (on or {}).get("rows") or []
            son_ts = eski[-1][0] if eski else None
            rng, tam_mi = _aralik_sec(aralik, son_ts, simdi)
            rows, bol, kaynak = self._cek(sym, aralik, rng, tam_mi)
            eski_bol = set(tuple(b) for b in ((on or {}).get("bol") or []))
            yeni_bol = set(tuple(b) for b in bol) - eski_bol
            if not tam_mi and yeni_bol and eski:
                # bölünme/bedelsiz: geçmiş fiyatlar değişti, baştan çek
                rows, bol, kaynak = self._cek(sym, aralik, TAM_ARALIK[aralik], True)
                tam_mi = True
            if not tam_mi and eski:
                birlesik = {r[0]: r for r in eski}
                for r in rows:
                    birlesik[r[0]] = r
                rows = [birlesik[k] for k in sorted(birlesik)]
            sinir = simdi - SAKLA_GUN[aralik] * 86400
            rows = [r for r in temizle(rows) if r[0] >= sinir]
            bol_tum = sorted(eski_bol | set(tuple(b) for b in bol))
            self._yaz(sym, aralik, rows, [list(b) for b in bol_tum], kaynak)
            sonuc[aralik] = Seri.satirlardan(aralik, rows)
            sonuc["bol"] = sorted(set(sonuc["bol"]) | set(bol_tum))
            sonuc["kaynak"] = kaynak
        return sonuc

    def guncelle(self, semboller, tam=False, ilerleme=None):
        """Sembolleri çek/güncelle. Başarısız olanların listesini döndürür."""
        basarisiz = []
        tamam = [0]

        def is_(sym):
            try:
                r = self._sembol_guncelle(sym, tam)
                with self.kilit:
                    self.ham[sym] = r
                    self.son_kaynak = r.get("kaynak")
            except Exception as e:
                on15, on1 = self._oku(sym, "15m"), self._oku(sym, "1h")
                if on15 and on1 and on15.get("rows") and on1.get("rows"):
                    with self.kilit:
                        self.ham[sym] = {"15m": Seri.satirlardan("15m", temizle(on15["rows"])),
                                         "1h": Seri.satirlardan("1h", temizle(on1["rows"])),
                                         "bol": [tuple(b) for b in (on1.get("bol") or [])],
                                         "kaynak": (on1.get("kaynak") or "?") + " (önbellek)"}
                    self.log("UYARI %s güncellenemedi, önbellek kullanılıyor: %s" % (sym, e))
                else:
                    basarisiz.append(sym)
                    self.log("HATA %s verisi alınamadı: %s" % (sym, e))
            finally:
                with self.kilit:
                    tamam[0] += 1
                    if ilerleme:
                        ilerleme(tamam[0], len(semboller))

        with ThreadPoolExecutor(max_workers=self.isci) as ex:
            list(ex.map(is_, semboller))
        # artık evrende olmayan hisseleri bellekten at
        return basarisiz

    def birak(self, tut):
        tut = set(tut)
        for s in list(self.ham):
            if s not in tut:
                self.ham.pop(s, None)

    def seriler(self, sym, simdi=None):
        """{"15m","1h","2h","4h"} -> Seri (yalnızca kapanmış barlar)."""
        simdi = simdi or time.time()
        d = self.ham.get(sym)
        if not d:
            return None
        s15 = kapali_barlar(d["15m"], simdi)
        s1 = kapali_barlar(d["1h"], simdi)
        return {"15m": s15, "1h": s1,
                "2h": ust_zaman_dilimi(s1, 120, simdi),
                "4h": ust_zaman_dilimi(s1, 240, simdi)}

    def bolunmeler(self, sym):
        d = self.ham.get(sym) or {}
        return [tuple(b) for b in d.get("bol") or []]
