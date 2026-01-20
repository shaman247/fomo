# Fomo NYC - iOS App

WebView-based iOS app that wraps fomo.nyc for App Store distribution.

## Approach

This app uses a WKWebView to load the fomo.nyc website directly:

- **Identical experience** to the mobile website
- **Automatic updates** - website changes appear immediately
- **Minimal maintenance** - just two Swift files
- **Extensible** - native features can be added later

## Requirements

- macOS with Xcode 15+
- iOS 17.0+ deployment target

## Setup Instructions

### 1. Create Xcode Project

1. Open Xcode
2. File → New → Project
3. Select **"App"** under iOS
4. Configure:
   - Product Name: `Fomo`
   - Team: (your team)
   - Organization Identifier: `nyc.fomo`
   - Interface: **SwiftUI**
   - Language: **Swift**
   - Storage: None
5. Save to: `mobile/ios/`

### 2. Replace Generated Files

1. In Xcode's project navigator, delete:
   - `ContentView.swift` (move to trash)
   - `FomoApp.swift` (move to trash)

2. Drag these files into the project navigator:
   - `FomoApp.swift`
   - `WebViewContainer.swift`

3. When prompted, check "Copy items if needed"

### 3. Build and Run

1. Select an iOS Simulator (iPhone 15 Pro recommended)
2. Press Cmd+R
3. The app loads fomo.nyc in a native wrapper

## Files

```
mobile/ios/
├── README.md
├── FomoApp.swift           # App entry point
└── WebViewContainer.swift  # WKWebView wrapper
```

## Features

- [x] Full fomo.nyc website experience
- [x] Loading indicator
- [x] Error handling with retry
- [x] External links open in Safari
- [x] Swipe-back navigation gesture
- [x] Geolocation support

## Future Enhancements

- [ ] Offline mode (cache HTML/JSON)
- [ ] Push notifications
- [ ] Share extension
- [ ] Home screen widget
- [ ] App Clips
