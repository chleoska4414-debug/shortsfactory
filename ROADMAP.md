# Roadmap

This project grows from "generate a video locally" toward "generate, publish, and learn
what works." YouTube Shorts is the primary target because its API supports programmatic
upload. Instagram Reels and TikTok are a manual re-upload step today and a possible
automated step later.

Each phase lists the key risks so there are no surprises.

## Phase 1: Offline-capable generation pipeline (DONE, this MVP)

The working foundation shipped in this repository.

- One command renders a vertical 1080x1920 mp4 end to end: topic -> script -> narration
  -> background -> burned-in captions -> mp4 with audio.
- Pluggable providers: TTS (`tone` offline default, `edge`, `gtts`), background
  (`gradient` offline default, `pexels`), and script (`template`).
- Data-driven topic packs; new topics are added as data with no code changes.
- Runs fully offline with no system media binaries (ffmpeg is bundled via
  `imageio-ffmpeg`).

**Interim publishing flow:** upload the rendered mp4 to YouTube Shorts, then re-upload the
same file to Instagram Reels and TikTok by hand.

**Risks:** the offline `tone` narration is a placeholder; real publishing needs a neural
voice (`edge`), which requires internet. Render time grows with the number of cards.

## Phase 2: YouTube Shorts auto-upload

Automate publishing to YouTube using the **YouTube Data API v3**.

- OAuth 2.0 (Desktop app) authorization using the `client_secret.json` and
  `YOUTUBE_CLIENT_SECRETS_FILE` already documented in the README.
- Resumable upload of the rendered mp4.
- Auto-fill title, description, and hashtags from the generated script, with
  `#Shorts` for Shorts eligibility.

**Risks:** YouTube API **quota** (a default daily quota makes each upload "expensive," so
batch runs must budget for it); **OAuth** setup and token refresh/expiry handling;
**platform policy** (metadata and content must satisfy YouTube's rules to be monetizable).

## Phase 3: Scheduling and batch generation

Move from one-off runs to a repeatable content pipeline.

- A cron-style queue that generates and (with Phase 2) uploads on a schedule.
- Multiple topics per run, so a single invocation can produce a batch of shorts.
- Simple job state so interrupted batches can resume.

**Risks:** uploads must stay inside the daily API **quota**; scheduling needs a reliable
host or runner; accidental duplicate posting must be prevented.

## Phase 4: Performance tracking and analytics

Close the loop by learning which content performs.

- Pull view, like, and retention stats via the YouTube Data / Analytics API.
- Rank topics and card styles by performance.
- Feed the winners back into generation to favor what works.

**Risks:** analytics endpoints have their own **quota and auth scopes**; stats are delayed
and noisy, so early conclusions can mislead; store only what is needed and respect data
retention.

## Phase 5: Optional direct Instagram Reels / TikTok upload

Extend automated publishing beyond YouTube, if and where platform APIs allow.

- Instagram Reels via the Instagram Graph API (requires a Business/Creator account, a
  linked Facebook Page, and app review for the needed permissions).
- TikTok via its Content Posting API (requires developer approval; posting may land as a
  draft rather than a fully public post depending on access level).

**Risks:** both platforms have **stricter and changing API access** than YouTube, approval
processes, and policy limits; **manual re-upload remains the reliable interim flow** and
the fallback if automated access is denied or revoked.
