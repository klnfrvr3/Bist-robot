# -*- coding: utf-8 -*-
"""Beş al-sat motoru. Her motor her bar için [-1, +1] aralığında bir oy üretir.

+1 = güçlü al eğilimi, -1 = güçlü sat eğilimi, 0 = nötr, None = yetersiz veri.

Motorlar, piyasada kâr eden iki temel aileden türetilmiştir:
  Trend ailesi  : trend, supertrend, kirilim, momentum  -> düşük isabet, büyük kazanç (pozitif çarpıklık)
  Dönüş ailesi  : donus                                 -> yüksek isabet, küçük kazanç (negatif çarpıklık)
Konsey motoru bu oyları zaman dilimleri ve motor ağırlıklarıyla birleştirir.
"""
from __future__ import annotations

from array import array

from . import gostergeler as g

NAN = float("nan")

MOTORLAR = ["trend", "supertrend", "kirilim", "momentum", "donus"]
ISINMA = 60  # bu kadar bar oluşmadan sinyal üretilmez

MOTOR_BILGI = {
    "trend": {
        "ad": "Trend Takipçisi (EMA 20/50 + ADX)",
        "aile": "Trend",
        "nasil": "Kısa ortalama uzun ortalamanın üstündeyse yükseliş trendi kabul edilir; ADX trendin gücünü ölçer. "
                 "Güçsüz trendde oy zayıflar.",
        "kar": "Az sayıda büyük trendi yakalayıp uzun süre taşır; kaybedenleri erken keser. İsabet oranı genelde "
               "%35-45 olsa da ortalama kazanç ortalama kayıptan büyüktür (CTA fonlarının ana mantığı).",
    },
    "supertrend": {
        "ad": "Supertrend (ATR 10 x 3)",
        "aile": "Trend",
        "nasil": "Fiyatın oynaklığa (ATR) göre çizilen bir bandı kırmasıyla yön değiştirir. Hem giriş hem iz süren stop görevi görür.",
        "kar": "Oynaklığa uyum sağlayan bir trend filtresidir; sakin piyasada sıkı, hareketli piyasada geniş durur.",
    },
    "kirilim": {
        "ad": "Kırılım / Kaplumbağa (Donchian 20/10)",
        "aile": "Trend",
        "nasil": "Fiyat son 20 barın zirvesini aşınca al, son 10 barın dibini kırınca sat (1980'lerin Turtle kuralları).",
        "kar": "Yeni zirve yapan hisse çoğu zaman yükselmeye devam eder; sıkışmadan çıkan sert hareketleri yakalar.",
    },
    "momentum": {
        "ad": "Momentum (MACD 12/26/9 + ROC 10)",
        "aile": "Trend",
        "nasil": "MACD histogramının işareti, eğimi ve 10 barlık değişim oranının oylaması.",
        "kar": "Hızlanan fiyat hareketine erken katılır; ivme kaybolunca çıkar.",
    },
    "donus": {
        "ad": "Ortalamaya Dönüş (RSI-2 + Bollinger, trend filtreli)",
        "aile": "Dönüş",
        "nasil": "Yükseliş trendindeki (fiyat > SMA50) hissede RSI(2) aşırı satıma inince al; aşırı alımda veya üst "
                 "Bollinger bandında sat. Düşüş trendinde alım yapmaz.",
        "kar": "Panik satışlarından sonraki tepki yükselişini toplar; isabet oranı yüksek, kazançlar küçüktür. "
               "Trend motorlarının zarar ettiği yatay piyasada kazandırarak dengeler.",
    },
}


def _kirp(x, a=-1.0, b=1.0):
    return a if x < a else (b if x > b else x)


def sinyal_hesapla(seri):
    """Seri için motor oyları ve yardımcı değerler."""
    n = len(seri)
    c, h, l = seri.c, seri.h, seri.l
    bos = [None] * n
    out = {m: list(bos) for m in MOTORLAR}
    out["atr"] = list(bos)
    out["ema50"] = list(bos)
    out["st_yon"] = list(bos)
    if n == 0:
        return {k: array("d") for k in out}

    e20 = g.ema(c, 20)
    e50 = g.ema(c, 50)
    ax = g.adx(h, l, c, 14)
    a14 = g.atr(h, l, c, 14)
    st_yon, _ = g.supertrend(h, l, c, 10, 3.0)
    up20, _ = g.donchian_onceki(h, l, 20)
    _, lo10 = g.donchian_onceki(h, l, 10)
    _, _, hist = g.macd(c, 12, 26, 9)
    r10 = g.roc(c, 10)
    s50 = g.sma(c, 50)
    r2 = g.rsi(c, 2)
    _, bb_up, _ = g.bollinger(c, 20, 2.0)

    out["atr"] = a14
    out["ema50"] = e50
    out["st_yon"] = st_yon

    kir_durum = 0
    for i in range(n):
        # kırılım durum makinesi ısınmadan önce de ilerlemeli
        if up20[i] is not None and c[i] > up20[i]:
            kir_durum = 1
        elif lo10[i] is not None and c[i] < lo10[i]:
            kir_durum = -1
        if i < ISINMA:
            continue

        # 1) Trend
        if e20[i] is not None and e50[i] is not None:
            yon = 1.0 if e20[i] > e50[i] else -1.0
            guc = _kirp(((ax[i] or 0.0) - 15.0) / 20.0, 0.0, 1.0)
            s = yon * (0.35 + 0.65 * guc)
            if (yon > 0 and c[i] < e50[i]) or (yon < 0 and c[i] > e50[i]):
                s *= 0.5
            out["trend"][i] = s

        # 2) Supertrend
        if st_yon[i] is not None:
            out["supertrend"][i] = float(st_yon[i])

        # 3) Kırılım
        out["kirilim"][i] = float(kir_durum)

        # 4) Momentum
        if hist[i] is not None and hist[i - 1] is not None:
            out["momentum"][i] = (g.isaret(hist[i]) + g.isaret(hist[i] - hist[i - 1]) + g.isaret(r10[i])) / 3.0

        # 5) Ortalamaya dönüş
        if s50[i] is not None and r2[i] is not None and bb_up[i] is not None:
            yukari = c[i] > s50[i]
            if yukari and r2[i] < 10:
                s = 1.0
            elif yukari and r2[i] < 25:
                s = 0.5
            elif r2[i] > 90 or c[i] > bb_up[i]:
                s = -0.7
            elif not yukari:
                s = -0.3
            else:
                s = 0.0
            out["donus"][i] = s
    # bellek için: None -> NaN, liste -> sayı dizisi
    return {k: array("d", (NAN if x is None else float(x) for x in v)) for k, v in out.items()}
