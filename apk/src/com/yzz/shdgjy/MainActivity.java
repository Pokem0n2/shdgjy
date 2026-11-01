package com.yzz.shdgjy;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

/**
 * 进出场核验 壳：WebView 全屏加载 http://yzz.cool/shdgjy.html
 * - http 明文（manifest usesCleartextTraffic）
 * - 断网显示本地错误页，可重试
 * - 返回键：无历史时双击退出
 * - blob:/http: 下载（CSV 导出、离线生成文件）落 Downloads
 */
public class MainActivity extends Activity {

    private static final String HOME_URL = "http://yzz.cool/shdgjy.html";

    private WebView web;
    private long lastBack = 0;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.setWebViewClient(new SiteClient());
        web.setWebChromeClient(new WebChromeClient());
        web.setDownloadListener(new SiteDownloadListener());
        web.addJavascriptInterface(new SaveBridge(this), "AndroidSave");
        setContentView(web);
        web.loadUrl(HOME_URL);
    }

    /** 站内链接留在 WebView；其他链接交给系统浏览器 */
    private class SiteClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            String s = u.toString();
            if (s.startsWith("http://yzz.cool") || s.startsWith("file:///android_asset/")) return false;
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (Exception e) {
                Toast.makeText(MainActivity.this, "无法打开链接", Toast.LENGTH_SHORT).show();
            }
            return true;
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                view.loadUrl("file:///android_asset/error.html");
            }
        }
    }

    /** blob: 下载（页面用 URL.createObjectURL 导出 CSV 等）+ 普通下载 */
    private class SiteDownloadListener implements DownloadListener {
        @Override
        public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimetype, long contentLength) {
            String name = URLUtil.guessFileName(url, contentDisposition, mimetype);
            if (name == null || name.length() == 0) name = "shdgjy-download";
            if (url.startsWith("blob:")) {
                // blob 只存在于页面内存中：让页面读出内容，经 AndroidSave 桥送回保存
                String js = "(function(){fetch('" + url + "').then(function(r){return r.blob()})"
                        + ".then(function(b){var fr=new FileReader();"
                        + "fr.onload=function(){AndroidSave.save(" + jsStr(name) + "," + jsStr(mimetype) + ",fr.result)};"
                        + "fr.onerror=function(){AndroidSave.save(" + jsStr(name) + ",null,'')};"
                        + "fr.readAsDataURL(b)})})()";
                web.evaluateJavascript(js, null);
            } else if (url.startsWith("data:")) {
                saveDataUrl(url, name, mimetype);
            } else {
                try {
                    DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                    req.setMimeType(mimetype);
                    req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
                    req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    dm.enqueue(req);
                    toast("已开始下载 " + name);
                } catch (Exception e) {
                    toast("下载失败");
                }
            }
        }
    }

    private static String jsStr(String s) {
        if (s == null) return "null";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    /** 页面 JS 桥：接收 blob 读出的 data: URL 并保存到 Downloads */
    public static class SaveBridge {
        private final MainActivity host;

        public SaveBridge(MainActivity host) {
            this.host = host;
        }

        @JavascriptInterface
        public void save(final String name, final String mime, final String dataUrl) {
            host.runOnUiThread(new SaveRunner(host, name, mime, dataUrl));
        }
    }

    private static class SaveRunner implements Runnable {
        private final MainActivity host;
        private final String name;
        private final String mime;
        private final String dataUrl;

        SaveRunner(MainActivity host, String name, String mime, String dataUrl) {
            this.host = host; this.name = name; this.mime = mime; this.dataUrl = dataUrl;
        }

        @Override
        public void run() {
            if (dataUrl == null || dataUrl.length() == 0) {
                host.toast("下载失败");
                return;
            }
            host.saveDataUrl(dataUrl, name, mime);
        }
    }

    private void saveDataUrl(String dataUrl, String name, String mime) {
        try {
            int comma = dataUrl.indexOf(',');
            if (comma < 0) throw new IllegalArgumentException("bad data url");
            String meta = dataUrl.substring(5, comma);
            if (mime == null || mime.length() == 0 || mime.equals("application/octet-stream")) {
                int semi = meta.indexOf(';');
                if (semi > 0) mime = meta.substring(0, semi);
            }
            byte[] bytes = Base64.decode(dataUrl.substring(comma + 1), Base64.DEFAULT);
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Downloads.DISPLAY_NAME, name);
                if (mime != null && mime.length() > 0) cv.put(MediaStore.Downloads.MIME_TYPE, mime);
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                if (uri == null) throw new IllegalStateException("insert failed");
                OutputStream os = getContentResolver().openOutputStream(uri);
                os.write(bytes);
                os.close();
            } else {
                File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                if (!dir.exists()) dir.mkdirs();
                File f = new File(dir, name);
                FileOutputStream fo = new FileOutputStream(f);
                fo.write(bytes);
                fo.close();
            }
            toast("已保存到 Download/" + name);
        } catch (Exception e) {
            toast("保存失败：" + e.getMessage());
        }
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
            return;
        }
        long now = System.currentTimeMillis();
        if (now - lastBack < 2000) {
            super.onBackPressed();
        } else {
            lastBack = now;
            Toast.makeText(this, "再按一次退出", Toast.LENGTH_SHORT).show();
        }
    }
}
