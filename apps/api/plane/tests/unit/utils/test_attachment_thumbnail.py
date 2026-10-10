# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from io import BytesIO

import pytest
from PIL import Image

from plane.utils.attachment_thumbnail import ThumbnailUnavailable, render_thumbnail

pytestmark = pytest.mark.unit


def image_bytes(size=(1600, 1000), mode="RGB", format="PNG", **kwargs):
    output = BytesIO()
    Image.new(mode, size).save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize("size,expected", [((1600, 1000), (640, 400)), ((400, 1600), (160, 640)), ((80, 40), (80, 40))])
def test_resizes_without_cropping_or_upscaling(size, expected):
    with Image.open(BytesIO(render_thumbnail(image_bytes(size)))) as image:
        assert image.format == "WEBP"
        assert image.size == expected


def test_retains_transparency():
    with Image.open(BytesIO(render_thumbnail(image_bytes(mode="RGBA")))) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0


def test_rotates_using_exif_and_strips_metadata():
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private camera metadata"
    with Image.open(BytesIO(render_thumbnail(image_bytes((1200, 600), format="JPEG", exif=exif)))) as image:
        assert image.size == (320, 640)
        assert not image.getexif()


def test_animated_image_uses_only_first_frame():
    output = BytesIO()
    Image.new("RGB", (800, 400), "red").save(
        output, format="GIF", save_all=True, append_images=[Image.new("RGB", (800, 400), "blue")], duration=100
    )
    with Image.open(BytesIO(render_thumbnail(output.getvalue()))) as image:
        assert not getattr(image, "is_animated", False)
        assert image.size == (640, 320)
        red, _, blue = image.convert("RGB").getpixel((0, 0))
        assert red > 240 and blue < 10


@pytest.mark.parametrize("source", [b"not an image", b'<svg xmlns="http://www.w3.org/2000/svg"/>'])
def test_invalid_and_vector_images_are_rejected(source):
    with pytest.raises(ThumbnailUnavailable):
        render_thumbnail(source)


def test_limits_compressed_bytes_and_decoded_pixels(monkeypatch):
    monkeypatch.setattr("plane.utils.attachment_thumbnail.MAX_SOURCE_BYTES", 10)
    with pytest.raises(ThumbnailUnavailable):
        render_thumbnail(b"x" * 11)
    monkeypatch.setattr("plane.utils.attachment_thumbnail.MAX_SOURCE_BYTES", 1024 * 1024)
    monkeypatch.setattr("plane.utils.attachment_thumbnail.MAX_SOURCE_PIXELS", 100)
    with pytest.raises(ThumbnailUnavailable):
        render_thumbnail(image_bytes((11, 10)))
