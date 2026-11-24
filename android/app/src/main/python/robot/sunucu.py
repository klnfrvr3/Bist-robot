# -*- coding: utf-8 -*-
"""Robot denetleyicisi + yerel web paneli (http://127.0.0.1:8765)."""
from __future__ import annotations

import copy
import json
import os
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import ayarlar as A
from .konsey import Konsey
from .rapor import panel_verisi
from .veri import VeriYoneticisi, borsapy_var_mi, dakika, yerel

SURUM = "1.0"


class Robot:
    def __init__(self, kok):
        self.kok = kok
        self.veri_klasor = os.path.join(kok, "veri")
        os.makedirs(self.veri_klasor, exist_ok=True)
        self.loglar = deque(maxlen=500)
        self.log_dosya = os.path.join(self.veri_klasor, "robot.log")
        self.ayar = A.yukle(kok)
        self.vy = VeriYoneticisi(os.path.join(self.veri_klasor, "onbellek"), self.ayar["veri_kaynagi"], log=self.log)
        self.kilit = threading.RLock()
        self.dur = False
        self.surum = 0
        self.onbellek = {}
        self.canli = None
        self.canli_aktif = False
        self.sim = None
        self.sim_ayar = None
        self.sim_bilgi = {}
        self.durum = {"is": None, "ilerleme": 0.0, "mesaj": "Hazır", "son_guncelleme": None,
                      "veri_kaynagi": None, "basarisiz": [], "borsapy": borsapy_var_mi()}
        self._yukle()
        self._zorla = threading.Event()

    # ------------------------------------------------------------ yardımcılar
    def log(self, mesaj):
        satir = "%s  %s" % (yerel(time.time()).strftime("%d.%m %H:%M:%S"), mesaj)
        self.loglar.append(satir)
        try:
            print(satir, flush=True)
        except Exception:
            pass
        try:
            with open(self.log_dosya, "a", encoding="utf-8") as f:
                f.write(satir + "\n")
        except Exception:
            pass

    def _degisti(self):
        self.surum += 1
        self.onbellek = {}

    def _yaz_json(self, ad, veri):
        yol = os.path.join(self.veri_klasor, ad)
        tmp = yol + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, yol)

    def _oku_json(self, ad):
        try:
            with open(os.path.join(self.veri_klasor, ad), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _yukle(self):
        d = self._oku_json("canli_durum.json")
        if d and d.get("konsey"):
            try:
                self.canli = Konsey.from_dict(d["konsey"], self.ayar)
                self.canli_aktif = bool(d.get("aktif"))
                self.log("Canlı sanal portföy yüklendi (başlangıç %s)." % (
                    yerel(self.canli.baslangic_T).strftime("%d.%m.%Y %H:%M") if self.canli.baslangic_T else "?"))
            except Exception as e:
                self.log("UYARI canlı durum okunamadı: %s" % e)
        s = self._oku_json("simulasyon.json")
        if s and s.get("konsey"):
            try:
                self.sim_ayar = A.dogrula(s.get("ayar") or {})
                self.sim = Konsey.from_dict(s["konsey"], self.sim_ayar)
                self.sim_bilgi = s.get("bilgi") or {}
            except Exception as e:
                self.log("UYARI simülasyon sonucu okunamadı: %s" % e)

    def _kaydet_canli(self):
        if self.canli is not None:
            self._yaz_json("canli_durum.json", {"aktif": self.canli_aktif, "konsey": self.canli.to_dict()})

    def semboller(self):
        return list(self.ayar["hisseler"])

    # ------------------------------------------------------------ ayarlar
    def ayar_kaydet(self, yeni):
        with self.kilit:
            birlesik = dict(self.ayar)
            birlesik.update(yeni or {})
            temiz = A.dogrula(birlesik)
            self.ayar.clear()
            self.ayar.update(temiz)
            A.kaydet(self.kok, self.ayar)
            self.vy.kaynak = self.ayar["veri_kaynagi"]
            self._degisti()
        self.log("Ayarlar kaydedildi: sermaye %.0f TL, komisyon binde %.2f%s, kayma %%%.2f, %d hisse." % (
            self.ayar["baslangic_sermayesi"], self.ayar["komisyon_binde"],
            " + BSMV" if self.ayar["bsmv_dahil"] else "", self.ayar["kayma_yuzde"], len(self.ayar["hisseler"])))
        return self.ayar

    # ------------------------------------------------------------ veri
    def _veri_al(self, tam=False, ilerleme=None):
        syms = self.semboller() + [self.ayar["endeks"]]
        basarisiz = self.vy.guncelle(syms, tam=tam, ilerleme=ilerleme)
        self.durum["basarisiz"] = basarisiz
        self.durum["veri_kaynagi"] = self.vy.son_kaynak
        simdi = time.time()
        seriler = {}
        for s in self.semboller():
            if s in self.vy.ham:
                sr = self.vy.seriler(s, simdi)
                if sr and len(sr["1h"]) > 0:
                    seriler[s] = sr
        endeks = self.vy.seriler(self.ayar["endeks"], simdi) if self.ayar["endeks"] in self.vy.ham else None
        return seriler, endeks

    # ------------------------------------------------------------ canlı
    def seans_yakin(self):
        d = yerel(time.time())
        return d.weekday() < 5 and 9 * 60 + 40 <= dakika(time.time()) <= 18 * 60 + 40

    def canli_baslat(self):
        with self.kilit:
            self.canli = Konsey(self.ayar)
            simdi = time.time()
            self.canli.son_T = simdi
            self.canli.baslangic_T = simdi
            self.canli_aktif = True
            self._kaydet_canli()
            self._degisti()
        self.log("CANLI sanal işlem başlatıldı: %.2f TL sermaye, komisyon binde %.2f." % (
            self.ayar["baslangic_sermayesi"], self.ayar["komisyon_binde"]))
        self._zorla.set()

    def canli_durdur(self):
        with self.kilit:
            self.canli_aktif = False
            self._kaydet_canli()
            self._degisti()
        self.log("Canlı sanal işlem duraklatıldı.")

    def canli_devam(self):
        if self.canli is None:
            return self.canli_baslat()
        with self.kilit:
            self.canli_aktif = True
            self._kaydet_canli()
            self._degisti()
        self.log("Canlı sanal işlem devam ediyor.")
        self._zorla.set()

    def canli_adim(self):
        if self.durum.get("is") == "simulasyon":
            return
        self.durum.update({"is": "canli", "mesaj": "Canlı veri güncelleniyor..."})
        try:
            seriler, endeks = self._veri_al()
            if not seriler:
                self.durum["mesaj"] = "Veri alınamadı — internet bağlantısını kontrol edin."
                return
            with self.kilit:
                k = self.canli
                if k is None:
                    return
                k.ayar = self.ayar
                k.hazirla(seriler, endeks, son_bar=600)
                k.bolunmeleri_uygula({s: self.vy.bolunmeler(s) for s in seriler})
                onceki = len(k.portfoyler["konsey"].islemler)
                n = k.calistir(T_son=k.ortak_son_T())
                k.skorlari_tazele()
                yeni = k.portfoyler["konsey"].islemler[onceki:]
                self._kaydet_canli()
                self._degisti()
            for x in yeni:
                self.log("İŞLEM %s %s %d adet @ %.2f (%s)%s" % (
                    x["yon"], x["sembol"], x["adet"], x["fiyat"], x["sebep"],
                    ("  K/Z %.2f TL" % x["kz"]) if "kz" in x else ""))
            self.durum["son_guncelleme"] = yerel(time.time()).strftime("%d.%m.%Y %H:%M:%S")
            self.durum["mesaj"] = "Güncel. %d yeni bar adımı işlendi, son bar: %s" % (
                n, yerel(k.son_T).strftime("%d.%m %H:%M") if k.son_T else "-")
        except Exception as e:
            self.durum["mesaj"] = "Hata: %s" % e
            self.log("HATA canlı adım: %s\n%s" % (e, traceback.format_exc()))
        finally:
            self.durum["is"] = None

    def canli_dongu(self):
        son = 0.0
        while not self.dur:
            try:
                if self.canli_aktif and self.canli is not None:
                    aralik = self.ayar["yenileme_sn"] if self.seans_yakin() else 1800
                    if self._zorla.is_set() or time.time() - son >= aralik:
                        self._zorla.clear()
                        son = time.time()
                        self.canli_adim()
            except Exception as e:
                self.log("HATA döngü: %s" % e)
            self._zorla.wait(5)

    # ------------------------------------------------------------ simülasyon
    def simulasyon_baslat(self, gun=None):
        if self.durum.get("is") == "simulasyon":
            return False
        gun = int(gun or self.ayar["simulasyon_gun"])
        threading.Thread(target=self._simulasyon, args=(gun,), daemon=True).start()
        return True

    def _simulasyon(self, gun):
        while self.durum.get("is") == "canli":
            time.sleep(0.5)
        self.durum.update({"is": "simulasyon", "ilerleme": 0.0, "mesaj": "Geçmiş veri indiriliyor..."})
        t0 = time.time()
        try:
            def il_veri(a, b):
                self.durum["ilerleme"] = 0.4 * a / max(1, b)
                self.durum["mesaj"] = "Veri indiriliyor: %d / %d sembol" % (a, b)

            seriler, endeks = self._veri_al(ilerleme=il_veri)
            if not seriler:
                raise RuntimeError("Hiçbir hisse için veri alınamadı. İnternet bağlantısını veya veri kaynağını kontrol edin.")
            ayar = copy.deepcopy(self.ayar)
            self.durum["mesaj"] = "Göstergeler hesaplanıyor..."
            k = Konsey(ayar)
            k.hazirla(seriler, endeks)
            ilk = k.ilk_T()
            bas = max(time.time() - gun * 86400, ilk + 45 * 86400)
            k.son_T = bas

            def il_sim(x):
                self.durum["ilerleme"] = 0.45 + 0.55 * x
                self.durum["mesaj"] = "Simülasyon çalışıyor: %%%d" % int(x * 100)

            k.calistir(ilerleme=il_sim)
            k.skorlari_tazele()
            bilgi = {"calisma": yerel(time.time()).strftime("%d.%m.%Y %H:%M"), "gun": gun,
                     "hisse": len(seriler), "sure_sn": round(time.time() - t0, 1),
                     "ilk15": None, "kaynak": self.vy.son_kaynak}
            ilk15 = [d["15m"].ts[0] for d in seriler.values() if len(d["15m"])]
            if ilk15:
                bilgi["ilk15"] = yerel(min(ilk15)).strftime("%d.%m.%Y")
            with self.kilit:
                self.sim = k
                self.sim_ayar = ayar
                self.sim_bilgi = bilgi
                self._yaz_json("simulasyon.json", {"ayar": ayar, "bilgi": bilgi, "konsey": k.to_dict()})
                self._degisti()
            p = k.portfoyler["konsey"]
            self.log("SİMÜLASYON bitti (%d gün, %d hisse, %.0f sn): özkaynak %.2f TL (%+.2f%%), %d işlem." % (
                gun, len(seriler), time.time() - t0, p.ozkaynak(), (p.ozkaynak() / p.sermaye - 1) * 100,
                len(p.islemler)))
            self.durum["mesaj"] = "Simülasyon tamamlandı."
            self.durum["ilerleme"] = 1.0
        except Exception as e:
            self.durum["mesaj"] = "Simülasyon hatası: %s" % e
            self.log("HATA simülasyon: %s\n%s" % (e, traceback.format_exc()))
        finally:
            self.durum["is"] = None

    # ------------------------------------------------------------ panel
    def panel(self, mod):
        anahtar = (mod, self.surum)
        if anahtar in self.onbellek:
            return self.onbellek[anahtar]
        with self.kilit:
            if mod == "simulasyon":
                if self.sim is None:
                    d = {"mod": mod, "bos": True}
                else:
                    d = panel_verisi(self.sim, self.sim_ayar or self.ayar, mod)
                    d["bilgi"] = self.sim_bilgi
                    d["ayar_ozet"] = {k: (self.sim_ayar or {}).get(k) for k in (
                        "baslangic_sermayesi", "komisyon_binde", "bsmv_dahil", "kayma_yuzde")}
            else:
                if self.canli is None:
                    d = {"mod": mod, "bos": True}
                else:
                    d = panel_verisi(self.canli, self.ayar, mod)
                    d["aktif"] = self.canli_aktif
        js = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.onbellek[anahtar] = js
        return js

    def genel_durum(self):
        d = dict(self.durum)
        d.update({"surum": self.surum, "canli_var": self.canli is not None, "canli_aktif": self.canli_aktif,
                  "sim_var": self.sim is not None, "seans": self.seans_yakin(),
                  "saat": yerel(time.time()).strftime("%d.%m.%Y %H:%M:%S"), "program_surum": SURUM,
                  "loglar": list(self.loglar)[-80:]})
        return d


# ---------------------------------------------------------------- HTTP

def isleyici_olustur(robot, panel_yolu):
    class Isleyici(BaseHTTPRequestHandler):
        server_version = "BISTKonsey/" + SURUM

        def log_message(self, *a):
            pass

        def _gonder(self, kod, govde, tur="application/json; charset=utf-8"):
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def _json(self, veri, kod=200):
            self._gonder(kod, json.dumps(veri, ensure_ascii=False).encode("utf-8"))

        def _govde(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return {}

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path in ("/", "/index.html"):
                    with open(panel_yolu, "rb") as f:
                        self._gonder(200, f.read(), "text/html; charset=utf-8")
                elif u.path == "/api/panel":
                    mod = (q.get("mod") or ["canli"])[0]
                    self._gonder(200, robot.panel("simulasyon" if mod == "simulasyon" else "canli"))
                elif u.path == "/api/durum":
                    self._json(robot.genel_durum())
                elif u.path == "/api/ayarlar":
                    self._json({"ayar": robot.ayar, "varsayilan": A.VARSAYILAN, "bist30": A.BIST30})
                else:
                    self._json({"hata": "bulunamadı"}, 404)
            except Exception as e:
                self._json({"hata": str(e)}, 500)

        def do_POST(self):
            u = urlparse(self.path)
            b = self._govde()
            try:
                if u.path == "/api/ayarlar":
                    self._json({"ok": True, "ayar": robot.ayar_kaydet(b)})
                elif u.path == "/api/canli/baslat":
                    if b.get("ayar"):
                        robot.ayar_kaydet(b["ayar"])
                    robot.canli_baslat()
                    self._json({"ok": True})
                elif u.path == "/api/canli/durdur":
                    robot.canli_durdur()
                    self._json({"ok": True})
                elif u.path == "/api/canli/devam":
                    robot.canli_devam()
                    self._json({"ok": True})
                elif u.path == "/api/canli/guncelle":
                    robot._zorla.set()
                    self._json({"ok": True})
                elif u.path == "/api/simulasyon":
                    if b.get("ayar"):
                        robot.ayar_kaydet(b["ayar"])
                    ok = robot.simulasyon_baslat(b.get("gun"))
                    self._json({"ok": ok, "mesaj": None if ok else "Zaten çalışan bir simülasyon var."})
                else:
                    self._json({"hata": "bulunamadı"}, 404)
            except Exception as e:
                robot.log("HATA API %s: %s" % (u.path, e))
                self._json({"hata": str(e)}, 500)

    return Isleyici


def sunucu_baslat(robot, panel_yolu, port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), isleyici_olustur(robot, panel_yolu))
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
