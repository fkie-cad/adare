"""Open-vocabulary element grounding backends for the GUI agent.

The default GUI agent grounds clicks with the vision LLM's own point estimate
(x, y) and records a fixed-size crop around it. This package adds an optional
*described-element* grounding path: given a natural-language description and a
screenshot, return a precise bounding box for the element. The current backend
is :class:`LocateAnythingClient`, a thin HTTP client for the standalone
LocateAnything sidecar (``scripts/locate_anything_sidecar.py``) — no heavy VLM
dependency enters the ``adare`` package.
"""

from __future__ import annotations

from .locate_anything import Detection, LocateAnythingClient

__all__ = ['Detection', 'LocateAnythingClient']
