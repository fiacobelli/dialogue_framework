# transplant_flutter

Android Flutter wrapper for the Ludi transplant microsite.

## What this app does

- Opens the microsite in an `InAppWebView`
- Clears cookies and cache on launch
- Grants webview permissions for the tablet flow
- Shows a startup overlay while the remote microsite loads

## Current scope

This project is intentionally thin. The real interview, photo upload, and page-generation logic lives in the web microsite backend and frontend.

## Source files

- `lib/main.dart`
- `lib/app_config.dart`
- `lib/webview_screen.dart`
- `lib/session_manager.dart`
- `android/app/src/main/kotlin/com/ludi/transplant_flutter/MainActivity.kt`

## Generated or local-only

These are created by Flutter/Android tooling and should not be treated as source:

- `.dart_tool/`
- `build/`
- `.idea/`
- `.flutter-plugins-dependencies`

## Notes

- The app is currently Android-only.
- The shell is designed for the microsite deployment at `https://ludi.a4hlab.org/microsite`, but you can override it at build time with `--dart-define=LUDI_SERVER_URL=...`.
- If the web app hangs at startup, that can come from the remote microsite as well as the Flutter wrapper.
- The current build uses Flutter 3.44.0, Dart 3.12.0, and Android API 36.
- Release APKs are debug-signed for internal testing until a study distribution key is configured.

## Build example

```bash
flutter build apk --release --dart-define=LUDI_SERVER_URL=https://ludi.a4hlab.org/microsite
```
