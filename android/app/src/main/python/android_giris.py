# -*- coding: utf-8 -*-
"""Android girişi: masaüstündeki robotun aynısını uygulama içinde başlatır."""
import threading

from robot.sunucu import Robot, sunucu_baslat

_robot = None
_sunucu = None
_port = None
_kilit = threading.Lock()


def baslat(kok, panel_yolu, port=8765):
    global _robot, _sunucu, _port
    with _kilit:
        if _robot is not None:
            return _port
        r = Robot(kok)
        son_hata = None
        for p in range(int(port), int(port) + 20):
            try:
                _sunucu = sunucu_baslat(r, panel_yolu, p)
                _port = p
                break
            except OSError as e:
                son_hata = e
        if _sunucu is None:
            raise RuntimeError("Yerel panel sunucusu açılamadı: %s" % son_hata)
        threading.Thread(target=r.canli_dongu, daemon=True).start()
        if r.canli is not None and r.canli_aktif:
            r._zorla.set()
        r.log("BIST Konsey Robotu Android'de çalışıyor (port %d)." % _port)
        _robot = r
        return _port


def zorla_guncelle():
    if _robot is not None and _robot.canli_aktif:
        _robot._zorla.set()


def durdur():
    if _robot is not None:
        _robot.dur = True
        _robot._zorla.set()
    if _sunucu is not None:
        try:
            _sunucu.shutdown()
        except Exception:
            pass
