"""Command-line interface for shortsfactory.

Usage:
    shortsfactory generate --topic space [--out out/space.mp4] [--provider-tts tone]
                           [--provider-bg gradient] [--cards 5]
    shortsfactory topics
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

from .config import Config
from .content.topics import list_topics
from .story.episodes import EPISODES, list_episodes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shortsfactory",
        description="Generate vertical 9:16 knowledge-card short-form videos (offline-first).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Render a short video for a topic.")
    gen.add_argument("--topic", required=True, help="Topic pack name (see 'topics').")
    gen.add_argument(
        "--out",
        default=None,
        help="Output mp4 path (default: out/<topic>.mp4).",
    )
    gen.add_argument(
        "--provider-tts",
        default=None,
        choices=["tone", "edge", "gtts"],
        help="TTS provider (default: from config / 'tone').",
    )
    gen.add_argument(
        "--provider-bg",
        default=None,
        choices=["gradient", "pexels"],
        help="Background provider (default: from config / 'gradient').",
    )
    gen.add_argument(
        "--provider-script",
        default=None,
        choices=["template"],
        help="Script provider (default: 'template').",
    )
    gen.add_argument(
        "--cards",
        type=int,
        default=5,
        help="Number of knowledge cards to include (default: 5).",
    )

    sub.add_parser("topics", help="List available topic packs.")

    ep = sub.add_parser(
        "episode", help="Render a scene-based micro-drama episode."
    )
    ep.add_argument(
        "--episode", default="ep01", help="Episode id (see 'episodes'). Default: ep01."
    )
    ep.add_argument(
        "--out", default=None, help="Output mp4 path (default: out/<episode>.mp4)."
    )
    ep.add_argument(
        "--provider-tts",
        default=None,
        choices=["tone", "edge", "gtts"],
        help="TTS provider (default: from config / 'tone').",
    )
    ep.add_argument(
        "--provider-script",
        default=None,
        choices=["template", "openai", "anthropic"],
        help=(
            "Episode source (default: 'template' = authored offline episode). "
            "'openai'/'anthropic' generate the episode from the series bible + prior "
            "cliffhanger and require an API key + outbound internet."
        ),
    )
    ep.add_argument(
        "--provider-image",
        default=None,
        choices=["openai"],
        help=(
            "OPT-IN AI character art (default: none = offline code-drawn figures with "
            "motion). 'openai' generates/caches a consistent key visual per character and "
            "composites it in place of the code-drawn figure; requires OPENAI_API_KEY + "
            "outbound internet and is billed per image."
        ),
    )

    sub.add_parser("episodes", help="List available micro-drama episodes.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "topics":
        print("Available topic packs:")
        for name in list_topics():
            print(f"  - {name}")
        return 0

    if args.command == "episodes":
        print("Available episodes:")
        for ep_id in list_episodes():
            print(f"  - {ep_id}: {EPISODES[ep_id].title}")
        return 0

    if args.command == "episode":
        from .pipeline import generate_episode

        config = Config.load()
        out_path = args.out or os.path.join("out", f"{args.episode}.mp4")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

        try:
            result = generate_episode(
                episode_id=args.episode,
                out_path=out_path,
                tts_name=args.provider_tts,
                script_name=args.provider_script,
                image_name=args.provider_image,
                config=config,
            )
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3

        print(f"Wrote {result}")
        return 0

    if args.command == "generate":
        # Import here so 'topics' stays light and import errors surface in context.
        from .pipeline import generate

        config = Config.load()
        out_path = args.out or os.path.join("out", f"{args.topic}.mp4")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

        try:
            result = generate(
                topic=args.topic,
                out_path=out_path,
                tts_name=args.provider_tts,
                bg_name=args.provider_bg,
                script_name=args.provider_script,
                n_cards=args.cards,
                config=config,
            )
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        except RuntimeError as exc:
            # Clear, actionable provider errors (e.g. network provider unavailable).
            print(f"Error: {exc}", file=sys.stderr)
            return 3

        print(f"Wrote {result}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
