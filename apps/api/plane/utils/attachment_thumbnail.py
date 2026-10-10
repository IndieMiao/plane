# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from hashlib import sha256
from io import BytesIO
import warnings

from django.core.cache import cache
from PIL import Image, ImageOps, UnidentifiedImageError

from plane.settings.storage import S3Storage

THUMBNAIL_SIZE = 640
THUMBNAIL_CACHE_SECONDS = 24 * 60 * 60
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
SUPPORTED_FORMATS = ("PNG", "JPEG", "GIF", "WEBP", "AVIF", "BMP", "ICO", "TIFF")


class ThumbnailUnavailable(ValueError):
    pass


def render_thumbnail(source):
    """Decode a bounded raster image and return a static, metadata-free WebP."""
    if len(source) > MAX_SOURCE_BYTES:
        raise ThumbnailUnavailable("Image is too large to thumbnail.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(source), formats=SUPPORTED_FORMATS) as image:
                if image.width * image.height > MAX_SOURCE_PIXELS:
                    raise ThumbnailUnavailable("Image has too many pixels to thumbnail.")
                # Decode only the first frame of animations; use JPEG draft decoding when available.
                image.seek(0)
                image.draft("RGB", (THUMBNAIL_SIZE, THUMBNAIL_SIZE))
                normalized = ImageOps.exif_transpose(image)
                normalized.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
                mode = "RGBA" if "A" in normalized.getbands() or "transparency" in normalized.info else "RGB"
                thumbnail = normalized.convert(mode)
                thumbnail.info.clear()
                output = BytesIO()
                thumbnail.save(output, format="WEBP", quality=80, method=4)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ThumbnailUnavailable("This image cannot be thumbnailed.") from exc


def get_attachment_thumbnail(asset):
    """Share generated thumbnails across API workers without changing originals or the database."""
    source_version = f"{asset.asset.name}:{asset.size}:{(asset.storage_metadata or {}).get('ETag', '')}"
    key = f"attachment-thumbnail:v1:{asset.id}:{sha256(source_version.encode()).hexdigest()}"
    cached = cache.get(key)
    if cached is not None:
        if not cached:
            raise ThumbnailUnavailable("This image cannot be thumbnailed.")
        return cached

    try:
        if asset.size > MAX_SOURCE_BYTES:
            raise ThumbnailUnavailable("Image is too large to thumbnail.")
        # Use the internal storage endpoint, never a URL supplied by the client.
        storage = S3Storage()
        obj = storage.s3_client.get_object(Bucket=storage.aws_storage_bucket_name, Key=asset.asset.name)
        body = obj["Body"]
        try:
            if obj.get("ContentLength", 0) > MAX_SOURCE_BYTES:
                raise ThumbnailUnavailable("Image is too large to thumbnail.")
            source = body.read(MAX_SOURCE_BYTES + 1)
        finally:
            body.close()
        thumbnail = render_thumbnail(source)
    except ThumbnailUnavailable:
        # Avoid repeatedly downloading invalid/unsupported images, including SVGs.
        cache.set(key, b"", timeout=60 * 60)
        raise

    cache.set(key, thumbnail, timeout=THUMBNAIL_CACHE_SECONDS)
    return thumbnail
