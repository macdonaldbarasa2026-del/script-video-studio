package studio.scriptvideo.app;

import android.app.Activity;
import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Toast;

import java.io.OutputStream;
import java.util.Base64;

public class MainActivity extends Activity {
    private static final String DEFAULT_SERVICE_URL = "https://script-video-studio.onrender.com";
    private EditText serviceUrl;
    private WebView webView;
    private String connectedHost = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildScreen();
        String saved = getPreferences(MODE_PRIVATE).getString("serviceUrl", DEFAULT_SERVICE_URL);
        serviceUrl.setText(saved);
        connect(saved);
    }

    private void buildScreen() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(16, 16, 16, 0);

        LinearLayout toolbar = new LinearLayout(this);
        serviceUrl = new EditText(this);
        serviceUrl.setSingleLine(true);
        serviceUrl.setHint("https://your-service.onrender.com");
        serviceUrl.setTextSize(14);
        toolbar.addView(serviceUrl, new LinearLayout.LayoutParams(0, 52, 1));

        Button connect = new Button(this);
        connect.setText("Connect");
        connect.setOnClickListener(view -> connect(serviceUrl.getText().toString().trim()));
        toolbar.addView(connect, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, 52));
        root.addView(toolbar);

        webView = new WebView(this);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new VideoBridge(), "VideoStudio");
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                if (target.getHost() != null && target.getHost().equals(connectedHost)) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, target));
                return true;
            }
        });
        root.addView(webView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
    }

    private void connect(String value) {
        Uri uri = Uri.parse(value);
        if (!"https".equals(uri.getScheme()) || uri.getHost() == null) {
            Toast.makeText(this, "Enter your HTTPS Render service URL.", Toast.LENGTH_LONG).show();
            return;
        }
        String normalized = value.replaceAll("/+$", "");
        connectedHost = uri.getHost();
        serviceUrl.setText(normalized);
        getPreferences(MODE_PRIVATE).edit().putString("serviceUrl", normalized).apply();
        webView.loadUrl(normalized);
    }

    private final class VideoBridge {
        @JavascriptInterface
        public void saveVideo(String dataUrl, String fileName) {
            new Thread(() -> {
                try {
                    int comma = dataUrl.indexOf(',');
                    if (comma < 0) throw new IllegalArgumentException("Invalid video data");
                    byte[] bytes = Base64.getDecoder().decode(dataUrl.substring(comma + 1));
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
                    values.put(MediaStore.MediaColumns.MIME_TYPE, "video/mp4");
                    values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    Uri item = getContentResolver().insert(
                            MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (item == null) throw new IllegalStateException("Could not create download");
                    try (OutputStream output = getContentResolver().openOutputStream(item)) {
                        if (output == null) throw new IllegalStateException("Could not write download");
                        output.write(bytes);
                    }
                    showSaveMessage("Saved to Downloads.");
                } catch (Exception exception) {
                    showSaveMessage("Could not save video: " + exception.getMessage());
                }
            }).start();
        }

        private void showSaveMessage(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_LONG).show());
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
