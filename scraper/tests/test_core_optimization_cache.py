"""Tests for the content-addressed optimization cache."""

import io

import pytest
from PIL import Image

from papers2zim.core import epub_optimizer, optimization_cache
from papers2zim.core.optimization_cache import S3OptimizationStore
from papers2zim.core.rewriters import image_rewriter
from papers2zim.core.utils import CriticalError


class _FakeStorage:
    """Minimal stand-in for `kiwixstorage.KiwixStorage`."""

    def __init__(self, objects=None):
        self.objects = dict(objects or {})

    def has_object(self, key):
        return key in self.objects

    def download_fileobj(self, key, fileobj):
        fileobj.write(self.objects[key])

    def upload_fileobj(self, fileobj, key):
        self.objects[key] = fileobj.read()


class _BrokenStorage:
    """Stand-in whose S3 calls all blow up."""

    def has_object(self, _key):
        raise RuntimeError("boom")

    def download_fileobj(self, _key, _fileobj):
        raise RuntimeError("boom")

    def upload_fileobj(self, _fileobj, _key):
        raise RuntimeError("boom")


def _store(storage=None) -> S3OptimizationStore:
    return S3OptimizationStore(storage or _FakeStorage())


def _jpeg_bytes(size: tuple[int, int] = (16, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="JPEG")
    return buffer.getvalue()


def _counter():
    calls: list[None] = []

    def compute() -> bytes:
        calls.append(None)
        return b"optimized"

    return calls, compute


def test_disabled_cache_computes_every_time():
    calls, compute = _counter()

    assert (
        optimization_cache.get_or_compute(b"source", {"q": 1}, compute) == b"optimized"
    )
    assert (
        optimization_cache.get_or_compute(b"source", {"q": 1}, compute) == b"optimized"
    )
    assert len(calls) == 2


def test_store_roundtrips_and_reports_misses():
    store = _store()

    assert store.get("optimized-assets/missing") is None
    store.put("optimized-assets/present", b"payload")
    assert store.get("optimized-assets/present") == b"payload"


def test_store_ignores_storage_failures():
    store = _store(_BrokenStorage())

    assert store.get("optimized-assets/any") is None
    store.put("optimized-assets/any", b"payload")


def test_enabled_cache_reuses_entry_for_identical_input():
    optimization_cache.configure(_store())
    calls, compute = _counter()

    optimization_cache.get_or_compute(b"source", {"q": 1}, compute)
    optimization_cache.get_or_compute(b"source", {"q": 1}, compute)

    assert len(calls) == 1


def test_cache_distinguishes_source_content():
    optimization_cache.configure(_store())

    first = optimization_cache.get_or_compute(b"first", {}, lambda: b"first-out")
    second = optimization_cache.get_or_compute(b"second", {}, lambda: b"second-out")

    assert first == b"first-out"
    assert second == b"second-out"


def test_cache_distinguishes_options():
    optimization_cache.configure(_store())

    wide = optimization_cache.get_or_compute(b"same", {"max_width": 400}, lambda: b"w")
    narrow = optimization_cache.get_or_compute(
        b"same", {"max_width": 200}, lambda: b"n"
    )

    assert wide == b"w"
    assert narrow == b"n"


def test_cache_survives_a_new_store_instance():
    storage = _FakeStorage()
    optimization_cache.configure(S3OptimizationStore(storage))
    optimization_cache.get_or_compute(b"image", {"q": 1}, lambda: b"cached")

    optimization_cache.configure(S3OptimizationStore(storage))
    calls, compute = _counter()

    result = optimization_cache.get_or_compute(b"image", {"q": 1}, compute)

    assert result == b"cached"
    assert calls == []


def test_empty_optimization_is_a_valid_entry():
    optimization_cache.configure(_store())
    calls: list[None] = []

    def compute() -> bytes:
        calls.append(None)
        return b""

    assert optimization_cache.get_or_compute(b"image", {}, compute) == b""
    assert optimization_cache.get_or_compute(b"image", {}, compute) == b""
    assert len(calls) == 1


def test_configure_none_disables_a_previously_enabled_cache():
    optimization_cache.configure(_store())
    optimization_cache.get_or_compute(b"image", {}, lambda: b"cached")
    optimization_cache.configure(None)
    calls, compute = _counter()

    assert optimization_cache.get_or_compute(b"image", {}, compute) == b"optimized"
    assert len(calls) == 1


def test_open_s3_store_validates_credentials(monkeypatch):
    created: dict = {}

    class _FakeKiwixStorage:
        def __init__(self, url):
            created["url"] = url
            self.bucket_name = "bucket"

        def check_credentials(self, **kwargs):
            created["kwargs"] = kwargs
            return True

    monkeypatch.setattr(optimization_cache, "KiwixStorage", _FakeKiwixStorage)

    store = optimization_cache.open_s3_store("s3://key:secret@host/bucket")

    assert isinstance(store, S3OptimizationStore)
    assert created["url"] == "s3://key:secret@host/bucket"
    assert created["kwargs"] == {
        "list_buckets": True,
        "bucket": True,
        "write": True,
        "read": True,
        "failsafe": True,
    }


def test_open_s3_store_rejects_bad_credentials(monkeypatch):
    class _FakeKiwixStorage:
        def __init__(self, _url):
            self.bucket_name = "bucket"
            self.url = type("U", (), {"netloc": "host"})()

        def check_credentials(self, **_kwargs):
            return False

    monkeypatch.setattr(optimization_cache, "KiwixStorage", _FakeKiwixStorage)

    with pytest.raises(CriticalError, match="credentials check failed"):
        optimization_cache.open_s3_store("s3://key:secret@host/bucket")


def test_image_processor_reuses_cached_webp(monkeypatch):
    optimization_cache.configure(_store())
    conversions: list[object] = []
    real_open = image_rewriter.pilopen

    def counting_open(source):
        conversions.append(source)
        return real_open(source)

    monkeypatch.setattr(image_rewriter, "pilopen", counting_open)

    image = _jpeg_bytes()
    first = image_rewriter.ImageProcessor.optimize_image_content(image)
    second = image_rewriter.ImageProcessor.optimize_image_content(image)

    assert first == second
    assert len(conversions) == 1


def test_epub_image_members_are_cached(monkeypatch, make_epub):
    optimization_cache.configure(_store())
    calls: list[None] = []

    def counting(*, src, dst):
        calls.append(None)
        dst.write(src.read())

    monkeypatch.setitem(epub_optimizer._IMAGE_OPTIMIZERS, ".jpg", counting)

    epub = make_epub()
    epub_optimizer.optimize_epub_bytes(epub)
    epub_optimizer.optimize_epub_bytes(epub)

    assert len(calls) == 1
