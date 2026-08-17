"""Vercel Python serverless entrypoint.

Vercel treats each file under `api/` as a function and serves an ASGI app
exported as `app`. Everything else lives in `src/`; this module only re-exports
the FastAPI application so the deployment target stays a one-line file.

Deploy this directory as its own Vercel project with the repository root as the
project root (see vercel.json). The Next.js frontend deploys separately with
`web/` as its root.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Vercel executes this file with the project root on the path already, but a
# local `vercel dev` run and some build steps do not guarantee it.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.api import app  # noqa: E402

__all__ = ["app"]
