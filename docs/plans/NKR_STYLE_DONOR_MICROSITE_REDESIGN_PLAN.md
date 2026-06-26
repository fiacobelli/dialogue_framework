# NKR-Style Donor Microsite Redesign Plan

Date: 2026-06-26
Branch: `bernard-dev`
Status: Revised final roadmap after independent review

## Executive Summary

The current donor microsite is improved but not yet at the required production standard. The target is not a generic story page. The target is a public kidney-donor campaign page that can credibly sit beside the National Kidney Registry example shared by Prof. Francisco:

`https://nkr.org/CCD266`

The current implementation has useful foundation work:

- A private preview flow.
- Patient-facing preview/approval wording.
- Hidden edit fields.
- Public sections grouped as `Who I am`, `Why I need a kidney`, and `How a donor can help`.
- Photos placed across the page instead of simply stacked.

However, it still does not fully rival the benchmark. The next pass must redesign the public page as a serious, beautiful, emotionally compelling donor campaign page with clear calls to action, trust framing, cloud/ribbon visual atmosphere, and a preview that closely matches the final public page.

Independent review conclusion: the original draft was directionally correct but not production-ready. The revised plan below tightens architecture, CTA policy, accessibility, privacy, preview/public drift control, and testing gates.

## Benchmark Findings From NKR Page

The NKR page is built as a donor campaign landing page, not a plain profile page.

Key observed details:

- Page title format: patient name + direct donor need, e.g. `Maria Diaz Needs a Kidney | Can You Help?`.
- Strong meta and social sharing fields: Open Graph title, description, image, Twitter card, canonical URL.
- Dedicated campaign stylesheet: `microsite-v2.css`.
- Kidney-specific color system: blue/green palette, not a soft generic journal palette.
- Fixed/visible campaign header concept with social/share affordances and prominent action buttons.
- Intro ribbon with a cloud-like background atmosphere.
- Large patient image treatment with polished framing.
- Quote/story emphasis near the top.
- Clear distinction between personal story, kidney need, and donor action.
- Read-more handling for long content.
- Callout-style sections explaining how people can help.
- Footer/trust framing connected to kidney donation information.

The exact NKR implementation is React-driven and not fully exposed through static HTML, so the goal is not to copy its code. The goal is to emulate the product/design pattern: credible donor campaign, strong CTA hierarchy, emotionally compelling layout, trustworthy medical framing, and polished mobile responsiveness.

## Current-State Problems

### Public Microsite

Current file:

- `templates/microsite.html`

Problems:

- The page looks pleasant but still too much like a soft personal story/blog.
- The CTA hierarchy is weak.
- The hero does not clearly say `Needs a Kidney` with campaign urgency.
- The help section is generic and appears too late.
- There is no strong fixed campaign header or top action band.
- Trust framing is present but understated.
- The visual system does not yet use the cloud/ribbon campaign style discussed from the NKR example.
- Story sections are improved but not yet arranged like a conversion-focused donor page.
- Some campaign primitives already exist, including metadata, a campaign badge, share links, photo placement, and trust footer. The implementation should refine and elevate these rather than blindly rewrite working pieces.

### Private Preview

Current files:

- `templates/interview.html`
- `static/js/UIController.js`
- `static/css/avatar.css`

Problems:

- Preview is better than before but still only approximates the final public page.
- The preview should look nearly identical to the final public page so patients know exactly what they are approving.
- If the public page is redesigned, the preview renderer must be updated in parallel.
- Current public rendering is Jinja in `templates/microsite.html`, while preview rendering is duplicated in `static/js/UIController.js`. This is a drift risk and must be fixed architecturally.

### Content Generation

Current file:

- `prompts/microsite.txt`

Problems:

- Current JSON fields are usable, but they do not fully support campaign-style presentation.
- The page needs stronger donor-facing copy blocks such as a hero quote, donor callout, and share description.
- Any new copy must remain evidence-grounded and must not fabricate patient facts.

### Backend Rendering

Current file:

- `web/microsite.py`

Problems:

