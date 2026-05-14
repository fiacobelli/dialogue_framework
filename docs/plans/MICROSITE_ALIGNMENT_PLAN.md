# Microsite Alignment Plan

Date: 2026-05-14

## Goal

Bring the transplant microsite app onto the same engineering level as the SDOH screening app while keeping the two branches independent.

The apps should not share one common code file or package. Instead, shared concepts should be mirrored as separate code in each project, and each app should diverge only where the product behavior is different.

- Screening app: SDOH question-and-answer screening flow.
- Microsite app: transplant donor-story interview, photo upload, and generated donor webpage.

## Current Source Of Truth

Both projects are deployed on the same EC2 instance and currently track separate branches from the same GitHub repository.

- Transplant local path: `C:\Users\bbofo\OneDrive\Desktop\TRANSPLANT\dialogue_framework`
- Transplant branch: `bernard`
- Transplant server path: `/home/ubuntu/transplant-microsite`
- Transplant service: `microsite.service`
- Transplant port: `5001`
- Screening local path: `C:\Users\bbofo\OneDrive\Desktop\SDOH_SCREENING\dialogue_framework`
- Screening branch: `bernard-sdoh-screening`
- Screening server path: `/home/ubuntu/sdoh-screening`
- Screening service: `sdoh.service`
- Screening port: `5000`

The source-of-truth workflow should be:

```text
local repo -> GitHub branch -> EC2 pull -> restart service
```

Deployment-critical server code should be tracked in Git. The transplant `wsgi.py` file is now tracked in commit `2c2beff`.

## Existing Dirty Files

Before implementation, keep unrelated local changes out of the microsite alignment commits.

Current known local dirty files:

```text
TRANSPLANT:
 M static/js/SpeechManager.js
?? study_guide.docx

SDOH:
 D prompts/dialysis.txt
?? progress_overview.docx
?? study_guide.docx
```

Recommendation:

- Do not mix these files into routing, avatar, or frontend alignment commits.
- Ignore SDOH dirty files during microsite work unless explicitly working on screening.
- Inspect the transplant `static/js/SpeechManager.js` change before touching speech behavior, then either preserve it, commit it separately, or deliberately replace it as part of a planned speech migration.

## Phase 1: Fix Microsite Namespace

This is the root blocker and should be done before avatar or frontend work.

### Current Problem

Nginx sends `/microsite` to the transplant app, but root-level paths still go to the screening app.

```text
/microsite                    -> transplant app
/static/...                   -> screening app
/api/...                      -> screening app
/interview?...                -> screening app
/microsite/static/...         -> transplant app
```

This causes the microsite page to load the wrong JavaScript and CSS. For example, the browser may load the screening `App.js` instead of the microsite `App.js`.

### Target Behavior

All microsite pages, assets, APIs, uploads, generated pages, and uploaded photos should stay under `/microsite`.

```text
/microsite                              -> transplant landing page
/microsite/interview                    -> transplant interview
/microsite/static/...                   -> transplant static assets
/microsite/api/...                      -> transplant API routes
/microsite/upload/<session_id>          -> transplant mobile upload page
/microsite/site/<session_id>            -> generated donor page
/microsite/photos/<filename>            -> uploaded photo files
/microsite/avatar-preview/<scene_id>    -> avatar preview
```

### Implementation Direction

- Keep `wsgi.py` as the single `/microsite` mount layer.
- Remove explicit `/microsite` route aliases from `web/app.py`.
- Keep internal Flask routes simple, such as `/`, `/interview`, `/api/session`, `/site/<session_id>`, and `/photos/<filename>`.
- Inject one frontend base path from `request.script_root`, for example `window.APP_BASE_PATH`.
- Replace hardcoded root URLs in templates and JavaScript.
- Replace manual URL construction in backend code with route-aware URL generation.

Specific surfaces to fix:

- `templates/select_avatar.html`
- `templates/interview.html`
- `templates/upload_mobile.html`
- `static/js/ConversationAPI.js`
- `static/js/App.js`
- `static/js/UIController.js`
- `web/routes_api.py`
- `web/routes_photos.py`
- `web/microsite.py`

Examples of risky current patterns:

```text
/static/css/interview.css
/static/js/App.js
/api/session
/avatar-preview/<scene_id>
/upload/<session_id>
/site/<session_id>
/photos/<filename>
request.host_url + "upload/..."
window.location.origin + data.microsite_url
```

Preferred patterns:

- Use `url_for()` in Jinja templates.
- Use `request.script_root` to expose the mounted app prefix to JavaScript.
- Use `url_for(..., _external=True)` for QR links and generated share URLs.
- Use a single JavaScript helper for app-relative URLs.

## Phase 2: Align Avatar Model

After routing is stable, mirror the screening avatar model into the microsite app as separate code.

### Target Avatar Set

The microsite app should use the same six avatar IDs as screening:

```text
black_female
latina_female
white_male
black_male
latino_male
white_female
```

All display names should be `Ludi`, matching screening.

Each avatar profile should include:

```text
name
scene_id
gender
lang
race
engine
language
voice
```

Add a microsite-side constant:

```python
DEFAULT_AVATAR_ID = 'black_female'
```

