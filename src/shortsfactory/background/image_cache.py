"""On-disk cache for generated images, keyed by a deterministic content hash.

The AI image path (``image_provider.py``) is billed PER IMAGE, so we never want to re-call
the paid API for an image we already generated. This module provides a small, PURE,
offline-testable cache under ``assets/cache/`` (already gitignored): a stable hash of the
generation inputs maps to a PNG path; a lookup is just an existence check; writing a cached
file is a plain file write. Nothing here touches the network, so it is fully exercised by
the offline test suite.
"""

from __future__ import annotations

import hashlib
import os

# All cached images live here; this directory is gitignored and created on demand.
CACHE_DIR = os.path.join("assets", "cache", "images")


def cache_key(backend: str, model: str, prompt: str, size: str, seed: int) -> str:
    """Return a deterministic hex key for one generation request.

    The key is a SHA-256 over the tuple that uniquely identifies an image: the backend
    name, the model, the full prompt, the pixel size, and the seed. Same inputs always
    yield the same key; any change to the prompt or seed yields a different key. Pure and
    offline.
    """
    payload = "\u0000".join(
        [
            str(backend or ""),
            str(model or ""),
            str(prompt or ""),
            str(size or ""),
            str(int(seed)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(
    backend: str,
    model: str,
    prompt: str,
    size: str,
    seed: int,
    cache_dir: str = CACHE_DIR,
) -> str:
    """Return the on-disk PNG path for a generation request (does not check existence)."""
    return os.path.join(cache_dir, f"{cache_key(backend, model, prompt, size, seed)}.png")


def lookup(
    backend: str,
    model: str,
    prompt: str,
    size: str,
    seed: int,
    cache_dir: str = CACHE_DIR,
):
    """Return the cached PNG path if it already exists on disk, else None. Offline."""
    path = cache_path(backend, model, prompt, size, seed, cache_dir=cache_dir)
    return path if os.path.exists(path) else None


def store(path: str, data: bytes) -> str:
    """Write ``data`` to ``path`` (creating the cache directory on demand). Returns path.

    Used to persist a freshly generated image so a later identical request re-finds it via
    :func:`lookup` instead of re-calling the paid API.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path
