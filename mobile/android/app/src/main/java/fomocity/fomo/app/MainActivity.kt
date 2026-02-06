package fomocity.fomo.app

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import fomocity.fomo.app.ui.theme.FomoTheme

class MainActivity : ComponentActivity() {
    private var webView: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            FomoTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    FomoWebViewScreen(
                        onWebViewCreated = { webView = it },
                        onBackPressedDispatcher = onBackPressedDispatcher
                    )
                }
            }
        }

        // Handle back button
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView?.canGoBack() == true) {
                    webView?.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }
}

@Composable
fun FomoWebViewScreen(
    onWebViewCreated: (WebView) -> Unit,
    onBackPressedDispatcher: androidx.activity.OnBackPressedDispatcher
) {
    var isLoading by remember { mutableStateOf(true) }
    var hasError by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf("") }
    var webViewInstance by remember { mutableStateOf<WebView?>(null) }

    Box(modifier = Modifier.fillMaxSize()) {
        // WebView with SwipeRefresh
        FomoWebView(
            url = BuildConfig.BASE_URL,
            onWebViewCreated = { webView ->
                webViewInstance = webView
                onWebViewCreated(webView)
            },
            onPageStarted = {
                isLoading = true
                hasError = false
            },
            onPageFinished = {
                isLoading = false
            },
            onError = { error ->
                isLoading = false
                hasError = true
                errorMessage = error
            },
            modifier = Modifier.fillMaxSize()
        )

        // Loading overlay
        if (isLoading && !hasError) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator()
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Loading fomo.nyc...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        // Error state
        if (hasError) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(32.dp)
                ) {
                    Icon(
                        painter = painterResource(id = android.R.drawable.ic_dialog_alert),
                        contentDescription = "Error",
                        modifier = Modifier.size(48.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Unable to load",
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = errorMessage,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(24.dp))
                    Button(onClick = {
                        hasError = false
                        isLoading = true
                        webViewInstance?.reload()
                    }) {
                        Text("Try Again")
                    }
                }
            }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun FomoWebView(
    url: String,
    onWebViewCreated: (WebView) -> Unit,
    onPageStarted: () -> Unit,
    onPageFinished: () -> Unit,
    onError: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current

    AndroidView(
        factory = { ctx ->
            SwipeRefreshLayout(ctx).apply {
                // Create WebView
                val webView = WebView(ctx).apply {
                    // Enable hardware acceleration for WebGL (MapLibre maps)
                    setLayerType(View.LAYER_TYPE_HARDWARE, null)

                    settings.apply {
                        javaScriptEnabled = true
                        domStorageEnabled = true
                        databaseEnabled = true
                        setSupportZoom(false)
                        builtInZoomControls = false
                        displayZoomControls = false
                        loadWithOverviewMode = true
                        useWideViewPort = true
                        userAgentString = "$userAgentString FomoApp/1.0"

                        // Required for proper CSS rendering (fixed positioning, modals)
                        @Suppress("DEPRECATION")
                        mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE

                        // Enable modern web features
                        mediaPlaybackRequiresUserGesture = false
                        javaScriptCanOpenWindowsAutomatically = true
                    }

                    webViewClient = object : WebViewClient() {
                        override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                            super.onPageStarted(view, url, favicon)
                            onPageStarted()
                        }

                        override fun onPageFinished(view: WebView?, url: String?) {
                            super.onPageFinished(view, url)
                            onPageFinished()
                            // Stop swipe refresh animation
                            (parent as? SwipeRefreshLayout)?.isRefreshing = false

                            // Get status bar height for safe area inset
                            val statusBarHeight = view?.rootWindowInsets?.let { insets ->
                                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                                    insets.getInsets(android.view.WindowInsets.Type.statusBars()).top
                                } else {
                                    @Suppress("DEPRECATION")
                                    insets.systemWindowInsetTop
                                }
                            } ?: 0

                            // Fix viewport height for Android WebView
                            // 100vh is unreliable in WebViews - set --app-height CSS variable
                            // Also set --safe-area-top for status bar padding
                            view?.evaluateJavascript("""
                                (function() {
                                    var safeAreaTop = $statusBarHeight;
                                    function setAppHeight() {
                                        var vh = window.innerHeight;
                                        console.log('DEBUG: Setting --app-height to ' + vh + 'px, --safe-area-top to ' + safeAreaTop + 'px');
                                        document.documentElement.style.setProperty('--app-height', vh + 'px');
                                        document.documentElement.style.setProperty('--safe-area-top', safeAreaTop + 'px');

                                        // Debug: check filter panel
                                        var filterPanel = document.getElementById('filter-panel');
                                        if (filterPanel) {
                                            var style = window.getComputedStyle(filterPanel);
                                            var rect = filterPanel.getBoundingClientRect();
                                            console.log('DEBUG: filter-panel rect: ' + JSON.stringify({
                                                width: rect.width,
                                                height: rect.height,
                                                top: rect.top,
                                                left: rect.left
                                            }));
                                            console.log('DEBUG: filter-panel computed: ' +
                                                'height=' + style.height +
                                                ', maxHeight=' + style.maxHeight +
                                                ', display=' + style.display +
                                                ', visibility=' + style.visibility +
                                                ', opacity=' + style.opacity);
                                        } else {
                                            console.log('DEBUG: filter-panel NOT FOUND');
                                        }

                                        // Debug: check map
                                        var map = document.getElementById('map');
                                        if (map) {
                                            var mapRect = map.getBoundingClientRect();
                                            console.log('DEBUG: map rect: ' + JSON.stringify({
                                                width: mapRect.width,
                                                height: mapRect.height
                                            }));
                                        }
                                    }

                                    // Run immediately and on resize
                                    setAppHeight();
                                    window.addEventListener('resize', setAppHeight);

                                    // Run again after delays to catch late layout changes
                                    setTimeout(setAppHeight, 100);
                                    setTimeout(setAppHeight, 500);
                                    setTimeout(setAppHeight, 1000);

                                    return 'Viewport fix applied';
                                })();
                            """.trimIndent(), null)
                        }

                        override fun onReceivedError(
                            view: WebView?,
                            request: WebResourceRequest?,
                            error: WebResourceError?
                        ) {
                            super.onReceivedError(view, request, error)
                            // Only show error for main frame
                            if (request?.isForMainFrame == true) {
                                onError(error?.description?.toString() ?: "Unknown error")
                            }
                        }

                        override fun shouldOverrideUrlLoading(
                            view: WebView?,
                            request: WebResourceRequest?
                        ): Boolean {
                            val requestUrl = request?.url?.toString() ?: return false

                            // Allow fomo.nyc and local dev server navigation within WebView
                            val baseUrl = BuildConfig.BASE_URL
                            if (requestUrl.contains("fomo.nyc") || requestUrl.startsWith(baseUrl)) {
                                return false
                            }

                            // Open external links in browser
                            try {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(requestUrl)))
                            } catch (e: Exception) {
                                // Handle case where no browser is available
                            }
                            return true
                        }
                    }

                    webChromeClient = object : WebChromeClient() {
                        override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                            Log.d("FomoWebView", "${consoleMessage?.messageLevel()}: ${consoleMessage?.message()} [${consoleMessage?.sourceId()}:${consoleMessage?.lineNumber()}]")
                            return true
                        }
                    }

                    // Load the URL
                    loadUrl(url)
                }

                addView(webView)
                onWebViewCreated(webView)

                // Disable pull-to-refresh (can interfere with map scrolling)
                isEnabled = false
            }
        },
        modifier = modifier
    )
}
