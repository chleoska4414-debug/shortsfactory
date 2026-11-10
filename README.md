# shortsfactory

Auto-generate vertical (9:16, 1080x1920) "knowledge-card" short-form videos end to end,
ready to post on **YouTube Shorts** and to re-upload manually to **Instagram Reels** and
**TikTok**.

## Can a tool like this really make shorts for you?

Yes. This is achievable, and this project is the first working piece of it.

- **What works today (this MVP):** you run one command and get a finished vertical `.mp4`
  with a background, burned-in captions, and narration. That file is reusable: upload it
  to YouTube Shorts, then re-upload the same file to Reels and TikTok by hand.
- **What comes later (documented, not built yet):** fully automated uploading to YouTube
  (and optionally Reels/TikTok), scheduling, and performance tracking. See
  [ROADMAP.md](ROADMAP.md).

So the honest answer to "can you do all of this for me automatically?" is: generation is
automated now, and automatic multi-platform uploading is a planned later phase. YouTube
is the primary target because its API allows programmatic upload; Reels and TikTok are a
manual re-upload step for now (more on why in the roadmap).

## What this does

For a given topic it builds a short video automatically:

1. picks a **topic pack** (a small set of punchy facts),
2. turns it into a short **script**,
3. generates **narration** (TTS),
4. draws a **background**,
5. burns in **captions**,
6. renders a **1080x1920 mp4 with audio**.

Everything the default path needs runs **offline** and with **no media software to
install**. You get much nicer narration by switching on a free neural voice (needs
internet) when you run it on your own computer, explained below.

## Requirements

- **Python 3.11 or newer.**
- **No system ffmpeg needed.** The `imageio-ffmpeg` package bundles its own ffmpeg, so
  you do not install ffmpeg yourself.
- **No ImageMagick and no espeak needed** for the default path.
- Internet is optional. It is only needed if you opt into the online providers (neural
  voices or stock/AI images).

## Setup

A virtual environment is the standard, recommended way to install this. It keeps the
project's packages isolated from the rest of your system.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

That is it. The `.env` file is optional for the default offline run; you only edit it to
turn on the higher-quality providers described later.

To also install the optional online providers (neural voices, stock images):

```bash
python -m pip install -e ".[providers]"
```

## Quick start

Make sure your virtual environment is active (`source .venv/bin/activate`), then run:

```bash
python -m shortsfactory generate --topic space
```

This writes the finished video to **`out/space.mp4`** (that is, `out/<topic>.mp4`). The
output path is configurable with `--out`:

```bash
python -m shortsfactory generate --topic space --out out/my-first-short.mp4
```

Two things to know:

- The default render uses **5 cards** and takes roughly **2 to 3 minutes**. That is
  normal; it is doing real video encoding.
- To get a result faster while you experiment, render fewer cards:

  ```bash
  python -m shortsfactory generate --topic space --cards 3
  ```

Once `out/space.mp4` exists you can upload it to YouTube Shorts and re-upload the same
file to Reels and TikTok.

> After installing the package you can also use the short console command
> `shortsfactory generate --topic space` instead of `python -m shortsfactory ...`.
> Both are identical.

### Sample output

A ready-made example short lives at [`samples/space-sample.mp4`](samples/space-sample.mp4).
It was generated with the default offline settings, so its narration is the synthetic
`tone` placeholder rather than a real voice. For proper narration, render your own with
the free neural voice: `python -m shortsfactory generate --topic space --provider-tts edge`.

## Choosing and adding topics

List the topic packs that ship with the tool:

```bash
python -m shortsfactory topics
```

Current packs: **space**, **history**, **psychology**, **health**. Pick one with the
`--topic` flag, for example `--topic history`.

Topics are **data, not code**. To add your own, edit
`src/shortsfactory/content/topics.py` and add a new entry to the `TOPICS` dictionary.
Each topic is a list of cards, and each card has a `headline` and a `fact`:

```python
TOPICS = {
    "ocean": [
        {
            "headline": "The Deepest Point",
            "fact": "The Mariana Trench is deeper than Mount Everest is tall.",
        },
        {
            "headline": "Unmapped Seafloor",
            "fact": "More than 80 percent of the ocean floor has never been mapped in detail.",
        },
        # add as many cards as you like
    ],
}
```