Replace all `mary`, `jane`, and `laura` defaults with `DEFAULT_AVATAR_ID`.

### Files To Update

- `web/config.py`
- `web/app.py`
- `web/routes_api.py`
- `static/js/App.js`
- `templates/select_avatar.html`
- `templates/interview.html`

### Avatar Preview Assets

Copy the screening avatar preview PNGs into the transplant repo as separate files:

```text
static/photos/avatars/2756814.png
static/photos/avatars/2756815.png
static/photos/avatars/2774645.png
static/photos/avatars/2774646.png
static/photos/avatars/2774647.png
static/photos/avatars/2774648.png
```

The microsite selection page should use these local image previews instead of iframe previews.

### SitePal Voice Configuration

The microsite interview page currently hardcodes SitePal values. That should be changed to profile-driven values, matching the screening pattern.

The template should receive:

- `avatar_id`
- `avatar_profile`
- `avatar_scene_id`

Then JavaScript should derive:

```javascript
const avatarProfile = window.AVATAR_PROFILE || {};
let language = avatarProfile.language || 1;
let voice = avatarProfile.voice || 11;
let engine = avatarProfile.engine || 4;
```

## Phase 3: Frontend Parity In Slices

Do not blindly copy the screening frontend into microsite. The microsite has product-specific photo upload, QR upload, donor-page generation, preview, and sharing logic.

### Safe Concepts To Mirror

- Improved `SpeechManager` behavior.
- VAD assets and initialization.
- `SentenceQueue.js` pattern.
- Repeat button behavior.
- Pause/resume behavior.
- Better SitePal stop/resume handling.
- Cleaner event wiring.

### Do Not Copy Directly

- `InputHandler.js`: screening-specific patient last-name/DOB overlay should not be copied verbatim.
- `App.js`: screening-specific classification/reporting does not apply to microsite.
- `UIController.js`: screening thank-you/progress layout differs from microsite photo/generation flow.

### Recommended Slice Order

1. Add a microsite-specific app URL helper and remove root-path assumptions.
2. Add a microsite-specific `InputHandler.js` only for shared DOM wiring, photo upload events, repeat/restart events, and text/mic controls.
3. Add `SentenceQueue.js` if microsite later adopts streaming.
4. Adapt the newer `SpeechManager` carefully, making VAD asset paths prefix-aware.
5. Add repeat/pause/resume UI only after the speech layer is stable.

## Phase 4: Microsite Flow Control

Defer this until routing and avatars are stable.

The screening app now uses code-owned flow control through `web/screening_flow.py`. The microsite should eventually use the same engineering principle, but not the same file.

Create a microsite-specific flow helper, likely:

```text
web/interview_flow.py
```

Purpose:

- Code owns the donor-story section order.
- LLM owns natural wording.
- Flow transitions to photo upload deterministically.
- Completion does not depend only on detecting goodbye phrases.

Potential microsite story sections:

- Personal background.
- Family and community.
- Kidney disease history.
- Daily life with kidney failure.
- Transplant hopes and goals.
- Message to potential donors.
- Final details and tone.
- Photo upload transition.

## Verification Gates

Every phase should follow the same workflow:

```text
test locally -> commit -> push -> EC2 pull --ff-only -> restart microsite -> verify public URLs
```

### Minimum Local Checks

- Flask route map.
- Template rendering.
- API session creation.
- Photo upload route behavior where applicable.
- Generated URL values include the expected base path.

### Minimum Public Checks After Phase 1

```text
https://ludi.a4hlab.org/microsite
https://ludi.a4hlab.org/microsite/interview?avatar=black_female
https://ludi.a4hlab.org/microsite/static/css/interview.css
https://ludi.a4hlab.org/microsite/static/js/App.js
https://ludi.a4hlab.org/microsite/api/session
https://ludi.a4hlab.org/microsite/avatar-preview/2756814
```

Expected:

- Microsite URLs should return from the transplant app.
- No microsite page should request root-level `/static`, `/api`, `/upload`, `/site`, `/photos`, `/avatar-preview`, or `/interview`.
- Root-level screening behavior should remain unchanged.

### Browser Network Check

Open DevTools Network tab while loading the microsite.

Failing signs:

```text
/static/...
/api/...
/interview?...
/avatar-preview/...
```

Passing signs:

```text
/microsite/static/...
/microsite/api/...
/microsite/interview?...
/microsite/avatar-preview/...
```

## Deferred Work

Do not do these until the earlier phases are stable:

- Broad frontend rewrite.
- Directly copying screening `App.js` or `UIController.js`.
- Adding microsite streaming.
- Building `web/interview_flow.py`.
- Changing screening deployment or screening routes.

## Review Agent Corrections Incorporated

An independent review of the draft plan identified the following corrections, which are incorporated here:

- Prefix handling must include templates, JavaScript, generated HTML, QR links, photo URLs, and VAD/static paths.
- `url_for()` alone is not enough if explicit `/microsite` Flask routes remain.
- `request.host_url` does not include `/microsite`; route-aware URL generation is required.
- Avatar mirroring requires updating defaults everywhere, not just copying `web/config.py`.
- Avatar voice metadata will not matter until `interview.html` becomes profile-driven.
- Broad frontend copying should be deferred until routing is fixed.
