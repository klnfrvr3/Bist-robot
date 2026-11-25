# -*- coding: utf-8 -*-
"""Ayarlar: varsayılanlar + ayarlar.json."""
from __future__ import annotations

import copy
import json
import os

# BIST 30 — 1 Ekim–31 Aralık 2026 dönemi (DSTKF çıktı, TRMET girdi)
BIST30 = ["AEFES", "AKBNK", "ASELS", "ASTOR", "BIMAS", "EKGYO", "ENKAI", "EREGL", "FROTO", "GARAN",
          "GUBRF", "ISCTR", "KCHOL", "KRDMD", "MGROS", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE",
          "TAVHL", "TCELL", "THYAO", "TOASO", "TRALT", "TRMET", "TTKOM", "TUPRS", "VAKBN", "YKBNK"]

VARSAYILAN = {
    "baslangic_sermayesi": 100000.0,   # TL — panelden değiştirilir
    "komisyon_binde": 1.5,             # her alış ve satışta, işlem tutarının binde kaçı
    "bsmv_dahil": True,                # komisyon üzerine %5 BSMV eklensin mi
    "min_komisyon_tl": 0.0,
    "kayma_yuzde": 0.05,               # emir başına fiyat kayması (%)
    "evren": "tum",                    # tum: tüm BIST (YİP hariç, likiditeye göre) | liste: aşağıdaki liste
    "evren_max_hisse": 120,            # 'tum' modunda en likit kaç hisse
    "min_gunluk_hacim_tl": 10000000.0, # 'tum' modunda asgari günlük işlem hacmi (TL)
    "hisseler": BIST30,
    "endeks": "XU100",
    "veri_kaynagi": "otomatik",        # otomatik | yahoo | borsapy
    "zaman_dilimleri": {"15m": 0.15, "1h": 0.25, "2h": 0.25, "4h": 0.35},
    "adaptif_agirlik": True,
    "adaptif_pencere_gun": 20,
    "giris_esigi": 0.30,
    "cikis_esigi": -0.10,
    "islem_basina_risk_yuzde": 1.0,
    "max_pozisyon_yuzde": 20.0,
    "max_acik_pozisyon": 5,
    "atr_zaman_dilimi": "4h",          # stop ve lot hesabında kullanılan ATR
    "stop_atr_kat": 2.0,
    "iz_suren_atr_kat": 3.0,
    "basabas_atr_kat": 1.5,
    "gunluk_zarar_limiti_yuzde": 3.0,
    "endeks_filtresi": True,
    "goreli_guc_filtresi": False,      # yalnız son dönemde BIST100'den güçlü hisseleri al
    "likidite_kaymasi": True,          # sığ hissede ek fiyat kayması
    "rejim_filtresi": True,
    "min_islem_tl": 1000.0,
    "simulasyon_gun": 365,
    "port": 8765,
    "yenileme_sn": 300,
}

SAYISAL = {k for k, v in VARSAYILAN.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
MANTIKSAL = {k for k, v in VARSAYILAN.items() if isinstance(v, bool)}


def yol(kok):
    return os.path.join(kok, "ayarlar.json")


def yukle(kok):
    a = copy.deepcopy(VARSAYILAN)
    try:
        with open(yol(kok), "r", encoding="utf-8") as f:
            a.update(json.load(f))
    except FileNotFoundError:
        kaydet(kok, a)
    except Exception:
        pass
    return dogrula(a)


def kaydet(kok, a):
    tmp = yol(kok) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=2)
    os.replace(tmp, yol(kok))


def dogrula(a):
    """Panelden gelen değerleri tür ve aralık olarak temizle."""
    out = copy.deepcopy(VARSAYILAN)
    for k, v in a.items():
        if k not in VARSAYILAN:
            continue
        if k in SAYISAL:
            try:
                v = float(str(v).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if isinstance(VARSAYILAN[k], int):
                v = int(round(v))
        elif k in MANTIKSAL:
            v = v in (True, "true", "1", 1, "on", "evet")
        elif k == "hisseler":
            if isinstance(v, str):
                v = v.replace(",", " ").replace(";", " ").split()
            v = [s.strip().upper().replace(".IS", "") for s in v if s and s.strip()]
            v = list(dict.fromkeys(v))
            if not v:
                continue
        elif k == "zaman_dilimleri":
            try:
                v = {tf: max(0.0, float(v.get(tf, 0))) for tf in ("15m", "1h", "2h", "4h")}
            except Exception:
                continue
            if sum(v.values()) <= 0:
                continue
        elif k == "atr_zaman_dilimi":
            v = v if v in ("15m", "1h", "2h", "4h") else "4h"
        elif k == "evren":
            v = v if v in ("tum", "liste") else "tum"
        elif k in ("veri_kaynagi",):
            v = v if v in ("otomatik", "yahoo", "borsapy") else "otomatik"
        elif k == "endeks":
            v = str(v).strip().upper() or "XU100"
        out[k] = v
    # mantıklı sınırlar
    out["baslangic_sermayesi"] = max(1000.0, out["baslangic_sermayesi"])
    out["komisyon_binde"] = min(max(0.0, out["komisyon_binde"]), 50.0)
    out["kayma_yuzde"] = min(max(0.0, out["kayma_yuzde"]), 5.0)
    out["max_acik_pozisyon"] = min(max(1, out["max_acik_pozisyon"]), 30)
    out["max_pozisyon_yuzde"] = min(max(1.0, out["max_pozisyon_yuzde"]), 100.0)
    out["islem_basina_risk_yuzde"] = min(max(0.1, out["islem_basina_risk_yuzde"]), 10.0)
    out["simulasyon_gun"] = min(max(5, out["simulasyon_gun"]), 1100)
    out["yenileme_sn"] = min(max(60, out["yenileme_sn"]), 3600)
    out["evren_max_hisse"] = min(max(5, out["evren_max_hisse"]), 600)
    out["min_gunluk_hacim_tl"] = max(0.0, out["min_gunluk_hacim_tl"])
    out["giris_esigi"] = min(max(0.0, out["giris_esigi"]), 1.0)
    out["cikis_esigi"] = min(max(-1.0, out["cikis_esigi"]), out["giris_esigi"])
    return out
