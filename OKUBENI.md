# BIST Konsey Robotu

Borsa İstanbul hisselerinde **sanal parayla** (kâğıt üzerinde) kendi kendine al-sat yapan program.
15 dakikalık, 1, 2 ve 4 saatlik barları birlikte okur, beş farklı al-sat motorunun oylarını
birleştirir ve sonuçları günlük / haftalık / aylık / yıllık kâr tablolarında gösterir.

> Gerçek emir göndermez, aracı kurumunuza bağlanmaz. Yatırım tavsiyesi değildir.

---

## 1. Kurulum (bir kez)

1. Bu klasörü istediğiniz yere koyun (ör. Masaüstü).
2. **BASLAT.bat** dosyasına çift tıklayın.
   - Bilgisayarda Python 3.8+ yoksa pencere bunu söyler ve `winget` ile otomatik kurmayı önerir.
     Elle kurmak isterseniz: https://www.python.org/downloads/ (kurulumda **Add python.exe to PATH** işaretli olsun).
   - Başka hiçbir kütüphane gerekmez; program yalnız Python'un kendi modülleriyle çalışır.
3. Tarayıcıda panel açılır: **http://127.0.0.1:8765**

İsteğe bağlı: **BORSAPY_KUR.bat** ile `borsapy` kütüphanesini kurarsanız ikinci bir veri kaynağı açılır.
**VERI_TESTI.bat** veri bağlantısını dener.

## 2. İlk kullanım: sermaye ve komisyon

Panelin üstünde iki mod var:

| Mod | Ne yapar |
|---|---|
| **Canlı sanal işlem** | Sizin belirlediğiniz sanal sermayeyle *bugünden itibaren* gerçek BIST verisiyle al-sat yapar. Program açık kaldığı sürece seans saatlerinde 5 dakikada bir yeni barları işler. Kapatıp açtığınızda kaldığı yerden devam eder; kapalıyken kaçırdığı barları da sırayla işler. |
| **Geçmiş simülasyon** | Son 2–3 yılın gerçek verisini baştan oynatır; robot o günlerde çalışıyormuş gibi işlem yapar. Tablolar hemen dolar. |

İlk açılışta ekranda **Sanal sermaye (₺)**, **Komisyon (binde)** ve **%5 BSMV** kutuları çıkar.
Değerleri girip *Başlat*'a basmanız yeterli. Tüm diğer ayarlar **Ayarlar** sekmesindedir.

Komisyon örneği: binde 1,5 + BSMV → 100.000 ₺'lik alışta 157,50 ₺, al-sat turunda 315 ₺.
Komisyon hem alışta hem satışta, işlem tutarı üzerinden alınır. Kayma (varsayılan %0,05) emrin
aleyhte bir fiyattan gerçekleşmesini taklit eder.

## 3. Panel

* **Anlık durum** (en üstte) — açık pozisyonlar, anlık kâr/zararları ve stop seviyeleri, bekleyen emirler ve son işlemler.
* **Fiyatlar ve takip** — robotun izlediği tüm hisselerin son fiyatı, günlük değişimi, gün aralığı, hacmi ve robot skoru.
  Kendi **takip listenize** istediğiniz hisseyi (Yakın İzleme Pazarı dahil) ekleyebilirsiniz; bu liste yalnız bilgi
  amaçlıdır, robotun portföyüne kaydedilmez ve al-sat kararlarını etkilemez. Sekme açıkken takip listesi dakikada bir yenilenir.
* **Kazançlar** — tek menüde Günlük / Haftalık / Aylık / Yıllık kâr tablosu. Bir satıra dokununca ayrıntısı açılır
  (hafta ve ay → günler, yıl → aylar, gün → o günün işlemleri). En altta tüm dönemin toplamı.

Her satırda: başlangıç varlık, bitiş varlık, kâr/zarar (₺ ve %), gerçekleşen kâr, ödenen komisyon,
işlem sayısı, kazanan/kaybeden işlem. Kâr/zarar her zaman **komisyon düşülmüş net** rakamdır;
gün sonu varlığı açık pozisyonları o günün kapanış fiyatıyla değerler.

