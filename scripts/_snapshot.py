"""Shared frozen-snapshot cache for the data-ingestion scripts.

Every ingestion script in this directory (`ingest_*.py`, `resolve_synonyms.py`,
`extract_letermovir_ledger.py`) depends on a live external service: ADEME's
data-fair API, PubChem PUG REST, the ProBas/GEMIS soda4LCA node, the US Federal
LCA Commons, or a PDF host. None of those are under this project's control. An
endpoint can be restructured, rate-limited, put behind a login, or retired —
and when that happens, an ingestion script that only knows how to fetch live
stops working, and with it the ability to *reproduce* or *audit* the factor
tables already committed to `data/factors/` and `data/synonyms/`.

This module gives every ingestion script two interchangeable modes, selected
by a `--offline` flag the script exposes:

- **live** (default): fetch each URL from the network as usual, and — new —
  write the raw response into `data/raw/<source>/` before returning it. Every
  live run refreshes the frozen snapshot to match what it just saw.
- **offline** (`--offline`): touch no network at all. Read exclusively from
  whatever a previous live run wrote to `data/raw/<source>/`. A URL that was
  never cached raises :class:`SnapshotError` naming the missing URL — the
  script stops there rather than silently reaching for the network or
  inventing a response.

`data/raw/<source>/manifest.json` records, for every cached URL, the first and
most recent UTC timestamp it was fetched — the frozen snapshot's "as of" point,
readable without running anything. `Snapshot.describe()` prints it.

Rebuilding the snapshot (running live, so `--offline` stays current) is a
deliberate, occasional maintenance step, not something that happens on every
commit — see `docs/reproducibility.md`.

This is a development-time tool for the people maintaining the factor tables.
`carbonroute` itself never imports this module and never touches a socket,
which `tests/test_cli.py::test_no_networking_code_is_reachable` enforces by
parsing the import graph of `src/carbonroute/`, not by trusting a comment.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "data" / "raw"


_NOT_FOUND_SENTINEL = b"\x00carbonroute-snapshot-404\x00"


class SnapshotError(RuntimeError):
    """Raised in --offline mode when a URL was never cached, or on a live
    fetch failure — either way, the script should stop rather than guess."""


@dataclass
class Snapshot:
    """A durable, per-source cache of raw HTTP responses, in or out of git.

    Two Snapshot instances for the same ``source`` and ``root`` share the same
    files, so a live run and a later offline run of the same script agree.
    """

    source: str
    offline: bool
    root: Path = RAW_ROOT
    rate_limit_seconds: float = 0.0
    _last_call: float = field(default=0.0, init=False, repr=False)

    @property
    def dir(self) -> Path:
        d = self.root / self.source
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def manifest_path(self) -> Path:
        return self.dir / "manifest.json"

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _payload_path(self, url: str) -> Path:
        return self.dir / f"{self._key(url)}.bin"

    def _load_manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def fetch(
        self,
        url: str,
        *,
        headers: dict | None = None,
        timeout: int = 60,
        cache_key: str | None = None,
    ) -> bytes:
        """Return the raw bytes at ``url``, live-and-cached or frozen-replayed.

        A 404 is a legitimate, meaningful answer from services like PubChem
        ("this name is not a compound") and is frozen and replayed like any
        other response, re-raised as :class:`urllib.error.HTTPError` so
        existing ``except HTTPError`` call sites keep working unchanged in
        both modes. Any other network failure (DNS, timeout, connection
        refused) is never cached as if it meant something, and never silently
        retried as a different answer — it is a :class:`SnapshotError`.

        ``cache_key`` lets a caller index and label the cached response under
        a different, redacted string than the URL actually fetched — for an
        endpoint like the Federal LCA Commons API, where the real URL carries
        an ``api_key`` query parameter that must never be written into a
        manifest this repository commits. Pass the real URL with the key
        removed or replaced by a placeholder; the live fetch still uses the
        real ``url`` argument.
        """
        key_source = cache_key if cache_key is not None else url
        payload_path = self._payload_path(key_source)

        if self.offline:
            if not payload_path.exists():
                raise SnapshotError(
                    f"[{self.source}] --offline was requested but {url!r} was never "
                    f"snapshotted (expected {payload_path.relative_to(REPO_ROOT)}). "
                    "Run this script once without --offline to populate the snapshot, "
                    "or accept that this item cannot be reproduced offline right now."
                )
            data = payload_path.read_bytes()
            if data == _NOT_FOUND_SENTINEL:
                raise urllib.error.HTTPError(url, 404, "Not Found (frozen snapshot)", None, None)
            return data

        if self.rate_limit_seconds:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.rate_limit_seconds:
                time.sleep(self.rate_limit_seconds - elapsed)

        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            self._last_call = time.monotonic()
            if exc.code == 404:
                self._remember(key_source, _NOT_FOUND_SENTINEL)
            raise
        except urllib.error.URLError as exc:
            self._last_call = time.monotonic()
            raise SnapshotError(f"[{self.source}] live fetch of {url!r} failed: {exc}") from exc
        self._last_call = time.monotonic()

        self._remember(key_source, data)
        return data

    def _remember(self, key_source: str, data: bytes) -> None:
        payload_path = self._payload_path(key_source)
        payload_path.write_bytes(data)
        now = datetime.now(timezone.utc).isoformat()
        manifest = self._load_manifest()
        entry = manifest.setdefault(
            self._key(key_source), {"url": key_source, "first_retrieved": now}
        )
        entry["last_retrieved"] = now
        manifest[self._key(key_source)] = entry
        self._save_manifest(manifest)

    def fetch_json(
        self,
        url: str,
        *,
        headers: dict | None = None,
        timeout: int = 60,
        cache_key: str | None = None,
    ) -> dict:
        raw = self.fetch(url, headers=headers, timeout=timeout, cache_key=cache_key)
        return json.loads(raw.decode("utf-8"))

    def describe(self) -> str:
        manifest = self._load_manifest()
        if not manifest:
            return f"{self.source}: no cached responses"
        firsts = sorted(e["first_retrieved"] for e in manifest.values())
        lasts = sorted(e["last_retrieved"] for e in manifest.values())
        return (
            f"{self.source}: {len(manifest)} cached response(s), "
            f"snapshot spans {firsts[0]} .. {lasts[-1]} (UTC)"
        )


def add_offline_flag(parser) -> None:
    """Attach the standard ``--offline`` flag to an argparse parser."""
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Never touch the network. Replay only from data/raw/<source>/, "
        "the frozen snapshot from the last live run. Fails clearly, naming the "
        "missing URL, if something was never cached.",
    )


def describe_all() -> None:
    """Print the retrieval window of every snapshot under data/raw/. CLI entry point."""
    if not RAW_ROOT.is_dir():
        print("data/raw/ does not exist yet; no ingestion script has been run.")
        return
    for source_dir in sorted(p for p in RAW_ROOT.iterdir() if p.is_dir()):
        manifest_path = source_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest:
            print(f"{source_dir.name}: no cached responses")
            continue
        firsts = sorted(e["first_retrieved"] for e in manifest.values())
        lasts = sorted(e["last_retrieved"] for e in manifest.values())
        print(
            f"{source_dir.name}: {len(manifest)} cached response(s), "
            f"snapshot spans {firsts[0]} .. {lasts[-1]} (UTC)"
        )


if __name__ == "__main__":
    describe_all()
    sys.exit(0)