- Rendering is currently coupled to the public template, while preview rendering is duplicated client-side.
- CTA destination and wording are not centralized.
- Share metadata exists but can be strengthened to match campaign-page expectations.

## Revised Architecture Principle

The public page and private preview must not be two independently maintained designs.

New rendering architecture:

- Create one shared campaign body partial, for example `templates/_donor_campaign_body.html`.
- Public `templates/microsite.html` wraps that shared body with full document metadata, canonical URL, social tags, footer scripts, and public share URLs.
- Private preview should use the same campaign view model and either:
  - receive server-rendered preview HTML from `/api/generate`, or
  - call a small authenticated preview endpoint that renders the same partial with preview-safe photo URLs.
- Move campaign page styling into one shared stylesheet, for example `static/css/microsite_campaign.css`, used by both public page and preview.
- `UIController.js` should stop reconstructing the campaign layout manually. It should inject the server-rendered preview HTML or render only a minimal wrapper.

This adds at most one template partial and one stylesheet, but reduces duplicated logic and makes the design easier to maintain.

Files likely affected by this architecture:

- `templates/_donor_campaign_body.html` new shared partial.
- `templates/microsite.html` public wrapper.
- `static/css/microsite_campaign.css` new shared stylesheet.
- `web/microsite.py` campaign view model and preview rendering helper.
- `web/routes_api.py` if `/api/generate` returns `preview_html` or if a private preview route is added.
- `static/js/UIController.js` simplified preview insertion.
- `templates/interview.html` if markup hooks need minor updates.

## Product Goal

Create a production-ready public donor microsite that:

- Immediately communicates that the patient needs a kidney.
- Makes the patient feel human, specific, and memorable.
- Explains why a kidney matters in a respectful, accurate way.
- Makes it obvious how a reader can help.
- Looks beautiful and credible on desktop, phone, and tablet.
- Uses a fixed design system, not AI-chosen styles.
- Preserves patient safety, privacy, and medical caution.
- Uses only evidence gathered from the interview.

## Design Direction

### Visual Style

Use a kidney-campaign visual language inspired by NKR but distinct enough to be our own:

- Blue/green kidney palette.
- White campaign cards over soft blue/green sections.
- Cloud/ribbon hero background to create atmosphere and optimism.
- Strong campaign banner: `Kidney Donor Needed`.
- Large hero patient photo.
- Rounded photo/card treatment.
- Clear, high-contrast buttons.
- Trust/footer section with responsible medical language.

Proposed palette:

- Deep navy: `#113459`
- Campaign blue: `#2778CE`
- Soft sky: `#DAE7F7`
- Kidney green: `#1F915D`
- Soft green: `#E6F2E2`
- White: `#FFFFFF`
- Warning/need accent: `#CE0E2D` used sparingly

Typography:

- Use one clean campaign sans-serif style.
- Avoid handwritten/journal typography.
- The public page should feel credible, modern, and donor-facing.

### Design Token Requirements

Define these in the shared campaign stylesheet:

- Breakpoints: phone, tablet, desktop.
- Sticky header behavior.
- Button states: default, hover, focus, disabled.
- Minimum tap target size: 44px.
- Contrast target: WCAG 2.2 AA.
- Reduced motion behavior for clouds/ribbon effects.
- Photo aspect ratios for hero, section photos, and gallery thumbnails.
- Safe fallback when a photo is missing or fails to load.

The cloud/ribbon treatment should be visually present but not heavy. It should feel hopeful and captivating without distracting from the patient story.

### Required Page Structure

1. Fixed or sticky campaign header

- Patient name/story title.
- `Needs a Kidney` campaign marker.
- Primary CTA.
- Share buttons.

2. Hero ribbon

- Cloud/ribbon background.
- Main patient photo.
- Headline.
- Short intro.
- Primary CTA.
- Secondary share CTA.

3. Patient-approved pullout / emotional anchor

- Prefer a verbatim patient sentence from accepted interview evidence.
- If generated, it must be shown in preview and approved by the patient before publication.
- Do not imply it is a direct quote unless it is verbatim.

4. `Who I am`

