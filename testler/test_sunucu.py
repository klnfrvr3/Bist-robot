# -*- coding: utf-8 -*-
"""Sentetik veriyle sunucuyu ayağa kaldırır (panel görsel testi için)."""
import os
import shutil
import sys
import time
from datetime import date

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sentetik  # noqa: E402
from robot.sunucu import Robot, sunucu_baslat  # noqa: E402
from robot.veri import temizle  # noqa: E402

TMP = "/tmp/bist_panel_test"
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)
SEM = ["THYAO", "ASELS", "AKBNK", "GARAN", "TUPRS", "BIMAS", "KCHOL", "EREGL", "SISE", "FROTO"]
with open(os.path.join(TMP, "ayarlar.json"), "w") as f:
    import json
    json.dump({"evren": "liste", "hisseler": SEM, "baslangic_sermayesi": 250000, "komisyon_binde": 1.5}, f)

robot = Robot(TMP)
drift = float(os.environ.get("DRIFT", "0.12"))
for i, s in enumerate(SEM + ["XU100"]):
    r15, r1 = sentetik.uret(s, date(2023, 12, 25), date(2026, 11, 24), tohum=i + 11, endeks=(s == "XU100"),
                            fiyat0=40 + 30 * i, drift_olcek=drift)
    robot.vy.ham_ata(s, r15, r1, kaynak="sentetik")
robot.vy.guncelle = lambda syms, tam=False, ilerleme=None: []
robot.vy.birak = lambda tut: None
robot.vy.son_kaynak = "sentetik-test"

if os.environ.get("BOS"):
    sunucu_baslat(robot, os.path.join(KOK, "robot", "panel.html"), 8799)
    print("SUNUCU HAZIR", flush=True)
    while True:
        time.sleep(1)
robot.simulasyon_baslat(365)
time.sleep(0.5)
while robot.durum.get("is") == "simulasyon":
    time.sleep(0.3)
print("sim bitti", robot.durum["mesaj"])
# canlı: 10 gün önceden başlat ki tablolar dolsun
robot.canli_baslat()
robot.canli.son_T = robot.canli.baslangic_T = time.time() - 10 * 86400
robot.canli_adim()
print("canlı:", robot.durum["mesaj"], "işlem", len(robot.canli.portfoyler["konsey"].islemler))
sunucu_baslat(robot, os.path.join(KOK, "robot", "panel.html"), 8799)
print("SUNUCU HAZIR", flush=True)
while True:
    time.sleep(1)
