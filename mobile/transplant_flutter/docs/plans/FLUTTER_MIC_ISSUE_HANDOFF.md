# Flutter Microsite Microphone Issue Handoff

## Executive Summary

The Flutter donor app is currently a thin Android WebView wrapper around the deployed microsite:

```text
https://ludi.a4hlab.org/microsite
```

The original issue was that the app appeared stuck at `Loading Ludi...` after avatar selection. That is no longer the active failure. The app now loads the microsite, reaches the interview screen, and reaches the `Begin interview` step.

The current unresolved issue is microphone startup. After tapping `Begin interview`, the app shows:

```text
Microphone check failed.
Could not start audio source (NotReadableError)
```

The latest evidence shows the failure happens inside:

```js
navigator.mediaDevices.getUserMedia(...)
```

It happens before VAD starts, so VAD is not the first failing layer.

## Repositories and Runtime Locations

Local Flutter wrapper:

```text
C:\Users\bbofo\OneDrive\Desktop\transplant_flutter
/mnt/c/Users/bbofo/OneDrive/Desktop/transplant_flutter
```

Local microsite/web repo:

```text
C:\Users\bbofo\OneDrive\Desktop\TRANSPLANT\dialogue_framework
/mnt/c/users/bbofo/onedrive/desktop/transplant/dialogue_framework
```

Live EC2 microsite repo:

```text
/home/ubuntu/transplant-microsite
```

Live service:

```text
microsite.service
```

The screening app is separate:

```text
/home/ubuntu/sdoh-screening
sdoh.service
```

## Current Architecture

The Flutter app is a WebView wrapper, not a native interview implementation.

Relevant Flutter files:

- `lib/main.dart`
- `lib/webview_screen.dart`
- `lib/session_manager.dart`
- `lib/app_config.dart`
- `android/app/src/main/AndroidManifest.xml`
- `pubspec.yaml`

The WebView loads the deployed microsite. The microsite owns:

- avatar selection
- session creation
- SitePal readiness
- interview start
- microphone preflight
- VAD
- transcription
- conversation flow
- photo upload
- donor page generation

Relevant microsite files:

- `dialogue_framework/static/js/SpeechManager.js`
- `dialogue_framework/static/js/App.js`
- `dialogue_framework/templates/interview.html`
- `dialogue_framework/static/js/vad/`

## What Is Working

The Flutter wrapper now successfully:

- launches
- clears cookies/cache during bootstrap
- creates the WebView
- loads `https://ludi.a4hlab.org/microsite`
- navigates to `/microsite/interview?avatar=...`
- reaches the `Begin interview` step

Representative logs:

```text
[LUDI][webview] initState
[LUDI][webview] bootstrap start
[LUDI][session] clearing cookies and cache
[LUDI][session] clear complete
[LUDI][webview] bootstrap complete
[LUDI][webview] webview created
[LUDI][webview] load start: https://ludi.a4hlab.org/microsite
[LUDI][webview] load stop: https://ludi.a4hlab.org/microsite
[LUDI][webview] load start: https://ludi.a4hlab.org/microsite/interview?avatar=white_male
[LUDI][webview] load stop: https://ludi.a4hlab.org/microsite/interview?avatar=white_male
[microsite] startup ready [object Object]
```

This means Flask, nginx, session startup, and basic WebView loading are not the current blockers.

## Original Loading Issue

### Symptom

After avatar selection, the app stayed on:

```text
Loading Ludi...
```

### Root Findings

The Flutter wrapper originally did not expose enough startup diagnostics. It also had startup sequencing risks around cache/session clearing and WebView mounting.

There was also a microsite JavaScript crash inside Android WebView:

```text
Cannot read properties of undefined (reading 'getVoices')
```

That came from assuming this browser API always existed:

```js
window.speechSynthesis.getVoices()
```

Android WebView did not provide the same speech synthesis surface as regular Chrome.

### Fixes Already Applied

Flutter wrapper:

- removed forced landscape orientation
- made microsite URL configurable through `--dart-define`
- added startup logging in `lib/webview_screen.dart`
- added bootstrap and load timeouts
- allowed WebView mounting even if cache clearing is slow
- added WebView console logging
- added basic WebView permission grant handling through `onPermissionRequest`

Microsite:

- guarded `speechSynthesis`
- guarded fallback `speakText()` and `stopSpeakText()`
- avoided crashing when `speechSynthesis` is unavailable

## Current Microphone Failure

### Symptom

After tapping `Begin interview`, microphone startup fails.

Visible app error from the latest screenshot:

```text
Microphone check failed.
Could not start audio source (NotReadableError)
```

The user has already tried:

- granting microphone permission in Android app settings
- allowing microphone every time while using the app
- enabling host microphone access in the Android emulator
- testing on emulator
- testing on physical phone

The failure persists.

## Latest Evidence From May 28 Test

Relevant log sequence:

```text
[LUDI][webview] load stop: https://ludi.a4hlab.org/microsite/interview?avatar=white_male
[microsite] startup ready [object Object]
[SpeechManager] preflight:start [object Object]
[SpeechManager] preflight:getUserMedia:start [object Object]
[SpeechManager] preflight:error [object Object]
[microsite] mic preflight result [object Object]
Failed to begin interview: Error: failed [object Object]
```

Interpretation:

- The app reaches the interview start path.
- The failure happens at microphone preflight.
- The failing call is `navigator.mediaDevices.getUserMedia(...)`.
- VAD does not start.
- The visible browser error is `NotReadableError`, not `NotAllowedError`.

Why this matters:

