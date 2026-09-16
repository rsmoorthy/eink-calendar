"""Management of the day/addl image files used by the renderer.

Images live in a single flat directory under assets/. Uploads are validated by
content rather than by extension, and filenames are restricted so an upload
cannot overwrite something outside that directory.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from renderer import DAY_IMAGE_DIR, SHIPPED_ASSETS_DIR, default_assets_dir

# Files the renderer relies on by name; these cannot be deleted from the UI.
PROTECTED = ("sun", "mon", "tue", "wed", "thu", "fri", "sat", "special")

ALLOWED_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

# Conservative filename rule: letters, digits, dash, underscore, dot. This keeps
# names usable as both an HTTP path segment and a filesystem path.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

MAX_DIMENSION = 2000


class AssetError(ValueError):
    """Raised for an invalid upload or asset operation."""


def prepare_assets_dir(target: Path | None = None) -> Path:
    """Return the writable assets directory, seeding it from the image once.

    Files that already exist are left alone so a re-upload or a hand-edited
    icon is not overwritten on restart.
    """
    directory = Path(target) if target else default_assets_dir()
    day_dir = directory / DAY_IMAGE_DIR
    day_dir.mkdir(parents=True, exist_ok=True)

    shipped = SHIPPED_ASSETS_DIR / DAY_IMAGE_DIR
    if shipped.exists() and shipped.resolve() != day_dir.resolve():
        for source in shipped.iterdir():
            destination = day_dir / source.name
            if source.is_file() and not destination.exists():
                shutil.copy2(source, destination)
    return directory


@dataclass
class AssetInfo:
    name: str
    width: int
    height: int
    size_bytes: int
    protected: bool

    @property
    def resolution(self) -> str:
        return f"{self.width} x {self.height}"


def normalise_name(raw: str) -> str:
    """Validate an image name and ensure it carries a known extension."""
    name = (raw or "").strip()
    if not name:
        raise AssetError("Image name is required.")
    if len(name) > 120:
        raise AssetError("Image name is too long.")
    if not NAME_RE.match(name):
        raise AssetError(
            "Image name may only contain letters, digits, dot, dash and "
            "underscore, and must start with a letter or digit."
        )
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        name = f"{name}.png"
    if not NAME_RE.match(name):
        raise AssetError("Image name is not valid.")
    return name


class AssetStore:
    """Reads and writes the images in ``day_dir``."""

    def __init__(self, day_dir: Path) -> None:
        self.day_dir = Path(day_dir)

    # ------------------------------------------------------------------- reads
    def path_for(self, name: str) -> Path:
        """Resolve a stored image name to a path inside the asset directory."""
        stem = Path((name or "").strip()).name
        if not stem:
            raise AssetError("Image name is required.")
        if not Path(stem).suffix:
            stem = f"{stem}.png"
        candidate = (self.day_dir / stem).resolve()
        # Guard against traversal even though names are validated on upload.
        if self.day_dir.resolve() not in candidate.parents:
            raise AssetError("Image name escapes the asset directory.")
        return candidate

    def list(self) -> list[AssetInfo]:
        """All images, newest first, with their real pixel dimensions."""
        if not self.day_dir.exists():
            return []

        found: list[tuple[float, AssetInfo]] = []
        for path in self.day_dir.iterdir():
            if not path.is_file():
                continue
            try:
                with Image.open(path) as handle:
                    width, height = handle.size
            except Exception:
                # A file that is not a readable image is still listed, but with
                # unknown dimensions, rather than breaking the whole page.
                width = height = 0
            found.append(
                (
                    path.stat().st_mtime,
                    AssetInfo(
                        name=path.name,
                        width=width,
                        height=height,
                        size_bytes=path.stat().st_size,
                        protected=self.is_protected(path.name),
                    ),
                )
            )

        found.sort(key=lambda item: item[0], reverse=True)
        return [info for _, info in found]

    def exists(self, name: str) -> bool:
        try:
            return self.path_for(name).exists()
        except AssetError:
            return False

    @staticmethod
    def is_protected(name: str) -> bool:
        """Whether the weekday/default artwork that firmware expects to find."""
        return Path(name).stem.lower() in PROTECTED

    # ------------------------------------------------------------------ writes
    def save(self, raw_name: str, data: bytes, overwrite: bool = True) -> AssetInfo:
        """Validate and store an uploaded image.

        The file is opened to confirm it really is an image and to reject
        oversized images, rather than trusting the browser's content type.
        """
        name = normalise_name(raw_name)
        if not data:
            raise AssetError("The uploaded file is empty.")

        import io

        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            # verify() consumes the object, so reopen to read the size.
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
        except Exception as exc:
            raise AssetError(f"Not a readable image: {exc}") from exc

        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise AssetError(
                f"Image is {width}x{height}; the maximum allowed side is "
                f"{MAX_DIMENSION}px."
            )

        self.day_dir.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(name)
        if destination.exists() and not overwrite:
            raise AssetError(f"{name} already exists.")
        destination.write_bytes(data)
        return AssetInfo(
            name=name,
            width=width,
            height=height,
            size_bytes=len(data),
            protected=self.is_protected(name),
        )

    def delete(self, name: str) -> None:
        """Remove an image, refusing the ones the default layout depends on."""
        path = self.path_for(name)
        if self.is_protected(path.name):
            raise AssetError(
                f"{path.name} is used by the default layout and cannot be deleted."
            )
        if not path.exists():
            raise AssetError(f"{path.name} does not exist.")
        path.unlink()
