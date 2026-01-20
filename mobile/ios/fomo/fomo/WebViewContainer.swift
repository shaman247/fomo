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

    private let fomoURL = URL(string: "https://fomo.nyc")!

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.allowsInlineMediaPlayback = true
        configuration.preferences.isElementFullscreenEnabled = true

        // Performance optimizations
        configuration.suppressesIncrementalRendering = false  // Render as content loads
        configuration.allowsAirPlayForMediaPlayback = false   // Disable unused features

        // Share process pool across instances for better memory management
        configuration.processPool = WKProcessPool()

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true

        // GPU/rendering optimizations
        webView.isOpaque = true                               // Enables compositing optimizations
        webView.scrollView.bounces = false                    // Reduce compositing overhead
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic

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
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            DispatchQueue.main.async {
                if self.parent.isFirstLoad {
                    self.parent.error = error
                }
            }
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
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

            // Open external links in Safari
            if navigationAction.navigationType == .linkActivated {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }

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
