package com.bistkonsey.robot;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** Paneli (Python robotunun yerel web sunucusu) tam ekran gösterir. */
public class MainActivity extends Activity {
    private WebView web;
    private final Handler h = new Handler(Looper.getMainLooper());
    private boolean yuklendi = false;
    private int deneme = 0;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.parseColor("#F4F3EF"));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);

        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
        startForegroundService(new Intent(this, RobotService.class));

        web = new WebView(this);
        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setCacheMode(WebSettings.LOAD_NO_CACHE);
        ws.setTextZoom(100);
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if ("127.0.0.1".equals(u.getHost()) || "localhost".equals(u.getHost())) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, u));
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    yuklendi = false;
                    h.postDelayed(MainActivity.this::yukle, 800);
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (url != null && url.startsWith("http://127.0.0.1")) {
                    yuklendi = true;
                    pilIzniSor();
                }
            }
        });
        bekleniyor("Robot başlatılıyor…", "İlk açılış birkaç saniye sürebilir.");
        setContentView(web);
        h.postDelayed(this::yukle, 400);
    }

    private void bekleniyor(String baslik, String alt) {
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                + "<body style='margin:0;height:100vh;display:flex;align-items:center;justify-content:center;"
                + "background:#f4f3ef;font-family:sans-serif;color:#0b0b0b;text-align:center'><div>"
                + "<div style='font-size:18px;font-weight:600'>" + baslik + "</div>"
                + "<div style='color:#52514e;margin-top:8px;font-size:14px;padding:0 24px'>" + alt + "</div>"
                + "</div></body></html>";
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    private void yukle() {
        if (isFinishing() || yuklendi) return;
        if (RobotService.hata != null) {
            bekleniyor("Robot başlatılamadı", RobotService.hata);
            return;
        }
        if (!RobotService.hazir) {
            deneme++;
            h.postDelayed(this::yukle, 500);
            return;
        }
        web.loadUrl("http://127.0.0.1:" + RobotService.port + "/");
    }

    /** Telefon uykudayken robotun internete çıkabilmesi için pil kısıtlamasından muaf tutulmayı bir kez iste. */
    private void pilIzniSor() {
        SharedPreferences sp = getSharedPreferences("ayar", MODE_PRIVATE);
        if (sp.getBoolean("pil_soruldu", false)) return;
        sp.edit().putBoolean("pil_soruldu", true).apply();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
            h.postDelayed(() -> {
                try {
                    @SuppressLint("BatteryLife")
                    Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:" + getPackageName()));
                    startActivity(i);
                } catch (Exception ignored) {
                }
            }, 1500);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        RobotService s = RobotService.ornek;
        if (s != null) s.zorlaAsenkron();
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            moveTaskToBack(true); // robot arka planda çalışmaya devam eder
        }
    }
}
