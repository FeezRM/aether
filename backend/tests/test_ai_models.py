import ast
import hashlib
import io
import time
from pathlib import Path

import pytest

from app.ai import models

PAYLOAD = b"GGUF" + b"\0" * 5000


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(models, "downloads", models.Downloads())
    return tmp_path


class FakeOpener:
    """Stands in for urllib's opener; reports a hash the way Hugging Face's redirect does."""

    def __init__(self, handlers, payload=PAYLOAD, etag=None):
        self.handlers, self.payload = handlers, payload
        self.etag = hashlib.sha256(payload).hexdigest() if etag is None else etag
        self.urls = []

    def open(self, url, timeout=None):
        self.urls.append(url)
        if self.etag:
            self.handlers[0].linked["X-Linked-Etag"] = self.etag
        return io.BytesIO(self.payload)


def use_opener(monkeypatch, **kw):
    made = []

    def build(*handlers):
        made.append(FakeOpener(handlers, **kw))
        return made[-1]

    monkeypatch.setattr(models.urllib.request, "build_opener", build)
    return made


def install(tier_id):
    for f in models.TIERS[tier_id].files:
        f.path.write_bytes(b"x")


def test_nothing_installed(models_dir):
    st = models.status()
    assert [t["id"] for t in st["tiers"]] == ["lite", "standard"]
    assert not any(t["installed"] for t in st["tiers"]) and st["active"] is None
    assert st["recommended"] in ("lite", "standard")


def test_installed_tier_becomes_active_and_choice_is_remembered(models_dir):
    install("lite")
    assert models.active_tier() == "lite"
    with pytest.raises(ValueError, match="not downloaded"):
        models.set_active("standard")
    install("standard")
    models.set_active("standard")
    assert models.active_tier() == "standard"
    models.set_active("lite")
    assert models.active_tier() == "lite"


def test_delete_keeps_files_another_tier_uses(models_dir):
    install("lite")
    install("standard")
    models.delete("lite")
    assert not models.TIERS["lite"].chat.path.exists()
    assert models.EMBED.path.exists() and models.installed("standard")
    models.delete("standard")
    assert not models.EMBED.path.exists()


def test_download_verifies_the_reported_checksum(models_dir, monkeypatch):
    use_opener(monkeypatch)
    f = models.ModelFile("org/repo", "m.gguf", len(PAYLOAD))
    seen = []
    models.fetch(f, seen.append, lambda: False)
    assert f.path.read_bytes() == PAYLOAD and sum(seen) == len(PAYLOAD)


def test_pinned_checksum_wins_and_a_mismatch_is_discarded(models_dir, monkeypatch):
    use_opener(monkeypatch)
    f = models.ModelFile("org/repo", "m.gguf", 1, sha256="0" * 64)
    with pytest.raises(models.DownloadError, match="checksum"):
        models.fetch(f, lambda n: None, lambda: False)
    assert list(models_dir.iterdir()) == []


def test_download_without_any_checksum_is_refused(models_dir, monkeypatch):
    use_opener(monkeypatch, etag="")
    with pytest.raises(models.DownloadError, match="No checksum"):
        models.fetch(models.ModelFile("org/repo", "m.gguf", 1), lambda n: None, lambda: False)
    assert list(models_dir.iterdir()) == []


def test_tier_download_job_fetches_missing_files(models_dir, monkeypatch):
    made = use_opener(monkeypatch)
    models.EMBED.path.write_bytes(b"already here")
    job = models.downloads.start("lite")
    for _ in range(100):
        if job.state != "downloading":
            break
        time.sleep(0.02)
    assert job.state == "done", job.error
    assert [o.urls[0] for o in made] == [models.TIERS["lite"].chat.url]
    assert models.installed("lite") and models.EMBED.path.read_bytes() == b"already here"


def test_cancel_stops_a_download(models_dir, monkeypatch):
    use_opener(monkeypatch)
    f = models.ModelFile("org/repo", "m.gguf", 1)
    with pytest.raises(models.DownloadError, match="cancelled"):
        models.fetch(f, lambda n: None, lambda: True)
    assert not f.path.exists()


def test_models_api(client, models_dir):
    body = client.get("/api/ai/models").json()
    assert {"tiers", "recommended", "ram", "active", "runtime"} <= body.keys()
    assert client.post("/api/ai/models/huge/download").status_code == 400
    assert client.post("/api/ai/models/lite/activate").status_code == 400
    install("lite")
    assert client.post("/api/ai/models/lite/activate").json()["active"] == "lite"
    assert client.delete("/api/ai/models/lite").json()["active"] is None


# ---------------------------------------------------------------- privacy --

NETWORK_PACKAGES = {"socket", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "websockets"}
# urllib.parse only manipulates strings, so it is allowed.
NETWORK_MODULES = {"urllib", "urllib.request", "http", "http.client"}


def test_only_the_model_downloader_can_use_the_network():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in NETWORK_PACKAGES or name in NETWORK_MODULES:
                    offenders.append(f"{path.relative_to(app_dir)}: {name}")
    assert offenders == ["ai/models.py: urllib.request"]


def test_models_load_from_local_files_only():
    source = (Path(models.__file__).with_name("runtime.py")).read_text()
    assert "from_pretrained" not in source and "model_path=str(tier." in source