## 4. Hangi hisseler?

Varsayılan: **Borsa İstanbul'daki tüm paylar, Yakın İzleme Pazarı (YİP) hariç.** Program her gün KAP'tan
Yıldız, Ana ve Alt Pazar listelerini alır, YİP'teki payları çıkarır, TradingView taramasından son 30 günlük
ortalama işlem hacmini okur ve günlük hacmi 10 milyon TL'yi geçenlerin **en likit 120 tanesini** izler.
Bu iki sayı Ayarlar'dan değiştirilebilir (en fazla 600). Sığ hisseler, 15 dakikalık barları boşluklu olduğu
ve sanal dolumları gerçekçi olmadığı için alınmaz. KAP'a ulaşılamazsa programın içindeki 25.11.2026 tarihli
liste kullanılır. İsterseniz Ayarlar → Hisse evreni → “Yalnız aşağıdaki liste” ile kendi listenizi verebilirsiniz.

## 5. Veri nereden geliyor?

| Kaynak | Açıklama |
|---|---|
| **Yahoo Finance** (varsayılan) | Ek kurulum istemez. BIST verisi ~15 dk gecikmelidir. 15 dakikalık barlar son ~60 işlem günü, 1 saatlik barlar ~2-3 yıl geriye gider. |
| **borsapy** (isteğe bağlı) | Borsa MCP'nin arkasındaki kütüphane (TradingView kaynaklı). `BORSAPY_KUR.bat` ile kurulur; Ayarlar → Veri kaynağı. |

