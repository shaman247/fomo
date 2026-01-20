# Fomo NYC - Android App

Native Android app using Kotlin and Jetpack Compose.

## Setup (TODO)

1. Open Android Studio
2. Create new project: "Empty Activity" (Compose)
3. Package name: `nyc.fomo`
4. Minimum SDK: API 26 (Android 8.0)

## Architecture

```
app/src/main/java/nyc/fomo/
├── data/
│   ├── model/          # Event, Location data classes
│   ├── repository/     # Data layer
│   └── api/            # Retrofit API service
├── ui/
│   ├── map/           # Map screen
│   ├── events/        # Event list screen
│   ├── detail/        # Event detail screen
│   └── components/    # Reusable composables
└── di/                # Dependency injection (Hilt)
```

## Key Dependencies

```kotlin
// build.gradle.kts (app)
dependencies {
    // Compose
    implementation(platform("androidx.compose:compose-bom:2024.01.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")

    // Navigation
    implementation("androidx.navigation:navigation-compose:2.7.6")

    // MapLibre
    implementation("org.maplibre.gl:android-sdk:10.2.0")

    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")

    // Local storage
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    // DI
    implementation("com.google.dagger:hilt-android:2.50")
    ksp("com.google.dagger:hilt-compiler:2.50")
}
```

## Status

🚧 Scaffolded - Implementation pending (focusing on iOS first)
