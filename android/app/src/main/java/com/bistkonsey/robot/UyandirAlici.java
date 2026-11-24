package com.bistkonsey.robot;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/** Seans başlangıcı alarmı: servisi uyandırır (servis kapanmışsa yeniden başlatmayı dener). */
public class UyandirAlici extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        RobotService s = RobotService.ornek;
        if (s != null) {
            s.oturumKontrol();
            return;
        }
        try {
            context.startForegroundService(new Intent(context, RobotService.class));
        } catch (Throwable t) {
            Log.w(RobotService.TAG, "Servis arka planda başlatılamadı; uygulama açılınca başlayacak", t);
        }
    }
}