- `NotAllowedError` usually means the user or browser denied permission.
- `NotReadableError` means the browser/WebView tried to start the microphone but could not open a usable audio source.
- This narrows the issue to Android WebView audio capture, but it does not prove the exact sub-cause.

Important limitation:

- Current JS logs show diagnostic objects as `[object Object]`.
- The screen exposed `NotReadableError`, but logcat does not yet show full structured metadata.
- Before making a major architecture change, logging should serialize objects as JSON.

## Relevant Code Today

The current web preflight requests audio with these constraints:

```js
navigator.mediaDevices.getUserMedia({
  audio: {
    channelCount: 1,
    echoCancellation: true,
    autoGainControl: true,
    noiseSuppression: true,
  }
})
```

This lives in:

```text
dialogue_framework/static/js/SpeechManager.js
```

The Flutter wrapper currently grants WebView permission requests:

```dart
onPermissionRequest: (controller, request) async {
  return PermissionResponse(
    resources: request.resources,
    action: PermissionResponseAction.GRANT,
  );
}
```

This lives in:

```text
transplant_flutter/lib/webview_screen.dart
```

The Android manifest includes:

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
```

This lives in:

```text
transplant_flutter/android/app/src/main/AndroidManifest.xml
```

Current Flutter dependencies do not include an explicit permission plugin:

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_inappwebview: 6.1.5
```

## Relevant Commits

Local microsite repo:

```text
f9b6bb5 Improve Flutter wrapper loading and responsiveness
55bd945 Guard microsite speech synthesis fallback
12c4c31 Add mic preflight diagnostics
```

Live EC2 microsite repo:

```text
feef0e4 Guard speech synthesis fallback
de0eaea Add mic preflight diagnostics
```

Note: EC2 push to GitHub failed because GitHub credentials are not configured on the EC2 box. The live service is updated and restarted.

## What Is Known With Confidence

- The app is not failing because Flask is down.
- The app is not failing because nginx is down.
- The app is not stuck at initial WebView loading anymore.
- The app reaches `Begin interview`.
- The mic failure happens before VAD.
- The failing browser API is `getUserMedia()`.
- The visible error is `NotReadableError`.

## What Is Not Yet Proven

The exact low-level cause of the `NotReadableError` is not proven.

Unproven possibilities:

- Android runtime microphone permission is not granted at the moment WebView asks for audio.
- WebView `onPermissionRequest` is not firing or not granting the expected resource.
- The current audio constraints are too strict for Android WebView.
- The emulator audio source is misconfigured or unavailable.
- The physical phone and emulator are failing for different reasons.
- The WebView engine has an audio capture limitation.

## Current Hypotheses

### Hypothesis A: Flutter WebView needs explicit runtime permission handling

The manifest declares `RECORD_AUDIO`, and the WebView grants permission requests, but the Flutter app does not explicitly check/request Android microphone permission before the web page calls `getUserMedia()`.

This may matter because Android app permission, WebView permission, and browser `getUserMedia()` permission are separate layers.

### Hypothesis B: Current audio constraints are too strict

The current request includes:

- `channelCount: 1`
- `echoCancellation: true`
- `autoGainControl: true`
- `noiseSuppression: true`

The next diagnostic should compare this with:

```js
navigator.mediaDevices.getUserMedia({ audio: true })
```

If simple audio works and constrained audio fails, the fix is in `SpeechManager.js`.

### Hypothesis C: Emulator audio setup is contributing, but not the whole story

In the latest emulator screenshot:

- `Enable Host Microphone Access` was enabled
- `Virtual microphone attached` was unchecked

That may explain emulator behavior. It does not fully explain the physical phone failure.

### Hypothesis D: Android WebView differs from Chrome

The earlier `speechSynthesis` failure already showed Android WebView does not behave exactly like Chrome. Microphone capture may have similar differences.

## Recommended Next Investigation

Do not redesign the app yet. First get better evidence at the exact failure layer.

Recommended changes for the next diagnostic pass:

1. Serialize JavaScript diagnostic objects as JSON so logcat does not show `[object Object]`.
2. Log every Flutter `onPermissionRequest`, including requested resources.
3. Log whether Flutter grants or denies each WebView permission request.
4. Add Flutter-side Android microphone permission state logging before WebView microphone use.
5. Test simple `getUserMedia({ audio: true })` separately from the current constrained request.
6. Rebuild and test emulator and physical phone separately.

Useful logcat filter:

```powershell
& $adb logcat | Select-String "LUDI|SpeechManager|microsite|flutter|WebView"
```

## Likely Solution Paths Depending on Evidence

### If Android runtime permission is the issue

Add explicit runtime permission handling in Flutter before microphone use.

Likely dependency:

```yaml
permission_handler
```

Then request/check microphone permission before WebView audio capture.

### If WebView permission bridge is the issue

Improve `onPermissionRequest` in `webview_screen.dart`:

- log requested resources
- request Android runtime permission first
- grant only after permission is confirmed
- show a visible error if permission is denied

### If constraints are the issue

Update `SpeechManager.js` to use a safer fallback:

1. try current preferred constraints
2. if `NotReadableError`, `OverconstrainedError`, or `AbortError`, retry with `{ audio: true }`
3. record which capture mode worked

### If WebView remains unreliable

Consider moving microphone capture into native Flutter while keeping the same backend APIs. This is a larger architectural change and should only be considered after the WebView mic bridge is properly tested.

## Current Recommendation

The next step should be diagnostic, not architectural. The current evidence narrows the problem to `getUserMedia()` inside Android WebView, but does not prove the exact sub-cause. The next agent should make the smallest diagnostic changes needed to prove whether the blocker is runtime permission, WebView permission bridge, audio constraints, or WebView engine behavior.