Save the file, then `python -m shortsfactory generate --topic ocean`. No other code
changes are required.

## Micro-drama (short-drama) mode

Besides the knowledge-card shorts above, the tool can render a scene-based **micro-drama
episode**: a vertical, roughly 60-second serialized short-drama with Korean dialogue,
staged character key visuals, and a HOOK / TWIST / CLIFFHANGER structure. The card mode
still works exactly as before; this is a second, separate render path.

List the episodes that ship with the tool:

```bash
python -m shortsfactory episodes
```

Render Episode 1 to an mp4:

```bash
python -m shortsfactory episode --episode ep01 --out out/ep01.mp4
```

This writes the finished vertical 1080x1920 video to the `--out` path (default
`out/<episode>.mp4`). Episode 1 is **걷어차인 회장님**, a subverted chaebol-heir romance in
which the ordinary woman secretly holds the upper hand. The series bible and the
shot-by-shot script live under [`stories/ep01/`](stories/ep01/).

For real narration instead of the offline placeholder, add the free neural voice flag:

```bash
python -m shortsfactory episode --episode ep01 --out out/ep01.mp4 --provider-tts edge
```

`--provider-tts` accepts the same options as the card mode (`tone` offline default,
`edge`, `gtts`).

### Directed motion and camera (offline)

The episode render is never static. Each scene is a directed shot built purely offline:

- **Ken Burns zoom and pan.** Every scene slowly pushes in or pulls back with a gentle
  camera drift; the direction is seeded so neighboring scenes drift opposite ways instead
  of all sliding the same way.
- **Beat-driven emphasis.** The HOOK pushes in calmly, twists push harder, and the
  cliffhanger pulls back ominously. Reversal and twist moments add a short decaying screen
  shake, a quick punch-in, a brief RGB-split glitch at the cut, and a white flash.
- **Character idle animation.** The code-drawn figure breathes with a slow sway, blinks on
  a natural cadence, and moves its mouth while speaking on dialog scenes. These idle
  variants apply only to the code-drawn figure and are skipped gracefully when real art is
  supplied (the art PNG is composited verbatim).

All of this runs with no network and no media software; it is a pure function of the scene
and a seed, so a given scene renders the same way every time.

### AI episode scripts (optional)

Besides the authored offline episode, the episode mode can GENERATE the next episode from
the series bible plus the previous episode's cliffhanger using an AI script provider:

```bash
# Needs OPENAI_API_KEY + internet:
python -m shortsfactory episode --episode ep01 --provider-script openai
# Needs ANTHROPIC_API_KEY + internet:
python -m shortsfactory episode --episode ep01 --provider-script anthropic
```

The default (`--provider-script template`, or omitting the flag) uses the authored offline
episode and needs no key. Set the matching key in `.env`
(`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`). With no key or no network these providers stop
with a clear error instead of producing a broken video; they are never used by the default
offline path.

### Getting real "well-drawn manga" character visuals

The offline default draws each character as a code-generated stylized figure built from
that character's visual spec. It is deterministic and distinct per character, but it is a
stand-in, not hand-drawn art. To get real webtoon / anime-style characters, supply your
own or AI-generated art by the following drop-in convention:

```
assets/characters/<episode_id>/<character_id>.png
```

For Episode 1 that means, for example, `assets/characters/ep01/yoojin.png`,
`assets/characters/ep01/haeun.png`, and `assets/characters/ep01/anchor.png` (the character
ids are `yoojin`, `haeun`, and `anchor`). When a character's visual spec points at an
existing PNG, the renderer composites that artwork instead of the code-drawn figure. These
files are your own content and are intentionally kept out of the committed repository; only
the directory convention ships.

Alternatively, you can enable the optional OpenAI image-generation path with an explicit
flag plus a key:

```bash
python -m shortsfactory episode --episode ep01 --provider-image openai
```

This generates a consistent key visual for each character and composites it in place of
the code-drawn figure, reusing the exact same `asset_image` hook as supplied art. It needs
`OPENAI_API_KEY` in `.env` and outbound internet. With no key, no network, or no
`--provider-image` flag it falls back cleanly: the default render draws the offline figures
with motion, and a key-missing AI image request stops with a clear error instead of a
broken video or a traceback. The AI image path is never used by the default offline render.

