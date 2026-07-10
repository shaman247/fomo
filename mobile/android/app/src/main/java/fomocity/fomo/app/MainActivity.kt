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
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
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

                            view?.let { injectViewportVars(it) }
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
                            if (BuildConfig.DEBUG) {
                                Log.d("FomoWebView", "${consoleMessage?.messageLevel()}: ${consoleMessage?.message()} [${consoleMessage?.sourceId()}:${consoleMessage?.lineNumber()}]")
                            }
                            return true
                        }
                    }

                    // Load the URL
                    loadUrl(url)
                }

                // Re-publish the inset CSS variables whenever the system bar
                // insets change (rotation, gesture vs 3-button nav switch)
                ViewCompat.setOnApplyWindowInsetsListener(webView) { v, insets ->
                    injectViewportVars(v as WebView)
                    insets
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

// The page can't measure system bars itself — env(safe-area-inset-*) is always
// 0 inside an Android WebView — so read the insets natively and hand them to
// the page as CSS variables. Insets are physical pixels; CSS px are
// density-scaled, so divide by density first. --app-height works around 100vh
// being unreliable in WebViews.
private fun injectViewportVars(webView: WebView) {
    val insets = ViewCompat.getRootWindowInsets(webView)?.getInsets(
        WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
    )
    val density = webView.resources.displayMetrics.density
    val safeAreaTop = kotlin.math.ceil((insets?.top ?: 0) / density).toInt()
    val safeAreaBottom = kotlin.math.ceil((insets?.bottom ?: 0) / density).toInt()

    webView.evaluateJavascript("""
        (function() {
            document.documentElement.style.setProperty('--safe-area-top', '${safeAreaTop}px');
            document.documentElement.style.setProperty('--safe-area-bottom', '${safeAreaBottom}px');
            function setAppHeight() {
                document.documentElement.style.setProperty('--app-height', window.innerHeight + 'px');
            }
            setAppHeight();
            if (!window.__appHeightHooked) {
                window.__appHeightHooked = true;
                window.addEventListener('resize', setAppHeight);
            }
            // Run again after delays to catch late layout changes
            setTimeout(setAppHeight, 100);
            setTimeout(setAppHeight, 500);
            setTimeout(setAppHeight, 1000);
        })();
    """.trimIndent(), null)
}
