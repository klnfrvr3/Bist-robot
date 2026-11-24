# -*- coding: utf-8 -*-
"""BIST Konsey Robotu — sanal (kâğıt üzerinde) otomatik al-sat programı.

Kullanım:
  python bist_robot.py                  Paneli başlatır (http://127.0.0.1:8765) ve tarayıcıyı açar
  python bist_robot.py --simulasyon 365 Konsolda geçmiş simülasyonu çalıştırır
  python bist_robot.py --veri-testi     Veri kaynağını dener
  python bist_robot.py --port 9000      Farklı port
  python bist_robot.py --tarayici-yok   Tarayıcıyı otomatik açma

UYARI: Bu program yatırım tavsiyesi değildir. Gerçek emir göndermez; tüm işlemler sanaldır.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import webbrowser

KOK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KOK)

if sys.version_info < (3, 8):
    print("Bu program Python 3.8 veya üzerini gerektirir. Kurulu sürüm:", sys.version)
    sys.exit(1)

try:  # Windows konsolunda Türkçe karakterler
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from robot.sunucu import Robot, SURUM, sunucu_baslat  # noqa: E402
from robot.veri import yahoo_cek, borsapy_cek, borsapy_var_mi, temizle, yerel  # noqa: E402


def veri_testi():
    print("Veri kaynağı testi\n" + "-" * 40)
    for sym, aralik, rng in (("THYAO", "15m", "1d"), ("THYAO", "1h", "5d"), ("XU100", "15m", "1d")):
        try:
            t0 = time.time()
            rows, _ = yahoo_cek(sym, aralik, rng)
            rows = temizle(rows)
            son = rows[-1]
            print("Yahoo   %-6s %-4s %4d bar  son: %s  kapanış %.2f  (%.1f sn)" % (
                sym, aralik, len(rows), yerel(son[0]).strftime("%d.%m %H:%M"), son[4], time.time() - t0))
        except Exception as e:
            print("Yahoo   %-6s %-4s HATA: %s" % (sym, aralik, e))
    if borsapy_var_mi():
        try:
            rows, _ = borsapy_cek("THYAO", "15m", kisa=True)
            rows = temizle(rows)
            print("borsapy THYAO  15m  %4d bar  son: %s  kapanış %.2f" % (
                len(rows), yerel(rows[-1][0]).strftime("%d.%m %H:%M"), rows[-1][4]))
        except Exception as e:
            print("borsapy HATA:", e)
    else:
        print("borsapy kurulu değil (isteğe bağlı): pip install borsapy")


def konsol_simulasyon(robot, gun):
    robot.simulasyon_baslat(gun)
    time.sleep(0.3)
    son = ""
    while robot.durum.get("is") == "simulasyon":
        m = "%s  [%3d%%]" % (robot.durum.get("mesaj"), int(100 * robot.durum.get("ilerleme", 0)))
        if m != son:
            print("\r" + m.ljust(70), end="", flush=True)
            son = m
        time.sleep(0.5)
    print()
    if robot.sim is None:
        print("Simülasyon sonucu yok:", robot.durum.get("mesaj"))
        return
    from robot.rapor import istatistik, tablolar
    print("\n%-12s %14s %9s %7s %8s %8s %7s" % ("Motor", "Özkaynak TL", "Getiri%", "İşlem", "İsabet%", "MaxDüş%", "Sharpe"))
    for ad, p in robot.sim.portfoyler.items():
        st = istatistik(p)
        print("%-12s %14.2f %9.2f %7d %8s %8.2f %7s" % (
            ad, st["ozkaynak"], st["toplam_yuzde"], st["islem"], st["isabet"], st["max_dusus"], st["sharpe"]))
    if robot.sim.endeks_noktalar:
        e = robot.sim.endeks_noktalar[-1][1]
        print("%-12s %14.2f %9.2f   (BIST100 al-tut karşılaştırması)" % (
            "XU100", e, (e / robot.sim.portfoyler["konsey"].sermaye - 1) * 100))
    t = tablolar(robot.sim.portfoyler["konsey"])
    print("\nAylık kâr/zarar (Konsey):")
    for a in t["aylar"]:
        print("  %-16s %12.2f TL  %7.2f%%  komisyon %9.2f  işlem %4d" % (
            a["etiket"], a["kz"], a["kz_yuzde"], a["komisyon"], a["islem"]))


def main():
    ap = argparse.ArgumentParser(description="BIST Konsey Robotu")
    ap.add_argument("--simulasyon", nargs="?", const=-1, type=int, help="geçmiş simülasyon (gün)")
    ap.add_argument("--veri-testi", action="store_true")
    ap.add_argument("--port", type=int)
    ap.add_argument("--tarayici-yok", action="store_true")
    a = ap.parse_args()

    if a.veri_testi:
        veri_testi()
        return

    robot = Robot(KOK)
    if a.simulasyon is not None:
        konsol_simulasyon(robot, None if a.simulasyon == -1 else a.simulasyon)
        return

    port = a.port or int(robot.ayar.get("port", 8765))
    panel = os.path.join(KOK, "robot", "panel.html")
    try:
        sunucu_baslat(robot, panel, port)
    except OSError:
        print("Port %d kullanımda. Program zaten açık olabilir; tarayıcıda http://127.0.0.1:%d adresini açın." % (port, port))
        if not a.tarayici_yok:
            webbrowser.open("http://127.0.0.1:%d" % port)
        return
    url = "http://127.0.0.1:%d" % port
    robot.log("BIST Konsey Robotu %s çalışıyor: %s  (kapatmak için bu pencerede Ctrl+C)" % (SURUM, url))
    if not a.tarayici_yok:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    import threading
    threading.Thread(target=robot.canli_dongu, daemon=True).start()
    if robot.canli is not None and robot.canli_aktif:
        robot._zorla.set()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        robot.dur = True
        robot.log("Kapatılıyor...")


if __name__ == "__main__":
    main()
