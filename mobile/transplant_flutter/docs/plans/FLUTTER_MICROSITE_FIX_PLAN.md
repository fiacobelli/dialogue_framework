# Flutter Microsite Fix Plan

## Purpose

The current Flutter app is a kiosk shell around the web microsite. That is acceptable for this project, but it is not yet production-ready for mixed phone/tablet use because it is locked to landscape and depends on a fragile startup sequence.

This plan focuses on two things:

1. Make the Flutter wrapper responsive and usable on phones and tablets without forcing orientation.
2. Fix the loading path after avatar selection so the app does not get stuck at `Loading Ludi...`.

## Current State

### What is good enough to keep

- The app shell is simple.
- `flutter_inappwebview` is a reasonable choice for embedding the existing web microsite.
- Session clearing on launch is sensible for kiosk-style use.
- Automatic microphone permission granting is useful for the tablet flow.
- The web microsite already contains most of the product logic, so the Flutter layer should stay thin unless we intentionally rebuild the product natively.

### What is not good enough

- Android is hard-locked to landscape in the manifest.
- `main.dart` also forces landscape orientation at runtime.
- The app uses a single remote web URL and has no loading timeout or fallback state.
- The loading state depends on both `/api/session` and SitePal readiness, but the UI gives no clear failure path if either stalls.
- The Flutter shell does not currently adapt to phones in portrait or tablets in portrait.

## Root Cause Summary

### 1. Orientation and fitting problems

The main cause is not Flutter state management. It is the layout policy:

- `android/app/src/main/AndroidManifest.xml` forces `android:screenOrientation="landscape"`.
- `lib/main.dart` forces landscapeLeft and landscapeRight only.
- The embedded web app is also styled for wide screens and uses desktop-like full-height panel layouts.

This means the app behaves like a kiosk board, not a responsive mobile app.

### 2. Loading issue after avatar selection

The current startup flow waits for:

- `conversationAPI.startSession('en', avatarId)`
- `this._waitForSitePal()`

If either stalls, the user stays on `Loading Ludi...`.

The likely failure points are:

- backend session endpoint latency
- SitePal readiness not firing
- network issues
- no timeout or recovery path in the Flutter shell

## What To Keep

- Keep the Flutter wrapper if the goal is to reuse the existing web microsite.
- Keep `InAppWebView` unless we decide to rebuild the whole experience natively.
- Keep session clearing on launch.
- Keep automatic permission handling for mic/camera where safe.
- Keep the existing web app as the source of interview and microsite logic for now.

## What To Improve

### A. Flutter wrapper

- Remove forced landscape from the Flutter app.
- Replace it with responsive behavior that allows portrait and landscape.
- Only prefer landscape if there is a proven kiosk-only deployment path.
- Add a visible fallback state if the web app does not finish loading.
- Add a timeout for startup so the app can fail gracefully instead of hanging forever.
- Show a retry button and a simple error explanation if the session cannot initialize.
- Add lightweight logging for startup timing:
  - page load start
  - session request start/end
  - avatar ready start/end
  - loading timeout events

### B. Web startup flow

- Make `Loading Ludi...` state time-bounded.
- Surface actual failures from `/api/session` and SitePal load events.
- Do not hide all errors behind a disabled button.
- If session creation succeeds but SitePal is delayed, show the user what is still loading.

### C. Speech interaction reliability

- Fix the `App.js` empty-response retry loop so it does not keep reissuing turns in a way that feels like the app is stuck.
- Remove the assumption that silence means failure.
- Keep a visible listening state, but do not leave the microphone open indefinitely without a ceiling.
- Preserve a clear long-stop / abort threshold for safety and battery control.

### D. Long-answer handling

- Review the `/api/transcribe` payload cap before encouraging longer pauses or longer uninterrupted stories.
- If longer answers are expected, choose one of:
  - safe audio cap increase,
  - client-side audio segmentation,
  - compression,
  - or streaming STT.
- Do not raise pause windows without also addressing the audio size limit.

### E. Responsive web UI

- Revisit the interview page layout for narrow screens.
- Remove any desktop-only assumptions that make the mobile webview feel clipped.
- Ensure buttons, avatars, and content scale cleanly on portrait phones and tablets.
- Audit hardcoded widths/heights in the interview and photo sections.

### F. Auth and telemetry

- Add patient-token authorization to any speech-related client events before expanding telemetry further.
- Update event and metadata allowlists when introducing new finalization fields.
- Do not store raw microphone device labels unless there is a specific debugging reason.

## What To Remove Or Simplify

- Remove hard landscape enforcement unless the deployment target is truly kiosk-only.
- Remove any startup logic that can block forever without timeout.
- Remove assumptions that every device has a wide screen.
- Avoid adding new Flutter-native UI if the web microsite already owns the actual workflow.

## What To Fix First

1. Fix startup hang behavior.
2. Make orientation flexible.
3. Add a graceful error/retry path.
4. Fix the speech-empty retry loop and initial silence handling.
5. Verify the web app still renders correctly inside the Flutter webview on narrow screens.
6. Only after that, consider deeper native Flutter improvements.

## Recommended Implementation Sequence

### Phase 1: Make startup safe

- Add explicit timeout handling around the avatar-selection to interview transition.
- Separate session initialization from WebView readiness.
- Show a useful error state if the backend is slow or unavailable.

### Phase 2: Remove forced landscape

- Update the Android manifest.
- Update `main.dart`.
- Test portrait and landscape on phone and tablet.

### Phase 3: Make the web content responsive

- Inspect the interview page, photo flow, review flow, and celebration flow at narrow widths.
- Reduce fixed-width layout assumptions.
- Ensure the content can scroll naturally on small screens.

### Phase 4: Fix speech interaction safety

- Remove the current empty/silence retry behavior that can make the app feel stuck.
- Keep listening behavior patient-centered, but add a max local ceiling so the microphone does not stay active forever.
- Keep the UI text calm and explicit about what the app is doing.

### Phase 5: Improve observability

- Log startup timings and failures in a way that is easy to inspect from device logs.
- Capture whether the failure was network, backend, or SitePal related.

### Phase 6: Reassess whether Flutter is the right shell

- If the wrapper still feels brittle after the fixes above, decide whether to keep the shell or move to a native Flutter implementation.
- Do not make that decision before the wrapper is stable.

## Risks

- Removing landscape lock may expose hidden web layout issues.
- Adding timeouts too aggressively could create false failures on slow networks.
- Making the Flutter shell more native may duplicate logic already implemented in the web app.
- Raising the speech pause window without addressing the audio cap will cause larger transcription failures.
- A full native rewrite would be a much larger task and is not justified unless the web wrapper remains unreliable after the basic fixes.

## Recommendation

The Flutter app is good enough as a wrapper, but not good enough as-is for production use.

The right move is to keep the current architecture, remove the forced landscape assumption, add startup timeout/error handling, fix the speech empty-loop behavior, and make the embedded web content responsive enough for phones and tablets. Only after that should we decide whether a deeper Flutter rewrite is actually necessary.