#### Keeping a character consistent (same face across scenes)

Character consistency is the hard part of any generated-art pipeline, so the tool anchors
it deterministically. Each character has a **fixed style prompt** (appearance, hair,
wardrobe, art style) and a **deterministic seed**, both carried on the character's visual
spec (`VisualSpec.style_prompt` and `VisualSpec.seed`). If you do not author a style
prompt, a stable one is derived from the character's other visual fields. Every scene image
reuses that same fixed style prompt and seed and appends only the situation, so the
character stays on-model while the background changes from scene to scene and across
episodes.

#### A realistic cost note

Image generation is **billed per image**, and an episode needs several shots (at least one
key visual per character, and optionally a per-scene situation image). Those charges add
up quickly across an episode and across a series, so treat the image path as a paid,
opt-in feature. To avoid paying twice for the same picture, generated images are **cached
on disk** under `assets/cache/` keyed by a hash of the backend, model, prompt, size, and
seed; a repeat render reuses the cached image instead of calling the paid API again. The
cache directory is gitignored and never committed.

### Sample episode and an honest reality note

A ready-made example episode lives at [`samples/ep01.mp4`](samples/ep01.mp4). Be clear
about what it is:

- It was rendered via the **fully offline path**, so its on-screen characters are
  **code-generated stylized illustrations**, not hand-drawn art.
- Its narration is the synthetic **`tone` placeholder**, not a real voice.

That sample exists to prove the episode engine end to end on a machine with no network and
no media software. In this offline sandbox the on-screen figures are always code-drawn,
because the AI image path needs a key and outbound internet that are not available here.
Drop a key into `.env` and run with `--provider-image openai` on your own computer and the
same engine produces real AI illustrations instead. True "well-drawn manga" quality and
real narration come from running it locally with character art dropped in (or the image
provider enabled) and the `edge` neural voice turned on.

## Provider options

A "provider" is a swappable piece of the pipeline. There are four kinds: narration (TTS),
background, script, and (for the episode mode) AI images. You can keep the offline
defaults, or opt into better quality.

| Concern    | Option     | Cost / needs        | How to select |
|------------|------------|---------------------|---------------|
| Narration  | `tone` (default) | Offline, free. A synthetic placeholder beep sized to the script. Works anywhere. | `--provider-tts tone` or `TTS_PROVIDER=tone` |
| Narration  | `edge`     | **Free**, needs internet. Microsoft Edge neural voices. Recommended for real narration. | `--provider-tts edge` or `TTS_PROVIDER=edge` |
| Narration  | `gtts`     | Free, needs internet. Google Text-to-Speech. | `--provider-tts gtts` |
| Background | `gradient` (default) | Offline, free. A Pillow-rendered color gradient. | `--provider-bg gradient` or `BG_PROVIDER=gradient` |
| Background | `pexels`   | **Opt-in / paid key**, needs internet. Royalty-free stock footage from Pexels. | `--provider-bg pexels` plus `PEXELS_API_KEY` in `.env` |
| Script (cards) | `template` (default) | Offline, free. Turns a topic pack into a narration script. | `--provider-script template` |
| Script (episode) | `openai` / `anthropic` | **Opt-in / paid key**, needs internet. Generates the next episode from the series bible + prior cliffhanger. | `--provider-script openai` (`OPENAI_API_KEY`) or `--provider-script anthropic` (`ANTHROPIC_API_KEY`) |
| AI images (episode) | `openai` | **Opt-in / paid key**, billed per image, needs internet. Generates consistent character art; the offline default draws figures with no key. | `--provider-image openai` plus `OPENAI_API_KEY` in `.env` |

### Why the default is offline, and what to use instead

The default narration (`tone`) is a **synthetic placeholder beep**. It exists so the
whole pipeline runs anywhere, including machines and CI with no internet. It is not meant
for a real published video.

For real narration, run the tool on your own computer and use the free neural voice:

```bash
python -m shortsfactory generate --topic space --provider-tts edge
```

`edge` uses Microsoft's free neural voices and only needs an internet connection. You can
choose a different voice by setting `EDGE_TTS_VOICE` in `.env` (default
`en-US-AriaNeural`).

