# Flutter Microsite Cleanup Roadmap

## A. Executive Summary

The current Flutter project is not a full native product. It is a thin Android wrapper around the existing web microsite, and that is the central architectural fact that should guide cleanup decisions.

The wrapper approach is acceptable if the goal is to reuse the web app quickly, but the codebase is currently carrying template leftovers, generated build output, and a smoke test that no longer matches the app. The bigger maintainability risk is not that the wrapper is too small; it is that the project has boilerplate and generated artifacts mixed in with the real product code, which makes the app look larger and less intentional than it is.

The right cleanup path is to keep the small set of real source files, remove template noise, make startup behavior explicit and testable, and avoid adding native Flutter UI complexity unless the product is intentionally being rebuilt as a standalone app.

## B. Current Architecture Assessment

### What the app is today

- Android-only Flutter shell.
- Uses `flutter_inappwebview` to load the microsite.
- Clears cookies and cache on launch.
- Grants browser permissions inside the webview.
- Renders a loading overlay and retry state while the embedded app starts.
- Delegates almost all real product behavior to the web microsite.

### What that means architecturally

- Flutter is not the product logic owner.
- The embedded web app remains the source of truth for interview flow, photo upload, and microsite generation.
- Flutter is currently acting as a transport shell, not a separate UI platform.
- If the wrapper hangs at startup, that can be a Flutter shell problem, a remote web app problem, or a dependency contract problem between the two. The cleanup plan should keep that boundary explicit instead of treating every startup failure as a Flutter defect.

### Architectural fit

This is reasonable for a kiosk-style Android deployment if the goal is speed and reuse.

It is not ideal if the long-term goal is a fully native cross-platform app. In that case, the wrapper becomes a transitional architecture and should eventually be replaced rather than expanded.

## C. Files and Components to Preserve

### Core Flutter source

- [lib/main.dart](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/lib/main.dart)
- [lib/webview_screen.dart](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/lib/webview_screen.dart)
- [lib/session_manager.dart](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/lib/session_manager.dart)

These are the only real application files in the Flutter layer. They should remain small and focused.

### Android entrypoints

- [android/app/src/main/kotlin/com/ludi/transplant_flutter/MainActivity.kt](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/app/src/main/kotlin/com/ludi/transplant_flutter/MainActivity.kt)
- [android/app/src/main/AndroidManifest.xml](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/app/src/main/AndroidManifest.xml)
- [android/app/src/debug/AndroidManifest.xml](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/app/src/debug/AndroidManifest.xml)
- [android/app/src/profile/AndroidManifest.xml](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/app/src/profile/AndroidManifest.xml)
- [android/app/build.gradle.kts](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/app/build.gradle.kts)
- [android/build.gradle.kts](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/build.gradle.kts)
- [android/settings.gradle.kts](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/settings.gradle.kts)

These are standard Android/Flutter plumbing and should stay unless the app changes platform scope.

### Dependency and project metadata

- [pubspec.yaml](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/pubspec.yaml)
- [pubspec.lock](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/pubspec.lock)
- [analysis_options.yaml](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/analysis_options.yaml)
- [transplant_flutter.iml](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/transplant_flutter.iml)

`pubspec.yaml` and `pubspec.lock` are necessary. The `.iml` files are IDE metadata and can be left alone or removed from version control if they are tracked accidentally.

### Documentation worth keeping

- [docs/plans/FLUTTER_MICROSITE_FIX_PLAN.md](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/docs/plans/FLUTTER_MICROSITE_FIX_PLAN.md)

This is useful as a record of the recent wrapper cleanup direction.

## D. Files / Logic Recommended for Removal or Simplification

### Clear boilerplate leftovers

- [README.md](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/README.md)
  - Current content is the default Flutter starter text.
  - It should be replaced with a project-specific README or removed if the repo is not meant to be public-facing.

- [test/widget_test.dart](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/test/widget_test.dart)
  - It still references `MyApp` and the default counter sample.
  - It is outdated and misleading.
  - It should be deleted or rewritten to test the actual `TransplantApp` / `WebViewScreen` behavior.

### Generated build output

- `build/`
- `.dart_tool/`

These are generated artifacts and should not be treated as source files. They can be deleted locally at any time and should remain ignored.

### Overly template-like comments and defaults

- `android/app/build.gradle.kts` still has TODO comments from the Flutter template.
- Those comments should be cleaned up once the project is stable, because they read like unfinished starter code.

### Simplification candidates in source

- `lib/webview_screen.dart`
  - Good enough for the wrapper role, but it now carries loading state, timeout state, retry behavior, and WebView wiring in one file.
  - That is acceptable for now, but if it grows further, the loading overlay should be extracted into a smaller widget or controller.

- `MainActivity.kt`
  - The system bar hiding logic is reasonable for a kiosk-style Android app.
  - If kiosk mode is not essential, this can be simplified or removed.

## E. Technical Debt and Risks

### 1. Hardcoded remote URL

`kServerUrl` in [lib/main.dart](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/lib/main.dart) points directly to `https://ludi.a4hlab.org/microsite`.

- Why it exists: one deployment target.
- Why it matters: it makes local/staging switching harder and hides environment configuration.
- Recommendation: keep short term if the app is deployed to one backend only; otherwise externalize to a build-time or environment config.

