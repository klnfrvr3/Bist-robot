#!/usr/bin/env bash
# Emülatörde: APK'yı kur, aç, panel sunucusunu ve gerçek veriyle küçük bir simülasyonu dene.
set -u
APK="$1"
PKG=com.bistkonsey.robot
mkdir -p test_sonuc
adb install -r "$APK" > test_sonuc/kurulum.txt 2>&1
cat test_sonuc/kurulum.txt
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS || true
adb shell dumpsys deviceidle whitelist +$PKG || true
adb logcat -c || true
adb shell am start -n $PKG/.MainActivity
hazir=0
for i in $(seq 1 60); do
  sleep 3
  adb forward tcp:8765 tcp:8765 >/dev/null 2>&1
  if curl -s --max-time 5 http://127.0.0.1:8765/api/durum > test_sonuc/durum.json 2>/dev/null && grep -q program_surum test_sonuc/durum.json; then
    hazir=1
    break
  fi
done
echo "panel_hazir=$hazir (bekleme ~$((i*3)) sn)" | tee test_sonuc/ozet.txt
if [ "$hazir" = "1" ]; then
  curl -s -X POST -H 'Content-Type: application/json' -d '{"hisseler":"THYAO ASELS GARAN","simulasyon_gun":45}' http://127.0.0.1:8765/api/ayarlar > /dev/null
  curl -s -X POST -H 'Content-Type: application/json' -d '{"gun":45}' http://127.0.0.1:8765/api/simulasyon
  echo
  for i in $(seq 1 72); do
    sleep 5
    curl -s --max-time 10 http://127.0.0.1:8765/api/durum > test_sonuc/durum.json
    if grep -q '"sim_var": true' test_sonuc/durum.json && grep -q '"is": null' test_sonuc/durum.json; then break; fi
    if grep -q 'Simülasyon hatası' test_sonuc/durum.json; then break; fi
  done
  python3 - <<'PY' | tee -a test_sonuc/ozet.txt
import json
d = json.load(open("test_sonuc/durum.json"))
print("sim_var=%s | mesaj=%s | kaynak=%s | basarisiz=%s" % (d.get("sim_var"), d.get("mesaj"), d.get("veri_kaynagi"), d.get("basarisiz")))
print("\n".join(d.get("loglar", [])[-20:]))
PY
  curl -s --max-time 20 "http://127.0.0.1:8765/api/panel?mod=simulasyon" -o test_sonuc/panel_sim.json
  python3 -c "import json; d=json.load(open('test_sonuc/panel_sim.json')); o=d.get('ozet',{}); print('ozet:', {k:o.get(k) for k in ('ozkaynak','toplam_yuzde','islem','gun_sayisi')})" | tee -a test_sonuc/ozet.txt
  rm -f test_sonuc/panel_sim.json
  adb shell input keyevent KEYCODE_WAKEUP || true
  adb shell am start -n $PKG/.MainActivity || true
fi
sleep 4
adb exec-out screencap -p > test_sonuc/ekran.png
adb logcat -d > test_sonuc/logcat_tam.txt 2>/dev/null
grep -iE "BISTKonsey|python\.std|chaquopy|AndroidRuntime|FATAL" test_sonuc/logcat_tam.txt | tail -300 > test_sonuc/logcat.txt
rm -f test_sonuc/logcat_tam.txt
cat test_sonuc/ozet.txt
grep -q "panel_hazir=1" test_sonuc/ozet.txt