- Patient identity, family, work, community, values, personality.
- Patient photo or supporting photo if available.

5. `Why I need a kidney`

- Diagnosis/timeline if available.
- Dialysis/treatment impact.
- Daily limitations.
- Emotional and practical burden.

6. `How a donor can help`

- What transplant could restore or make possible.
- Message to potential donors.
- Respectful explanation that interested people should speak with qualified transplant professionals.

7. How to help callout panel

- Learn about living donation.
- Share this page.
- Talk to a transplant/transplant-center professional.
- Optional future slot: confidential donor screening if Prof. Francisco provides an approved destination.

8. Photo story gallery

- Hero photo.
- Journey photo.
- Hope/support photo.
- Photos must be integrated into story sections, not stacked.

9. Trust footer

- Not medical advice.
- Donation decisions should be guided by qualified transplant professionals.
- Link to reputable kidney donation resources.

## Content Model Plan

Keep the existing required fields:

- `headline`
- `short_intro`
- `personal_identity`
- `kidney_journey`
- `daily_impact`
- `transplant_hope`
- `donor_message`

Add only presentation-focused fields if needed:

- `approved_pull_quote`: one short verbatim or patient-approved pullout.
- `donor_callout`: one concise donor-facing summary of why help matters.
- `share_description`: short social-share description.

Rules:

- Do not invent medical details.
- Do not invent donor screening information.
- Do not create pressure, guilt, or unrealistic promises.
- Do not claim someone will be a match.
- Do not say paired exchange is available to the specific patient unless approved by the research/team context.
- Use generic educational framing only if no approved donor-screening link exists.
- Do not present generated language as a direct quote unless it is taken verbatim from the interview evidence.
- All optional presentation fields must be backward-compatible. Missing optional fields must not block generation or publication.

## CTA Policy

CTA destination is a release blocker.

If Prof. Francisco provides an approved recipient-specific donor-screening destination:

- Primary CTA: `Start Confidential Donor Screening`.
- Secondary CTA: `Share This Page`.
- Tertiary CTA: `Learn About Living Donation`.

If no approved recipient-specific donor-screening destination exists:

- Primary CTA: `Share This Page`.
- Secondary CTA: `Learn About Living Donation`.
- Tertiary CTA: `Talk With a Transplant Professional`.

Do not imply that the app collects donor applications unless that workflow is approved, built, and privacy-reviewed.

Centralize CTA config in backend rendering so wording and URLs are not scattered across templates and JavaScript.

## Implementation Plan

### Phase 1 — Shared Campaign Rendering Foundation

Files:

- `templates/_donor_campaign_body.html` new.
- `static/css/microsite_campaign.css` new.
- `templates/microsite.html`.
- `web/microsite.py`.
- `static/js/UIController.js`.

Changes:

- Define a canonical campaign view model in `web/microsite.py`.
- Create shared Jinja partial for the campaign body.
- Move campaign CSS to a shared static stylesheet.
- Make public page and private preview use the same structure/styling.
- Remove the duplicated full preview layout from `UIController.js` once server-rendered preview HTML is available.

Risk:

- Medium. Adds one shared partial and one stylesheet but reduces long-term duplication.

Validation:

- Public page and preview show the same sections, CTAs, photos, and visual hierarchy.
- `UIController.js` no longer owns donor-page layout decisions.

Rollback:

- Revert the shared partial/CSS changes and return to the last committed preview implementation.

### Phase 2 — Public Template Redesign

Files:

- `templates/microsite.html`
- `templates/_donor_campaign_body.html`
- `static/css/microsite_campaign.css`

Changes:

- Refine the current soft story-page layout into a campaign landing page.
- Add sticky campaign header.
- Add cloud/ribbon hero.
- Add hero image and CTA stack.
- Add patient-approved pullout block.
- Add section cards for the three required donor-facing sections.
- Add help/action panel.
- Add integrated photo gallery.
- Add trust footer.
- Preserve working metadata, share links, and publication gating.

Risk:

- Medium. This is mostly template/CSS work, but visual regressions are possible.

Validation:

