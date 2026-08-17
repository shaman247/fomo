import SwiftUI
import WebKit

struct WebViewContainer: View {
    @State private var isFirstLoad = true
    @State private var error: Error?

    var body: some View {
        ZStack {
            FomoWebView(
                isFirstLoad: $isFirstLoad,
                error: $error
            )

            // Loading overlay (only on first load)
            if isFirstLoad && error == nil {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.5)
                    Text("Loading fomo.nyc...")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.systemBackground))
            }

            // Error state
            if let error = error {
                VStack(spacing: 16) {
                    Image(systemName: "wifi.slash")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("Unable to load")
                        .font(.headline)
                    Text(error.localizedDescription)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                    Button("Try Again") {
                        self.error = nil
                        NotificationCenter.default.post(name: .reloadWebView, object: nil)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.systemBackground))
            }
        }
    }
}

// MARK: - WKWebView Wrapper

struct FomoWebView: UIViewRepresentable {
    @Binding var isFirstLoad: Bool
    @Binding var error: Error?

    private let fomoURL: URL = {
        #if DEBUG
        // Screenshot/dev override — launch with a deep-link URL, e.g.:
        //   xcrun simctl launch <udid> fomocity.fomo -fomoURL 'https://fomo.nyc?tags=Music&zoom=13'
        // Only fomo.nyc URLs are honored; Release builds compile this out.
        // Read from raw arguments, not UserDefaults — values starting with "(" or
        // "{" get plist-parsed by the argument domain and come back nil.
        if let override = FomoWebView.launchArg("fomoURL"),
           let url = URL(string: override), url.host?.contains("fomo.nyc") == true {
            return url
        }
        #endif
        return URL(string: "https://fomo.nyc")!
    }()

