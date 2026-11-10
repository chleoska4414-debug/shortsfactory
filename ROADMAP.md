# Roadmap

This project is pivoting toward a **vertical micro-drama series**: serialized short-dramas
(단편 드라마) built around a HOOK / TWIST / CLIFFHANGER spine, roughly 60 seconds per
episode, ending every episode on a cliffhanger. The flagship series is 걷어차인 회장님, a
subverted chaebol-heir romance in which the ordinary woman secretly holds the upper hand.
The knowledge-card short mode still ships and still works; the forward direction is the
drama series.

The product still grows from "generate a video locally" toward "generate, publish, and
learn what works." YouTube Shorts is the primary target because its API supports
programmatic upload. Instagram Reels and TikTok are a manual re-upload step today and a
possible automated step later.

Each phase lists the key risks so there are no surprises.

## Phase 1: Offline-capable generation engine (DONE, this MVP)

The working foundation shipped in this repository.

- One command renders a vertical 1080x1920 mp4 end to end. Two render paths:
  - **Knowledge-card mode:** topic -> script -> narration -> background -> burned-in
    captions -> mp4 with audio.
  - **Micro-drama episode mode:** an authored, scene-based episode (data in
    `src/shortsfactory/story/`) -> staged character key visuals -> Korean captions ->
    narration -> mp4 with audio, following the HOOK / TWIST / CLIFFHANGER spine. Episode 1
    (걷어차인 회장님) ships as data with its series bible and shot-by-shot script under
    `stories/ep01/`, and a committed offline sample at `samples/ep01.mp4`.
- Pluggable providers: TTS (`tone` offline default, `edge`, `gtts`), background
  (`gradient` offline default, `pexels`), and script (`template`).
- Korean captions render with a vendored Korean-capable font.
- Runs fully offline with no system media binaries (ffmpeg is bundled via
  `imageio-ffmpeg`).

**Interim publishing flow:** upload the rendered mp4 to YouTube Shorts, then re-upload the
same file to Instagram Reels and TikTok by hand.

**Risks:** the offline `tone` narration is a placeholder; real publishing needs a neural
voice (`edge`), which requires internet. The offline character visuals are code-generated
stylized figures, not hand-drawn art; true "well-drawn manga" quality needs supplied
character art or an image provider (see Phase 2). Render time grows with the number of
scenes or cards.

## Phase 2: Real illustrated-character pipeline (consistent faces)

Turn the code-drawn stand-in figures into real webtoon / anime-style character art that
stays consistent across an episode and across a series.

- Honor the drop-in convention `assets/characters/<episode>/<character_id>.png` so supplied
  or hand-drawn character sheets are composited in place of the code-drawn figure.
- Wire the optional image provider (OpenAI image generation, guarded by `OPENAI_API_KEY`)
  to generate character art from each character's visual spec.
- Keep each character's key visual stable across all of their scenes (same face, hair, and
  wardrobe), which is the hard part of any generated-art pipeline.

**Risks:** image generation needs a paid key and outbound network; **face / character
consistency** across prompts is genuinely hard and is the main quality risk; licensing of
any generated or supplied art is the user's responsibility; generation cost and latency add
up across a multi-scene episode.

## Phase 3: Korean neural narration

Replace the offline `tone` placeholder with natural Korean voice-over for the drama series.

- Use the `edge` neural voices with a Korean voice (set `EDGE_TTS_VOICE` to a `ko-KR`
  voice) so narration and dialogue sound like a real read.
- Match voice to speaker where practical (distinct voices for the leads vs. the anchor).

**Risks:** neural TTS needs internet and is not exercisable offline or in CI; Korean
prosody and pacing may need per-line tuning to fit the ~60-second budget; voice
availability and naming can change upstream.

## Phase 4: Multi-episode series batch generation

Move from one authored episode to a serialized, repeatable pipeline.

- Author episodes as data (`src/shortsfactory/story/episodes.py`) and batch-render a whole
  series in one invocation.
- A cron-style queue that generates and (with Phase 5) uploads on a schedule.
- Simple job state so interrupted batches can resume, and so the same episode is never
  posted twice.

**Risks:** keeping continuity and visual consistency across many episodes; uploads must
stay inside the daily API **quota**; scheduling needs a reliable host or runner; accidental
duplicate posting must be prevented.

## Phase 5: YouTube Shorts auto-upload

Automate publishing of each drama episode to YouTube using the **YouTube Data API v3**.

- OAuth 2.0 (Desktop app) authorization using the `client_secret.json` and
  `YOUTUBE_CLIENT_SECRETS_FILE` already documented in the README.
- Resumable upload of the rendered mp4.
- Auto-fill title, description, and hashtags from the episode (title, logline, series
  name), with `#Shorts` for Shorts eligibility.

**Risks:** YouTube API **quota** (a default daily quota makes each upload "expensive," so
batch runs must budget for it); **OAuth** setup and token refresh/expiry handling;
**platform policy** (metadata and content must satisfy YouTube's rules to be monetizable).

## Phase 6: Performance tracking and analytics

Close the loop by learning which episodes and hooks perform.

- Pull view, like, and retention stats via the YouTube Data / Analytics API.
- Rank hooks, twists, and series by performance, including early retention (the first few
  seconds matter most for serialized drama).
- Feed the winners back into authoring to favor what works.

**Risks:** analytics endpoints have their own **quota and auth scopes**; stats are delayed
and noisy, so early conclusions can mislead; store only what is needed and respect data
retention.

## Phase 7: Optional direct Instagram Reels / TikTok upload

Extend automated publishing beyond YouTube, if and where platform APIs allow. Serialized
drama shorts travel well across all three platforms, so the same episode mp4 is the unit.

- Instagram Reels via the Instagram Graph API (requires a Business/Creator account, a
  linked Facebook Page, and app review for the needed permissions).
- TikTok via its Content Posting API (requires developer approval; posting may land as a
  draft rather than a fully public post depending on access level).

**Risks:** both platforms have **stricter and changing API access** than YouTube, approval
processes, and policy limits; **manual re-upload remains the reliable interim flow** and
the fallback if automated access is denied or revoked.