- Render a generated page locally.
- Check desktop width.
- Check mobile width.
- Check tablet width.
- Confirm no internal labels are visible.
- Confirm photos appear in meaningful locations.

Rollback:

- Revert only `templates/microsite.html` if public rendering breaks.

### Phase 3 — Preview Matches Public Page

Files:

- `static/js/UIController.js`
- `static/css/avatar.css`
- `templates/interview.html`
- `web/microsite.py`
- `web/routes_api.py`

Changes:

- Update preview to use server-rendered campaign HTML from the shared partial.
- Use the same section order and CTA labels as the public page.
- Keep edit fields hidden in `Edit story details`.
- Ensure preview remains private and clearly labeled.

Risk:

- Medium. Preview endpoint or preview HTML response must remain authenticated by session/patient token.

Mitigation:

- Use the same shared partial and view model as the public page.
- Require `patient_token`/session authorization for preview HTML.
- Do not expose unpublished preview pages through public routes.

Validation:

- Generate preview locally.
- Compare preview and final public page visually.
- Confirm approve flow still works.

Rollback:

- Revert `UIController.js`, `avatar.css`, and `interview.html` if preview breaks.

### Phase 4 — Prompt / Content Upgrade

Files:

- `prompts/microsite.txt`
- `web/microsite.py`

Changes:

- Optionally extend JSON output with `approved_pull_quote`, `donor_callout`, and `share_description`.
- Normalize these fields in `web/microsite.py`.
- Use fallbacks derived from existing supported fields if the LLM omits optional fields.
- Improve meta description/social share text.

Risk:

- Medium-high if required fields are changed.

Mitigation:

- Make new fields optional at first.
- Do not break existing required fields.
- Keep `_normalize_content()` backward-compatible.

Validation:

- Generate multiple donor drafts.
- Confirm invalid/missing optional fields do not block publication.
- Confirm required fields still block incomplete drafts.

Rollback:

- Revert prompt and `web/microsite.py` optional-field changes while keeping template able to use existing fields.

### Phase 5 — CTA Configuration

Files:

- `web/microsite.py`
- `templates/microsite.html`
- `static/js/UIController.js`

Changes:

- Centralize CTA label and URL.
- Avoid hardcoding an unapproved donor-screening destination.
- Use the CTA hierarchy defined in `CTA Policy`.

Open decision:

- Should the primary CTA be:
  - `Start Confidential Donor Screening`
  - `Learn About Living Donation`
  - `Share This Page`
  - Another approved transplant-center action

Risk:

- High if we imply a donor-screening workflow that does not exist.

Validation:

- Confirm CTA destination with Prof. Francisco before production deployment.

Rollback:

- Change CTA config only; no template rollback required.

### Phase 6 — Testing and Production Readiness

Tests:

- JavaScript syntax check:
  - `node --check static/js/UIController.js`
  - `node --check static/js/App.js`
- Jinja parse check:
  - `templates/interview.html`
  - `templates/microsite.html`
- Local full interview:
  - Complete interview.
  - Upload three photos.
  - Preview donor page.
  - Approve/create public page.
  - View public page.
- Visual checks:
  - Desktop.
  - Phone.
  - Tablet.
  - Long story.
  - Short story.
  - One photo.
  - Three photos.
- Safety checks:
  - No internal labels visible.
  - No unsupported medical claims.
  - No invented facts.
  - Public route still protected by publication status.
  - Share links work.
- Accessibility checks:
  - WCAG 2.2 AA color contrast.
  - Keyboard navigation.
  - Visible focus states.
  - Skip link behavior with sticky header.
  - Reduced motion behavior.
  - Semantic heading order.
  - Alt text for uploaded photos.
  - Live feedback for copied links.
- Automated checks to add where feasible:
  - Jinja render fixture for public page.
  - Jinja render fixture for preview partial.
  - Optional-field backward compatibility.
  - Share metadata output.
  - JS syntax.
  - Playwright screenshot checks for phone, tablet, desktop if local tooling is available.
  - Axe/Lighthouse accessibility check if local tooling is available.

## Privacy and Safety Requirements

