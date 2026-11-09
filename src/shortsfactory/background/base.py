"""Background provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple


class BackgroundProvider(ABC):
    """Base class for background visual providers."""

    @abstractmethod
    def make_clip(self, duration: float, resolution: Tuple[int, int]):
        """Return a moviepy clip sized to ``resolution`` lasting ``duration`` seconds.

        resolution is (width, height), e.g. (1080, 1920) for a 9:16 short.
        """
        raise NotImplementedError