    #if DEBUG
    static func launchArg(_ name: String) -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let i = args.firstIndex(of: "-\(name)"), i + 1 < args.count else { return nil }
        return args[i + 1]
    }
    #endif

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.allowsInlineMediaPlayback = true
        configuration.preferences.isElementFullscreenEnabled = true

        // Required (together with WKAppBoundDomains in Info.plist) for Service
        // Worker support — the site's offline cache. Restricts main-frame
        // navigation to fomo.nyc; the navigation delegate below sends external
        // links to Safari, which it did already.
        configuration.limitsNavigationsToAppBoundDomains = true

        // Performance optimizations
        configuration.suppressesIncrementalRendering = false  // Render as content loads
        configuration.allowsAirPlayForMediaPlayback = false   // Disable unused features

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        #if DEBUG
        // Safari Develop-menu inspection (service worker / IndexedDB state).
        webView.isInspectable = true
        #endif
        webView.allowsBackForwardNavigationGestures = true

        // GPU/rendering optimizations
        webView.isOpaque = true                               // Enables compositing optimizations
        webView.scrollView.bounces = false                    // Reduce compositing overhead
        // Never let the scroll view add its own safe-area content insets — the
        // page is edge-to-edge (see .ignoresSafeArea() in FomoApp) and manages
        // insets itself via CSS env(safe-area-inset-*). .automatic would stack a
        // second top inset on top of the CSS padding.
        webView.scrollView.contentInsetAdjustmentBehavior = .never

        // Prevent zoom but allow scrolling
        webView.scrollView.maximumZoomScale = 1.0
        webView.scrollView.minimumZoomScale = 1.0

        // Reduce unnecessary redraws
        webView.scrollView.decelerationRate = .normal

        // Set mobile viewport
        webView.customUserAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 FomoApp/1.0"

        // Listen for reload notifications
        NotificationCenter.default.addObserver(
            forName: .reloadWebView,
            object: nil,
            queue: .main
        ) { _ in
            webView.load(URLRequest(url: fomoURL))
        }

        // Initial load
        webView.load(URLRequest(url: fomoURL))

        #if DEBUG
        // Screenshot/dev hook — force an orientation, e.g.:
        //   xcrun simctl launch <udid> fomocity.fomo -fomoOrientation landscape
        // simctl has no rotate command; this rotates the scene from inside.
        if let orientation = FomoWebView.launchArg("fomoOrientation") {
            // The request is racily rejected ("windowing mode does not allow")
            // right after launch on iOS 26 simulators — keep retrying until the
            // scene actually reports the wanted orientation.
            var ticks = 0
            Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { timer in
                ticks += 1
                guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene else { return }
                let wantLandscape = orientation == "landscape"
                if scene.interfaceOrientation.isLandscape == wantLandscape || ticks > 30 {
                    NSLog("fomoOrientation: settled at \(scene.interfaceOrientation.rawValue) after \(ticks)s")
                    timer.invalidate()
                    return
                }
                let mask: UIInterfaceOrientationMask = wantLandscape ? .landscapeRight : .portrait
                scene.requestGeometryUpdate(.iOS(interfaceOrientations: mask)) { error in
                    NSLog("fomoOrientation: geometry update rejected: \(error)")
                }
                scene.keyWindow?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
            }
        }
        #endif

        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        // No updates needed
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var parent: FomoWebView

        init(_ parent: FomoWebView) {
            self.parent = parent
        }

        // MARK: - WKNavigationDelegate

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isFirstLoad = false
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isFirstLoad = false
                self.parent.error = nil
            }
            #if DEBUG
            // Screenshot/dev hook — run JS a few seconds after load, e.g.:
            //   xcrun simctl launch <udid> fomocity.fomo -fomoJS "document.querySelector('.maplibregl-marker')?.click()"
            // Release builds compile this out.
            if let js = FomoWebView.launchArg("fomoJS") {
                DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
                    webView.evaluateJavaScript(js, completionHandler: nil)
                }
            }
            #endif
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            // Cancellations (e.g. our own .cancel → open-in-Safari path) are
            // not failures — never flash the error screen for them.
            if (error as NSError).code == NSURLErrorCancelled { return }
            DispatchQueue.main.async {
                if self.parent.isFirstLoad {
                    self.parent.error = error
                }
            }
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            if (error as NSError).code == NSURLErrorCancelled { return }
            DispatchQueue.main.async {
                if self.parent.isFirstLoad {
                    self.parent.error = error
                }
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }

            // Allow fomo.nyc navigation
            if url.host?.contains("fomo.nyc") == true {
                decisionHandler(.allow)
                return
            }

            // Open ANY external main-frame navigation in Safari — not just
            // tapped links but also JS-driven redirects (ticket vendors etc.),
            // which limitsNavigationsToAppBoundDomains would otherwise hard-fail
            // with an in-webview error page.
            if navigationAction.targetFrame?.isMainFrame != false,
               let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }

            // Cross-origin iframes and non-http schemes handled by the system.
            decisionHandler(.allow)
        }

        // MARK: - WKUIDelegate

        func webView(
            _ webView: WKWebView,
            createWebViewWith configuration: WKWebViewConfiguration,
            for navigationAction: WKNavigationAction,
            windowFeatures: WKWindowFeatures
        ) -> WKWebView? {
            guard let url = navigationAction.request.url else { return nil }

            if url.host?.contains("fomo.nyc") == true {
                webView.load(navigationAction.request)
            } else {
                UIApplication.shared.open(url)
            }

            return nil
        }

        func webView(
            _ webView: WKWebView,
            runJavaScriptAlertPanelWithMessage message: String,
            initiatedByFrame frame: WKFrameInfo,
            completionHandler: @escaping () -> Void
        ) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in
                completionHandler()
            })

            if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
               let viewController = windowScene.windows.first?.rootViewController {
                viewController.present(alert, animated: true)
            } else {
                completionHandler()
            }
        }

        func webView(
            _ webView: WKWebView,
            requestMediaCapturePermissionFor origin: WKSecurityOrigin,
            initiatedByFrame frame: WKFrameInfo,
            type: WKMediaCaptureType,
            decisionHandler: @escaping (WKPermissionDecision) -> Void
        ) {
            decisionHandler(.prompt)
        }
    }
}

// MARK: - Notification Extension

extension Notification.Name {
    static let reloadWebView = Notification.Name("reloadWebView")
}

#Preview {
    WebViewContainer()
}