- Public pages must only render when publication status is approved/published.
- Preview pages must remain private and session-token protected.
- Unpublished/deleted pages must stop serving from public routes.
- Do not collect donor health or contact information unless explicitly approved.
- Do not imply donor screening exists unless the route and privacy handling are approved.
- Add photo guidance in UI reminding users not to upload photos they do not have permission to share.
- Avoid exposing minors/third-party images without consent guidance.
- Review indexing policy with Prof. Francisco. If pages are public and shareable, indexing may be acceptable; if not, add noindex behavior.
- Social preview images may persist in third-party caches after sharing; this should be acknowledged in consent copy if public sharing is encouraged.

## Existing Published Page Migration

Before deployment:

- Identify whether existing static microsites have been published.
- Decide whether old pages should remain as-is or be regenerated with the new template.
- If regenerating, preserve publication status and URLs.
- Do not overwrite or delete previous public pages without explicit approval.
- Test unpublish/delete behavior after redesign because static HTML files may already exist.

## Acceptance Criteria

The redesign is acceptable only if:

- The public page looks like a credible donor campaign page, not a plain generated story.
- The visual quality is close to the NKR benchmark and appropriate for real patient use.
- The page has a clear top campaign CTA.
- The cloud/ribbon atmosphere is present and polished.
- Photos are integrated into the story.
- The preview closely matches the final public page.
- The three required sections are obvious to readers:
  - `Who I am`
  - `Why I need a kidney`
  - `How a donor can help`
- The page is usable on phone/tablet without awkward cropping.
- The user never sees internal field names.
- The content remains evidence-grounded and medically cautious.
- Preview and public page are generated from the same campaign structure or shared partial.
- Accessibility has no obvious blocker issues.
- CTA wording and destination are approved before production deployment.
- Existing publish/unpublish behavior still works.

## Recommended Implementation Order

1. Confirm CTA wording/destination.
2. Add shared campaign view model, partial, and stylesheet.
3. Refine public page using the shared campaign body.
4. Change private preview to use the shared campaign body.
5. Add optional content fields only if the design needs them.
6. Add privacy/photo consent wording where needed.
7. Run syntax/template validation.
8. Run localhost full workflow.
9. Run accessibility/responsiveness checks.
10. User visual review.
11. Commit as a separate production redesign commit.
12. Promote/deploy only after localhost approval.

## Files Expected To Change

Primary:

- `templates/microsite.html`
- `static/js/UIController.js`
- `static/css/avatar.css`
- `templates/_donor_campaign_body.html`
- `static/css/microsite_campaign.css`
- `web/microsite.py`

Likely:

- `prompts/microsite.txt`
- `web/routes_api.py`

Possible:

- `templates/interview.html`
- `static/js/App.js`

Do not touch unless necessary:

- Interview flow files.
- Speech/VAD files.
- Database schema.
- Photo upload backend.

## Independent Review Summary

Reviewer verdict:

- The original draft is acceptable as a design brief, but not as a production implementation plan.
- The direction is right, but the plan needed tighter architecture, real CTA policy, accessibility/test gates, and privacy lifecycle detail.

Reviewer strengths:

- Correctly framed the page as a donor campaign landing page.
- Strong safety posture around no invented facts or medical claims.
- Correctly identified CTA destination as high-risk.
- Kept new content fields optional.

Reviewer concerns addressed in this revision:

- Preview/public duplication is now addressed through a shared campaign partial/view model.
- CTA hierarchy is now a release blocker with approved and fallback modes.
- `hero_quote` has been replaced with `approved_pull_quote`.
- Accessibility requirements are expanded.
- Privacy and public-page lifecycle risks are explicit.
- Existing campaign primitives are preserved/refined instead of blindly rewritten.
- Testing now includes template fixtures, optional-field compatibility, metadata checks, visual/responsive checks, and accessibility checks where tooling is available.

Final recommendation:

- Proceed only after confirming CTA destination/wording.
- Implement incrementally.
- Test locally before deployment.
- Do not deploy until the preview and public page look production-grade and match the campaign benchmark.
