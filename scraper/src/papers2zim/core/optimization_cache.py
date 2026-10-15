"""Persistent, content-addressed cache for optimized assets.

Optimizing EPUB images and converting HTML images to WebP is CPU-heavy: a
full Gutenberg run spends hours re-encoding artwork. Project Gutenberg
rebuilds its files very frequently without changing the actual image bytes,
so keying a cache on a file's URL, ETag or modification date would be
invalidated on nearly every run and buy nothing (see issue #32).

Keying entries on a digest of the *input* bytes and the optimization
parameters avoids that problem entirely: an entry is reused only when the
image it was produced from is byte-identical, i.e. when re-running the
optimizer could only produce the same output. There is nothing to expire and
no invalidation policy to tune.

As in the other openZIM scrapers the entries live in an S3 bucket, given by
the ``--optimization-cache`` option (a URL carrying the credentials). The
cache is inactive unless that option is passed.
"""

import hashlib
import io
import json
from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any, Protocol

from kiwixstorage import KiwixStorage

from papers2zim.constants import logger
from papers2zim.core.utils import critical_error

_CACHE_FORMAT = "1"
_KEY_PREFIX = "optimized-assets"


def _zimscraperlib_version() -> str:
    """Version of the image-optimization library, part of every cache key.

    The output of an optimizer is a function of its own implementation as
    well as its input, so an upgraded zimscraperlib has to bypass entries
    produced by the previous one.
    """
    try:
        return package_version("zimscraperlib")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


_ZIMSCRAPERLIB_VERSION = _zimscraperlib_version()


class OptimizationStore(Protocol):
    """Backend holding optimized assets, addressed by their cache key."""

    def get(self, key: str) -> bytes | None: ...

    def put(self, key: str, content: bytes) -> None: ...


class _S3Client(Protocol):
    """Subset of `kiwixstorage.KiwixStorage` used to store cache entries."""

    def has_object(self, key: str) -> bool: ...

    def download_fileobj(self, key: str, fileobj: Any) -> None: ...

    def upload_fileobj(self, fileobj: Any, key: str) -> None: ...


class S3OptimizationStore:
    """Content-addressed cache stored in an S3 bucket via kiwixstorage."""

    def __init__(self, storage: _S3Client):
        self._storage = storage

    def get(self, key: str) -> bytes | None:
        buffer = io.BytesIO()
        try:
            if not self._storage.has_object(key):
                return None
            self._storage.download_fileobj(key, buffer)
        except Exception as exc:
            logger.warning(f"Failed to read {key} from optimization cache: {exc}")
            return None
        return buffer.getvalue()

    def put(self, key: str, content: bytes) -> None:
        try:
            self._storage.upload_fileobj(io.BytesIO(content), key)
        except Exception as exc:
            logger.warning(f"Failed to write {key} to optimization cache: {exc}")


def open_s3_store(url: str) -> S3OptimizationStore:
    """Build a validated S3-backed store from an ``--optimization-cache`` URL."""
    storage = KiwixStorage(url)
    if not storage.check_credentials(
        list_buckets=True, bucket=True, write=True, read=True, failsafe=True
    ):
        critical_error(
            f"Unable to use bucket {storage.bucket_name} at {storage.url.netloc} "
            "as optimization cache: credentials check failed"
        )
    logger.info(f"Optimization cache enabled on bucket {storage.bucket_name}")
    return S3OptimizationStore(storage)


class _CacheState:
    store: OptimizationStore | None = None


_state = _CacheState()


def configure(store: OptimizationStore | None) -> None:
    """Use `store` for subsequent lookups, or disable the cache when `None`."""
    _state.store = store


def get_or_compute(
    source: bytes,
    options: Mapping[str, object],
    compute: Callable[[], bytes],
) -> bytes:
    """Return the optimized form of `source`, computing it on a cache miss.

    `options` captures the optimization parameters: two calls sharing a
    `source` but not the `options` are cached separately. `compute` is only
    invoked when no usable entry exists.
    """
    store = _state.store
    if store is None:
        return compute()
    key = _cache_key(source, options)
    cached = store.get(key)
    if cached is not None:
        return cached
    optimized = compute()
    store.put(key, optimized)
    return optimized


def _cache_key(source: bytes, options: Mapping[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(_CACHE_FORMAT.encode())
    digest.update(_ZIMSCRAPERLIB_VERSION.encode())
    digest.update(source)
    digest.update(b"\x00")
    digest.update(json.dumps(options, sort_keys=True, default=repr).encode("utf-8"))
    return f"{_KEY_PREFIX}/{digest.hexdigest()}"
