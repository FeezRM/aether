"""Model tiers, and the one place Aether can reach the internet.

The assistant runs on GGUF model files read from MODELS_DIR. They arrive only
when the user clicks Download for a tier; nothing here runs on its own, and
everything else in the app works from the files on disk with no network.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODELS_DIR = Path(os.environ.get("AETHER_MODELS_DIR", "~/.aether/models")).expanduser()
CHUNK = 1 << 20
GB = 1024 ** 3


@dataclass(frozen=True)
class ModelFile:
    repo: str
    filename: str
    approx_size: int
    # Pinned SHA-256 of the file. When None, the hash Hugging Face reports for the file
    # (its X-Linked-Etag header) is checked instead; scripts/pin_models.py fills these in.
    sha256: str | None = None
    revision: str = "main"

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}"

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.filename


@dataclass(frozen=True)
class Tier:
    id: str
    label: str
    description: str
    chat: ModelFile
    embed: ModelFile
    n_ctx: int
    # Below this much RAM the tier is not recommended.
    min_ram_gb: int

    @property
    def files(self) -> list[ModelFile]:
        return [self.chat, self.embed]


EMBED = ModelFile("CompendiumLabs/bge-small-en-v1.5-gguf", "bge-small-en-v1.5-q8_0.gguf", 36_000_000)

TIERS: dict[str, Tier] = {
    "lite": Tier(
        "lite", "Lite", "Fast on any computer. Answers questions and makes simple edits.",
        ModelFile("LiquidAI/LFM2-1.2B-GGUF", "LFM2-1.2B-Q4_K_M.gguf", 731_000_000),
        EMBED, n_ctx=8192, min_ram_gb=8,
    ),
    "standard": Tier(
        "standard", "Standard", "Better reasoning and multi-step edits. Needs 16 GB of memory.",
        ModelFile("unsloth/Qwen3-4B-Instruct-2507-GGUF", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", 2_500_000_000),
        EMBED, n_ctx=16384, min_ram_gb=12,
    ),
}


def total_ram() -> int:
    """Physical memory in bytes, or 0 if it cannot be read."""
    try:
        if sys.platform == "win32":
            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("pagefile", ctypes.c_ulonglong), ("availpagefile", ctypes.c_ulonglong),
                            ("virtual", ctypes.c_ulonglong), ("availvirtual", ctypes.c_ulonglong),
                            ("extended", ctypes.c_ulonglong)]
            st = Status(length=ctypes.sizeof(Status))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return int(st.total)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return 0


def recommended_tier() -> str:
    ram = total_ram()
    return "standard" if ram >= TIERS["standard"].min_ram_gb * GB else "lite"


def installed(tier_id: str) -> bool:
    return all(f.path.is_file() for f in TIERS[tier_id].files)


# -------------------------------------------------------------- settings --

def _settings_path() -> Path:
    return MODELS_DIR / "settings.json"


def active_tier() -> str | None:
    """The chosen tier if installed, else the best installed one, else None."""
    try:
        chosen = json.loads(_settings_path().read_text()).get("active")
    except (OSError, ValueError):
        chosen = None
    if chosen in TIERS and installed(chosen):
        return chosen
    preferred = [recommended_tier(), "lite", "standard"]
    return next((t for t in preferred if installed(t)), None)


def set_active(tier_id: str) -> None:
    if tier_id not in TIERS:
        raise ValueError(f"Unknown model tier {tier_id!r}")
    if not installed(tier_id):
        raise ValueError(f"{TIERS[tier_id].label} is not downloaded yet")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    _settings_path().write_text(json.dumps({"active": tier_id}))


def delete(tier_id: str) -> None:
    tier = TIERS[tier_id]
    shared = {f.filename for t in TIERS.values() if t.id != tier_id and installed(t.id) for f in t.files}
    for f in tier.files:
        if f.filename not in shared:
            f.path.unlink(missing_ok=True)


# ------------------------------------------------------------- downloads --

class DownloadError(Exception):
    pass


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Remember the hash and size Hugging Face reports before redirecting to its file store."""

    def __init__(self) -> None:
        self.linked: dict[str, str] = {}

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        for key in ("X-Linked-Etag", "X-Linked-Size"):
            if headers.get(key) and key not in self.linked:
                self.linked[key] = headers[key].strip('"')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(f: ModelFile, progress, cancelled) -> None:
    """Download one file to MODELS_DIR, verifying its SHA-256 before it is used.

    `progress(n)` is called with each chunk's byte count; `cancelled()` stops the download.
    """
    redirects = _Redirects()
    opener = urllib.request.build_opener(redirects)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    part = f.path.with_name(f.path.name + ".part")
    digest = hashlib.sha256()
    try:
        with opener.open(f.url, timeout=60) as res, part.open("wb") as out:
            while chunk := res.read(CHUNK):
                if cancelled():
                    raise DownloadError("Download cancelled")
                digest.update(chunk)
                out.write(chunk)
                progress(len(chunk))
        expected = f.sha256 or redirects.linked.get("X-Linked-Etag")
        if not expected or len(expected) != 64:
            raise DownloadError(f"No checksum available to verify {f.filename}")
        if digest.hexdigest() != expected.lower():
            raise DownloadError(f"{f.filename} failed its checksum; the download was discarded")
        part.replace(f.path)
    except OSError as exc:
        raise DownloadError(f"Could not download {f.filename}: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)


@dataclass
class Download:
    tier: str
    total: int
    received: int = 0
    state: str = "downloading"  # downloading | done | error | cancelled
    error: str | None = None
    cancel: bool = False


class Downloads:
    def __init__(self) -> None:
        self._jobs: dict[str, Download] = {}
        self._lock = threading.Lock()

    def get(self, tier_id: str) -> Download | None:
        return self._jobs.get(tier_id)

    def start(self, tier_id: str) -> Download:
        tier = TIERS.get(tier_id)
        if tier is None:
            raise ValueError(f"Unknown model tier {tier_id!r}")
        with self._lock:
            job = self._jobs.get(tier_id)
            if job and job.state == "downloading":
                return job
            todo = [f for f in tier.files if not f.path.is_file()]
            job = Download(tier_id, total=sum(f.approx_size for f in todo))
            self._jobs[tier_id] = job
        threading.Thread(target=self._run, args=(job, todo), daemon=True).start()
        return job

    def cancel(self, tier_id: str) -> None:
        job = self._jobs.get(tier_id)
        if job:
            job.cancel = True

    def _run(self, job: Download, todo: list[ModelFile]) -> None:
        def progress(n: int) -> None:
            job.received += n
            job.total = max(job.total, job.received)

        try:
            for f in todo:
                fetch(f, progress, lambda: job.cancel)
            job.state = "done"
        except DownloadError as exc:
            job.state = "cancelled" if job.cancel else "error"
            job.error = None if job.cancel else str(exc)


downloads = Downloads()


def status() -> dict:
    active = active_tier()
    tiers = []
    for t in TIERS.values():
        job = downloads.get(t.id)
        tiers.append({
            "id": t.id, "label": t.label, "description": t.description,
            "size": sum(f.approx_size for f in t.files), "installed": installed(t.id),
            "active": t.id == active,
            "download": None if job is None else {
                "state": job.state, "received": job.received, "total": job.total, "error": job.error,
            },
        })
    return {"tiers": tiers, "recommended": recommended_tier(), "ram": total_ram(), "active": active}