### 2. WebView wrapper depends on remote app health

The Flutter shell is only as stable as the web app it embeds.

- Why it exists: the current design intentionally reuses the web microsite.
- Why it matters: startup stalls or SitePal issues look like Flutter bugs even when they are not.
- Recommendation: keep the wrapper only if the web app remains the canonical flow. Otherwise move to a native Flutter architecture.
- Cleanup implication: preserve the thin shell, but document and test the remote loading contract so the wrapper does not mask backend failures.

### 3. Android-only scope

There are no iOS/macOS/web Flutter targets in this repo.

- Why it exists: the project appears scoped to Android tablets/phones.
- Why it matters: the codebase is intentionally narrower, but it should be documented as such.
- Recommendation: preserve if Android-only is the real deployment target; otherwise expand project structure later.

### 4. Kiosk-style system UI control

`SystemUiMode.immersiveSticky` in [lib/main.dart](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/lib/main.dart) and the system-bar hiding logic in [MainActivity.kt](/mnt/c/users/bbofo/onedrive/desktop/transplant_flutter/android/app/src/main/kotlin/com/ludi/transplant_flutter/MainActivity.kt) are kiosk-oriented choices.

- Why it exists: the app was built for a controlled tablet-like experience.
- Why it matters: if the product should feel like a regular mobile app, hiding system bars by default may be unnecessary friction.
- Recommendation: keep only if kiosk-style full-screen behavior is truly part of the deployment scope; otherwise simplify later.

### 5. Thin wrapper plus complex backend

The backend interview flow is already complex. The Flutter shell should not try to duplicate that complexity.

- Why it exists: the web app already owns the product logic.
- Why it matters: duplicating the workflow natively before the backend contract is stable would create two hard-to-maintain implementations.
- Recommendation: keep the wrapper thin or explicitly replace it with a native app later.

### 6. Startup/loading edge cases

The loading overlay and retry behavior are an improvement, but the startup path still needs device-level validation.

- Why it exists: remote session init and embedded site readiness are asynchronous.
- Why it matters: slow networks and flaky device conditions can still expose failure cases.
- Recommendation: keep explicit timeout/retry state and test on the target hardware.

## F. Cleanup and Refactoring Plan

### Quick cleanup wins

- Replace the default `README.md` with a project-specific one or remove it.
- Delete or rewrite `test/widget_test.dart` so it no longer references `MyApp`.
- Remove template `TODO` comments from Gradle files once the app is stable.
- Ensure generated artifacts under `build/` and `.dart_tool/` remain excluded from source control.

### Medium-complexity improvements

- Externalize the server URL if the project needs local/staging/prod switching.
- Add a small Flutter widget test that verifies the app boots into `WebViewScreen` rather than the template counter app.
- Add a startup state model if `webview_screen.dart` grows further.
- Document the Android-only deployment scope explicitly.
- Add a note to the README or project docs explaining that startup failures can originate in the remote microsite, not just the Flutter shell.

### Larger architectural work

- Decide whether the app stays a webview wrapper or becomes a true native Flutter client.
- If native Flutter is chosen, move interview flow, photo flow, and review flow into Flutter screens and keep the backend only for data and generation.
- If wrapper mode remains the chosen path, keep Flutter intentionally minimal and stop adding native UI layers that duplicate web logic.
- If the team wants two real frontends, treat them as separate products with a shared backend contract, not as one codebase trying to do both jobs.

## G. UX and Responsiveness Improvements

- Preserve portrait and landscape support unless kiosk-only orientation becomes a strict requirement.
- Keep the wrapper responsive on phones and tablets.
- Avoid hardcoded width assumptions in Flutter UI overlays.
- Keep the loading overlay centered and readable on narrow screens.
- Keep error states actionable: the user should know whether to retry or check the connection.

## H. Stability and Loading Improvements

- Keep startup timeout handling.
- Keep retry behavior for failed web app loads.
- Keep session clearing on launch.
- Keep permission grants inside the WebView layer.
- Make failure states sticky enough that late WebView callbacks do not hide an error.
- Continue testing the actual path on real devices, because the remote web app can still fail independently of the wrapper.

## I. Recommended Implementation Sequence

1. Clean obvious boilerplate: README, smoke test, Gradle TODO comments.
2. Lock down the cleanup boundary: generated artifacts ignored, source files preserved.
3. Decide whether the Flutter app is a permanent wrapper or a transitional shell.
4. If wrapper stays, externalize configuration only if needed and keep the shell minimal.
5. If native rewrite is chosen, define the screen architecture before writing more UI code.
6. Validate startup behavior and layout on real phones and tablets.
7. Reassess whether the wrapper architecture still makes sense after device testing.

## J. Final Recommendations

The current Flutter project is small enough that the main cleanup problem is not excessive code volume. The main problem is that a starter template sits beside a real wrapper implementation, which makes the repo feel less intentional than it is.

Best next move:

- Preserve the current Flutter shell if the goal is to reuse the web microsite.
- Remove template leftovers and generated noise.
- Keep the wrapper thin.
- Do not expand Flutter UI complexity unless you are intentionally moving to a native app.
- If the team wants two true product options, treat the web app and Flutter app as separate frontends with a shared backend contract rather than trying to force the webview wrapper to become both.