**Borsa MCP neden doğrudan kullanılmadı?** Borsa MCP, Claude'un sohbet içinde veri çekmesi için
yapılmış bir bağlayıcıdır. Her 15 dakikada bir kendi kendine çalışması gereken bir robotun her adımda
Claude'a bağlanması gerekmez: robot, Borsa MCP'nin kullandığı aynı `borsapy` kütüphanesini (ya da
Yahoo'yu) doğrudan kullanır. Borsa MCP'yi ayrıca Claude'a bağlayıp hisseler hakkında sohbet edebilirsiniz.

2 ve 4 saatlik barlar 1 saatlik barlardan, BIST seansına hizalı olarak üretilir
(09:30–11:30, 11:30–13:30, … ve 09:30–13:30, 13:30–18:10).

## 6. Robot nasıl karar veriyor?

### Beş motor (piyasada kullanılan iki büyük ailenin temsilcileri)

| Motor | Aile | Nasıl kâr eder |
|---|---|---|
| Trend (EMA 20/50 + ADX) | Trend | Az sayıda büyük trendi uzun süre taşır, kaybedenleri erken keser. İsabet düşük, kazanç/kayıp oranı yüksek. |
| Supertrend (ATR 10×3) | Trend | Oynaklığa göre genişleyip daralan bir bantla yön belirler. |
| Kırılım / Kaplumbağa (Donchian 20/10) | Trend | 20 barın zirvesini aşan hisseyi alır, 10 barın dibini kıranı satar (Turtle kuralları). |
| Momentum (MACD + ROC) | Trend | Hızlanan harekete katılır, ivme bitince çıkar. |
| Ortalamaya Dönüş (RSI-2 + Bollinger) | Dönüş | Yükseliş trendindeki hissenin panik düşüşlerini alır. İsabet yüksek, kazançlar küçük; trend motorlarının zarar ettiği yatay piyasada dengeler. |

Piyasa yapıcılık ve yüksek frekanslı işlem (HFT) gibi motorlar alış-satış makasından ve milisaniyelik
fiyat farklarından kazanır; bunlar borsaya ortak yerleşim ve derinlik verisi gerektirir, 15 dakika
gecikmeli veriyle yapılamaz. Bu yüzden robotta yer almazlar.

### Konsey

* Her motor her zaman diliminde −1 (sat) ile +1 (al) arasında oy verir.
* Zaman dilimi ağırlıkları: 4s %35 · 2s %25 · 1s %25 · 15dk %15 (büyük resim yönü, küçük resim zamanlamayı belirler).
* **Adaptif ağırlık:** her motor aynı sermayeyle kendi “gölge portföyünde” de işlem yapar. Son 20 işlem
  gününde iyi giden motorun Konsey'deki oyu artar (yarısı her zaman eşit dağıtılır, aşırı uyum olmasın diye).
* **Al:** Konsey skoru ≥ +0,30 **ve** hissenin 4 saatlik fiyatı EMA50 üstünde **ve** BIST100 düşüş trendinde değilse.
* **Sat:** skor ≤ −0,10 ya da stop.
* Yalnız alım yönlü işlem yapar (açığa satış yok).

### Risk yönetimi

* Lot büyüklüğü: stop olursa özkaynağın en fazla %1'i kaybedilecek şekilde (4 saatlik ATR'ye göre), tek hissede en fazla %20.
* İlk stop: giriş − 2 × ATR. İz süren stop: en yüksek kapanış − 3 × ATR. 1,5 ATR kâra geçince stop başabaşa çekilir.
  (Testlerde 1 saatlik ATR ile kurulan sıkı stoplar işlem sayısını ve komisyonu 2–3 kat artırdı; bu yüzden varsayılan 4 saatlik ATR'dir.)
* Aynı anda en fazla 5 pozisyon. Günde %3 zarar edilirse o gün yeni alım yapılmaz. Stop olan hisseye aynı gün tekrar girilmez.
* Emirler sinyalin geldiği barın kapanışında verilir ve **bir sonraki barın açılışında** gerçekleşir
  (geleceği görme hatası olmasın diye). Oluşmakta olan bar hiçbir zaman kullanılmaz.

## 7. Dosyalar

```
BIST_Robot/
  BASLAT.bat         programı ve paneli açar
  VERI_TESTI.bat     veri kaynağını dener
  BORSAPY_KUR.bat    isteğe bağlı borsapy kurulumu
  bist_robot.py      ana program (python bist_robot.py --simulasyon 365 ile konsoldan simülasyon)
  ayarlar.json       ayarlarınız (ilk çalıştırmada oluşur)
  robot/             motorlar, sanal aracı kurum, veri katmanı, panel
  veri/              önbellek, canlı portföy durumu, simülasyon sonucu, robot.log
```

Canlı portföyü sıfırlamak için: Ayarlar → *Kaydet ve canlı sanal işlemi sıfırdan başlat*.

## 8. Bilmeniz gerekenler

* **Hiçbir motor kâr garantisi vermez.** Geçmiş simülasyonda iyi görünen ayarlar gelecekte aynı sonucu vermeyebilir.
  Ayarları geçmişe göre çok sık değiştirip “en iyi” sonucu aramak (aşırı uyum) en yaygın hatadır.
* **Komisyon belirleyicidir.** Sık işlem yapan bir robotta komisyon yıllık getirinin önemli kısmını yiyebilir;
  Motorlar sekmesindeki “Ödenen komisyon” rakamını mutlaka izleyin.
* Yahoo verisi ~15 dk gecikmelidir; canlı mod “gerçek zamanlı” değil, gecikmeli gerçek veriyle çalışır.
* Temettüler hesaba katılmaz. Bedelsiz/bölünmelerde canlı portföydeki adet ve fiyatlar otomatik düzeltilir.
* Program kapalıyken canlı portföy işlem yapmaz; açıldığında aradaki barları sırayla işleyerek yetişir.

## 9. Sorun giderme

| Sorun | Çözüm |
|---|---|
| Panel açılmadı | Tarayıcıda http://127.0.0.1:8765 adresini elle açın. |
| “Port kullanımda” | Program zaten açık; mevcut pencereyi kullanın ya da `python bist_robot.py --port 9000`. |
| Veri alınamıyor | `VERI_TESTI.bat` çalıştırın. Kurum ağı Yahoo'yu engelliyorsa `BORSAPY_KUR.bat` ile borsapy'yi kurup Ayarlar'dan kaynağı değiştirin. |
| Bir hisse için “veri alınamadı” | Kod değişmiş olabilir (ör. endeks dönemi). Ayarlar → Hisseler listesinden çıkarın. |
