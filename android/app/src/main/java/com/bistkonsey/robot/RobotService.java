package com.bistkonsey.robot;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Calendar;
import java.util.TimeZone;

/**
 * Python robotunu (aynı masaüstü kodu) ön planda çalıştıran servis.
 * Seans saatlerinde (hafta içi 09:35–18:45, İstanbul) işlemciyi uyanık tutar;
 * seans dışında bırakır ve bir sonraki seans başlangıcı için alarm kurar.
 */
public class RobotService extends Service {
    static final String TAG = "BISTKonsey";
    static final String KANAL = "robot";
    static final String EYLEM_KAPAT = "com.bistkonsey.robot.KAPAT";
    static final int BILDIRIM_ID = 1;

    static volatile boolean hazir = false;
    static volatile int port = 8765;
    static volatile String hata = null;
    static volatile RobotService ornek = null;

    private PowerManager.WakeLock uyanik;
    private HandlerThread isParcacigi;
    private Handler isleyici;
    private PyObject giris;

    private final Runnable kontrol = new Runnable() {
        @Override
        public void run() {
            oturumKontrol();
            if (isleyici != null) isleyici.postDelayed(this, 60_000);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        ornek = this;
        kanalOlustur();
        Notification n = bildirim("Robot başlatılıyor…");
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(BILDIRIM_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(BILDIRIM_ID, n);
        }
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        uyanik = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "BISTKonsey::seans");
        uyanik.setReferenceCounted(false);

        isParcacigi = new HandlerThread("robot-kontrol");
        isParcacigi.start();
        isleyici = new Handler(isParcacigi.getLooper());
        isleyici.post(this::pythonBaslat);
    }

    private void pythonBaslat() {
        try {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
            File kok = new File(getFilesDir(), "robot");
            if (!kok.exists() && !kok.mkdirs()) throw new RuntimeException("Klasör oluşturulamadı: " + kok);
            File panel = new File(getFilesDir(), "panel.html");
            kopyala("panel.html", panel);
            giris = Python.getInstance().getModule("android_giris");
            port = giris.callAttr("baslat", kok.getAbsolutePath(), panel.getAbsolutePath(), 8765).toInt();
            hazir = true;
            hata = null;
            bildirimGuncelle("Robot çalışıyor · panel: uygulamayı açın");
            Log.i(TAG, "Python robotu hazır, port " + port);
            isleyici.post(kontrol);
        } catch (Throwable t) {
            hata = t.toString();
            Log.e(TAG, "Python başlatılamadı", t);
            bildirimGuncelle("Hata: " + t.getMessage());
        }
    }

    private void kopyala(String varlik, File hedef) throws Exception {
        try (InputStream in = getAssets().open(varlik); OutputStream out = new FileOutputStream(hedef)) {
            byte[] b = new byte[16384];
            int n;
            while ((n = in.read(b)) > 0) out.write(b, 0, n);
        }
    }

    static boolean seansMi(long ms) {
        Calendar c = Calendar.getInstance(TimeZone.getTimeZone("Europe/Istanbul"));
        c.setTimeInMillis(ms);
        int g = c.get(Calendar.DAY_OF_WEEK);
        if (g == Calendar.SATURDAY || g == Calendar.SUNDAY) return false;
        int dk = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE);
        return dk >= 9 * 60 + 35 && dk <= 18 * 60 + 45;
    }

    static long sonrakiSeans(long ms) {
        Calendar c = Calendar.getInstance(TimeZone.getTimeZone("Europe/Istanbul"));
        c.setTimeInMillis(ms);
        c.set(Calendar.HOUR_OF_DAY, 9);
        c.set(Calendar.MINUTE, 40);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        while (c.getTimeInMillis() <= ms || c.get(Calendar.DAY_OF_WEEK) == Calendar.SATURDAY
                || c.get(Calendar.DAY_OF_WEEK) == Calendar.SUNDAY) {
            c.add(Calendar.DAY_OF_MONTH, 1);
        }
        return c.getTimeInMillis();
    }

    /** Seans içindeyse uyanık kal ve robotu dürt; dışındaysa bırak ve sonraki seansa alarm kur. */
    synchronized void oturumKontrol() {
        long simdi = System.currentTimeMillis();
        if (seansMi(simdi)) {
            if (!uyanik.isHeld()) {
                uyanik.acquire();
                zorlaAsenkron();
            }
        } else {
            if (uyanik.isHeld()) uyanik.release();
            alarmKur(sonrakiSeans(simdi));
        }
    }

    /** Python çağrısını ana iş parçacığında değil, servisin kendi iş parçacığında yap. */
    void zorlaAsenkron() {
        Handler hh = isleyici;
        if (hh != null) hh.post(this::zorla);
    }

    void zorla() {
        try {
            if (giris != null) giris.callAttr("zorla_guncelle");
        } catch (Throwable t) {
            Log.w(TAG, "zorla_guncelle", t);
        }
    }

    private void alarmKur(long zaman) {
        AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
        PendingIntent pi = PendingIntent.getBroadcast(this, 0, new Intent(this, UyandirAlici.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, zaman, pi);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && EYLEM_KAPAT.equals(intent.getAction())) {
            kapat();
            return START_NOT_STICKY;
        }
        return START_STICKY;
    }

    private void kapat() {
        try {
            if (giris != null) giris.callAttr("durdur");
        } catch (Throwable ignored) {
        }
        if (uyanik != null && uyanik.isHeld()) uyanik.release();
        stopForeground(true);
        stopSelf();
        // Python iş parçacıklarının tamamen durması için süreci sonlandır
        new Handler(getMainLooper()).postDelayed(() -> android.os.Process.killProcess(android.os.Process.myPid()), 400);
    }

    @Override
    public void onDestroy() {
        if (isParcacigi != null) isParcacigi.quitSafely();
        if (uyanik != null && uyanik.isHeld()) uyanik.release();
        ornek = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    // ------------------------------------------------------------ bildirim
    private void kanalOlustur() {
        NotificationChannel k = new NotificationChannel(KANAL, "Robot durumu", NotificationManager.IMPORTANCE_LOW);
        k.setDescription("BIST Konsey Robotu arka planda çalışırken gösterilir");
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(k);
    }

    private Notification bildirim(String metin) {
        PendingIntent ac = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent kapat = PendingIntent.getService(this, 1,
                new Intent(this, RobotService.class).setAction(EYLEM_KAPAT),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, KANAL)
                .setSmallIcon(R.drawable.ic_bildirim)
                .setContentTitle("BIST Konsey Robotu")
                .setContentText(metin)
                .setContentIntent(ac)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "Robotu kapat", kapat).build())
                .build();
    }

    private void bildirimGuncelle(String metin) {
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(BILDIRIM_ID, bildirim(metin));
    }
}
