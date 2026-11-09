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

## Provider options

A "provider" is a swappable piece of the pipeline. There are three kinds: narration
(TTS), background, and script. You can keep the offline defaults, or opt into better
quality.

| Concern    | Option     | Cost / needs        | How to select |
|------------|------------|---------------------|---------------|
| Narration  | `tone` (default) | Offline, free. A synthetic placeholder beep sized to the script. Works anywhere. | `--provider-tts tone` or `TTS_PROVIDER=tone` |
| Narration  | `edge`     | **Free**, needs internet. Microsoft Edge neural voices. Recommended for real narration. | `--provider-tts edge` or `TTS_PROVIDER=edge` |
| Narration  | `gtts`     | Free, needs internet. Google Text-to-Speech. | `--provider-tts gtts` |
| Background | `gradient` (default) | Offline, free. A Pillow-rendered color gradient. | `--provider-bg gradient` or `BG_PROVIDER=gradient` |
| Background | `pexels`   | **Opt-in / paid key**, needs internet. Royalty-free stock footage from Pexels. | `--provider-bg pexels` plus `PEXELS_API_KEY` in `.env` |
| Script     | `template` (default) | Offline, free. Turns a topic pack into a narration script. | `--provider-script template` |
| AI images  | (future)   | **Opt-in / paid key.** Reserved for AI-generated visuals. | set `OPENAI_API_KEY` in `.env` |

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
  `--provider-bg pexels`, `--provider-script template`.
- **As a default, in `.env`**: `TTS_PROVIDER=edge`, `BG_PROVIDER=pexels`. These apply to
  every run unless a flag overrides them.

Paid or key-based providers also need their key in `.env`:

```bash
# .env
PEXELS_API_KEY=your_pexels_key_here
OPENAI_API_KEY=your_openai_key_here
```

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
  render/       moviepy 9:16 compositor
  content/      knowledge-card topic packs (data-driven)
tests/          offline unit + smoke tests
out/            rendered mp4s land here (gitignored)
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full phased plan: YouTube Shorts auto-upload,
scheduling and batch generation, performance tracking, and optional direct uploading to
Instagram Reels and TikTok. Until those land, the rendered mp4 is ready for manual
re-upload to Reels and TikTok today.
