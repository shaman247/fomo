import SwiftUI

@main
struct FomoApp: App {
    var body: some Scene {
        WindowGroup {
            WebViewContainer()
                .ignoresSafeArea(edges: .bottom)
        }
    }
}
