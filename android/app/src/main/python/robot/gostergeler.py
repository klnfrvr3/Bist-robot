# -*- coding: utf-8 -*-
"""Teknik göstergeler — saf Python (ek kütüphane gerektirmez).

Tüm fonksiyonlar girdiyle aynı uzunlukta liste döndürür; yeterli veri
oluşmadan önceki elemanlar None olur.
"""
from __future__ import annotations

import math


def sma(x, n):
    out = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x, n):
    out = [None] * len(x)
    if len(x) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(x[:n]) / n
    out[n - 1] = e
    for i in range(n, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def _wilder(vals, n, start):
    """vals[start:] üzerinde Wilder yumuşatması (RMA)."""
    out = [None] * len(vals)
    if len(vals) - start < n:
        return out
    r = sum(vals[start:start + n]) / n
    out[start + n - 1] = r
    for i in range(start + n, len(vals)):
        r = (r * (n - 1) + vals[i]) / n
        out[i] = r
    return out


def rsi(c, n=14):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    up = [0.0] * len(c)
    dn = [0.0] * len(c)
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        up[i] = d if d > 0 else 0.0
        dn[i] = -d if d < 0 else 0.0
    au = _wilder(up, n, 1)
    ad = _wilder(dn, n, 1)
    for i in range(len(c)):
        if au[i] is None:
            continue
        if ad[i] == 0:
            out[i] = 100.0 if au[i] > 0 else 50.0
        else:
            rs = au[i] / ad[i]
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def true_range(h, l, c):
    tr = [0.0] * len(c)
    for i in range(len(c)):
        if i == 0:
            tr[i] = h[i] - l[i]
        else:
            pc = c[i - 1]
            tr[i] = max(h[i] - l[i], abs(h[i] - pc), abs(l[i] - pc))
    return tr


def atr(h, l, c, n=14):
    return _wilder(true_range(h, l, c), n, 0)


def adx(h, l, c, n=14):
    L = len(c)
    out = [None] * L
    if L < 2 * n + 1:
        return out
    pdm = [0.0] * L
    mdm = [0.0] * L
    for i in range(1, L):
        um = h[i] - h[i - 1]
        dm = l[i - 1] - l[i]
        pdm[i] = um if (um > dm and um > 0) else 0.0
        mdm[i] = dm if (dm > um and dm > 0) else 0.0
    tr = true_range(h, l, c)
    atr_ = _wilder(tr, n, 1)
    pdi_s = _wilder(pdm, n, 1)
    mdi_s = _wilder(mdm, n, 1)
    dx = [0.0] * L
    first = None
    for i in range(L):
        if atr_[i] is None or atr_[i] == 0:
            continue
        pdi = 100 * pdi_s[i] / atr_[i]
        mdi = 100 * mdi_s[i] / atr_[i]
        s = pdi + mdi
        dx[i] = 0.0 if s == 0 else 100 * abs(pdi - mdi) / s
        if first is None:
            first = i
    if first is None:
        return out
    return _wilder(dx, n, first)


def supertrend(h, l, c, n=10, mult=3.0):
    """(yön listesi, çizgi listesi). Yön: +1 yükseliş, -1 düşüş."""
    L = len(c)
    yon = [None] * L
    line = [None] * L
    a = atr(h, l, c, n)
    fub = flb = None
    d = 1
    for i in range(L):
        if a[i] is None:
            continue
        hl2 = (h[i] + l[i]) / 2.0
        bu = hl2 + mult * a[i]
        bl = hl2 - mult * a[i]
        if fub is None:
            fub, flb = bu, bl
            d = 1 if c[i] >= hl2 else -1
        else:
            fub = bu if (bu < fub or c[i - 1] > fub) else fub
            flb = bl if (bl > flb or c[i - 1] < flb) else flb
            if d == 1 and c[i] < flb:
                d = -1
            elif d == -1 and c[i] > fub:
                d = 1
        yon[i] = d
        line[i] = flb if d == 1 else fub
    return yon, line


def donchian_onceki(h, l, n):
    """Mevcut bar HARİÇ son n barın en yüksek/en düşük değeri."""
    L = len(h)
    up = [None] * L
    lo = [None] * L
    for i in range(n, L):
        up[i] = max(h[i - n:i])
        lo[i] = min(l[i - n:i])
    return up, lo


def macd(c, fast=12, slow=26, sig=9):
    ef = ema(c, fast)
    es = ema(c, slow)
    m = [None] * len(c)
    for i in range(len(c)):
        if ef[i] is not None and es[i] is not None:
            m[i] = ef[i] - es[i]
    start = next((i for i, v in enumerate(m) if v is not None), None)
    s = [None] * len(c)
    hist = [None] * len(c)
    if start is None:
        return m, s, hist
    sub = ema(m[start:], sig)
    for j, v in enumerate(sub):
        s[start + j] = v
        if v is not None:
            hist[start + j] = m[start + j] - v
    return m, s, hist


def roc(c, n=10):
    out = [None] * len(c)
    for i in range(n, len(c)):
        if c[i - n]:
            out[i] = (c[i] / c[i - n] - 1.0) * 100.0
    return out


def bollinger(c, n=20, k=2.0):
    mid = sma(c, n)
    up = [None] * len(c)
    lo = [None] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((v - m) ** 2 for v in w) / n)
        up[i] = m + k * sd
        lo[i] = m - k * sd
    return mid, up, lo


def isaret(x):
    if x is None:
        return 0
    return 1 if x > 0 else (-1 if x < 0 else 0)