### Selecting providers

You can select any provider two ways:

- **Per run, with a flag** (overrides everything): `--provider-tts edge`,
  `--provider-bg pexels`, `--provider-script openai`, `--provider-image openai`.
- **As a default, in `.env`**: `TTS_PROVIDER=edge`, `BG_PROVIDER=pexels`,
  `SCRIPT_PROVIDER=template`, `IMAGE_PROVIDER=openai`. These apply to every run unless a
  flag overrides them. (`--provider-image` has no default; leave `IMAGE_PROVIDER` unset to
  stay offline.)

Paid or key-based providers also need their key in `.env`:

```bash
# .env
PEXELS_API_KEY=your_pexels_key_here
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

`OPENAI_API_KEY` is used by both the `openai` AI script provider and the `openai` AI image
provider; `ANTHROPIC_API_KEY` is used by the `anthropic` AI script provider.

If you select a provider that needs a key or network and it is not available, the tool
stops with a clear error instead of producing a broken video.

## Copyright and monetization: why this does not repost other people's videos

This tool deliberately **does not scrape or re-post other creators' videos**. That is a
choice to protect you, not a limitation.

- Platforms such as YouTube actively detect **reused or unoriginal content**. Channels
  built on other people's clips are routinely **rejected from monetization** or have ads
  limited, and can face strikes. Reuploading someone else's footage is also a copyright
  risk.
- To stay safe to monetize, shortsfactory composes each video from pieces that are clear
  to use:
  - **Visuals:** an offline generated gradient by default, or royalty-free / CC0 stock
    (for example Pexels), or AI-generated images. No ripped clips.
  - **Narration:** synthetic (offline tone) or neural TTS (edge-tts / gTTS). No
    copyrighted audio tracks.
  - **Script:** original text generated from the topic packs.

**Your responsibility:** if you plug in your own source (a stock provider, an AI image
service, your own footage, background music), you are responsible for confirming its
license allows the way you use and monetize it. Read the terms of any provider or asset
you add. When in doubt, use CC0 / royalty-free sources or assets you created yourself.

## YouTube Data API v3 setup (for the future upload phase only)

> **You do NOT need this for the MVP.** Generating the `.mp4` locally needs none of the
> steps below. This section is for the upcoming auto-upload phase (see
> [ROADMAP.md](ROADMAP.md)). You can set it up now so you are ready, or skip it entirely
> for today.

When the auto-upload phase lands, uploading to YouTube will use the YouTube Data API v3,
which requires a one-time Google setup:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and **create a new
   project** (or pick an existing one).
2. In **APIs & Services > Library**, search for **YouTube Data API v3** and click
   **Enable**.
3. Open **APIs & Services > OAuth consent screen**. Choose **External**, fill in the
   required app name and your email, and add your own Google account as a **test user**.
4. Open **APIs & Services > Credentials > Create credentials > OAuth client ID**. For
   **Application type**, choose **Desktop app**.
5. **Download** the credentials JSON. It is usually named something like
   `client_secret_XXXX.json`. Save it in the project folder (for example as
   `client_secret.json`).
6. In your `.env`, point the tool at that file:

   ```bash
   # .env
   YOUTUBE_CLIENT_SECRETS_FILE=client_secret.json
   ```

Keep this file private and never commit it. The first upload will open a browser once to
authorize your account; after that the tool reuses the saved authorization.

## Running the tests

```bash
python -m pytest -q
```

The test suite runs fully offline.

## Project layout

```
src/shortsfactory/
  script/       topic -> script
  tts/          narration providers (offline tone default)
  background/   visual backdrop providers (offline gradient default)
  captions/     Pillow text rendering (no ImageMagick)
  render/       moviepy 9:16 compositor (card + episode)
  content/      knowledge-card topic packs (data-driven)
  story/        micro-drama episode model + authored episodes (data-driven)
tests/          offline unit + smoke tests
stories/        human-readable series bible + episode scripts
out/            rendered mp4s land here (gitignored)
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full phased plan: YouTube Shorts auto-upload,
scheduling and batch generation, performance tracking, and optional direct uploading to
Instagram Reels and TikTok. Until those land, the rendered mp4 is ready for manual
re-upload to Reels and TikTok today.
