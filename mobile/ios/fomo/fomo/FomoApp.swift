import SwiftUI

@main
struct FomoApp: App {
    var body: some Scene {
        WindowGroup {
            WebViewContainer()
                // Edge-to-edge on all sides: the map fills behind the status bar
                // and home indicator, and the page's CSS env(safe-area-inset-*)
                // pads the filter panel / sheet down. Insetting the top here would
                // leave a blank strip above the WebView and zero out the CSS inset.
                .ignoresSafeArea()
        }
    }
}
