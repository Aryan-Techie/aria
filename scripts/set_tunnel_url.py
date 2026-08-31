"""Rewrite PUBLIC_BASE_URL in the root .env.

Exists as a file rather than an inline `python -c` inside run.bat because the
regex needs `^`, `$` and quotes, and cmd.exe mangles all three in different
ways depending on whether delayed expansion is on. A script takes one plain
argument and cannot be mis-escaped.

    python scripts/set_tunnel_url.py https://something.trycloudflare.com

The backend caches settings with lru_cache, so it must be RESTARTED after
this runs - editing .env alone changes nothing.
"""
from __future__ import annotations

import io
import pathlib
import re
import sys

KEY = "PUBLIC_BASE_URL"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {pathlib.Path(sys.argv[0]).name} <https://...>", file=sys.stderr)
        return 2

    url = sys.argv[1].strip().rstrip("/")
    if not url.startswith("https://"):
        print(f"refusing to write a non-https URL: {url!r}", file=sys.stderr)
        return 2

    env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        print(f"no .env at {env_path}", file=sys.stderr)
        return 1

    text = io.open(env_path, encoding="utf-8").read()
    line = f"{KEY}={url}"

    if re.search(rf"(?m)^{KEY}=", text):
        text = re.sub(rf"(?m)^{KEY}=.*$", line, text, count=1)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"

    io.open(env_path, "w", encoding="utf-8").write(text)
    print(f"{KEY} -> {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
