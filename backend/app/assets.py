"""Local-only managed raster assets. No network acquisition or client import endpoint.

Trusted bundled fixtures enter via register_bytes; model output can only select an
existing candidate ID. Files are canonical raster encodings with content hashes.
No cleanup is performed: saved-lesson references must be retained indefinitely.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
import warnings
from PIL import Image
from .contracts import AssetRecord
from .errors import AppError

MAX_BYTES = 5_000_000
MAX_PIXELS = 8_000_000
MAX_DIMENSION = 4096
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "assets"

class Assets:
    def __init__(self, store):
        self.store = store
        self.root = store.data / "assets"
        if self.root.is_symlink():
            raise ValueError("Managed asset directory cannot be a symlink.")
        self.root.mkdir(exist_ok=True)
        with store.lock, store.db:
            store.db.executescript("""
            CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS asset_refs (asset_id TEXT, lesson_id TEXT, short_id TEXT,
                PRIMARY KEY(asset_id, lesson_id, short_id));
            """)

    def register_bytes(self, data, *, kind, original_source, creator, permission_basis,
                       attribution, source_context, illustrative, license_url=None, cancel=None):
        def checkpoint():
            if cancel is not None and cancel.is_set():
                from .errors import Cancelled
                raise Cancelled()
        checkpoint()
        # Validate rights before decoding and storage, never infer rights from a transcript URL.
        metadata = dict(kind=kind, original_source=original_source, creator=creator,
            permission_basis=permission_basis, attribution=attribution, source_context=source_context,
            illustrative=illustrative, license_url=license_url)
        AssetRecord(id="0"*64, content_hash="0"*64, mime_type="image/png", byte_size=1,
            width=1, height=1, managed_filename="0"*64+".png", acquired_at=time.time(), **metadata)
        if not 0 < len(data) <= MAX_BYTES:
            raise ValueError("Asset exceeds the 5 MB input limit.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                with Image.open(io.BytesIO(data), formats=("PNG", "JPEG")) as probe:
                    if probe.format not in {"PNG", "JPEG"} or getattr(probe, "n_frames", 1) != 1:
                        raise ValueError("Only single-frame PNG/JPEG assets are supported; SVG is rejected.")
                    w, h = probe.size
                    if max(w, h) > MAX_DIMENSION or w*h > MAX_PIXELS:
                        raise ValueError("Asset exceeds decoded dimension/pixel limits.")
                    probe.verify()
                checkpoint()
                with Image.open(io.BytesIO(data), formats=("PNG", "JPEG")) as image:
                    image.load()
                    # Strip EXIF, ancillary chunks and appended content; never serve originals.
                    output = io.BytesIO()
                    image.convert("RGB").save(output, format="PNG")
                    clean = output.getvalue()
            except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ValueError("Asset is not a valid bounded raster image.") from exc
        if len(clean) > MAX_BYTES:
            raise ValueError("Canonical asset exceeds the stored byte limit.")
        digest = hashlib.sha256(clean).hexdigest()
        record = AssetRecord(id=digest, content_hash=digest, mime_type="image/png", byte_size=len(clean),
            width=w, height=h, managed_filename=digest+".png", acquired_at=time.time(), status="ready", **metadata)
        checkpoint()
        # Serialise deduplication and record publication. Retries repair missing local files.
        with self.store.lock:
            if self.root.is_symlink():
                raise ValueError("Managed asset directory cannot be a symlink.")
            path = self.root / record.managed_filename
            if path.is_symlink():
                raise ValueError("Managed asset files cannot be symlinks.")
            with tempfile.NamedTemporaryFile(dir=self.root, suffix=".tmp", delete=False) as file:
                temp = Path(file.name)
                try:
                    file.write(clean)
                    file.flush()
                    os.fsync(file.fileno())
                    checkpoint()
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
            previous = self.store.db.execute("SELECT body FROM assets WHERE id=?", (digest,)).fetchone()
            if previous:
                record = AssetRecord.model_validate_json(previous[0]).model_copy(update={"status": "ready", "failure_reason": ""})
            with self.store.db:
                self.store.db.execute("INSERT OR REPLACE INTO assets VALUES (?,?)", (digest, record.model_dump_json()))
        return record

    def get(self, asset_id):
        if not re.fullmatch(r"[a-f0-9]{64}", asset_id):
            raise AppError("ASSET_NOT_FOUND", "Unknown managed asset ID.", 404)
        with self.store.lock:
            row = self.store.db.execute("SELECT body FROM assets WHERE id=?", (asset_id,)).fetchone()
        if row is None:
            raise AppError("ASSET_NOT_FOUND", "The managed image is missing. Retry lesson preparation.", 404)
        return AssetRecord.model_validate_json(row[0])

    def read(self, asset_id):
        record = self.get(asset_id)
        try:
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fd = os.open(record.managed_filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
            finally:
                os.close(root_fd)
            with os.fdopen(fd, "rb") as file:
                import stat
                info = os.fstat(file.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != record.byte_size:
                    raise OSError("Invalid asset file")
                data = file.read(MAX_BYTES+1)
            if hashlib.sha256(data).hexdigest() != record.content_hash:
                raise OSError("Asset checksum mismatch")
        except OSError:
            missing = record.model_copy(update={"status": "missing", "failure_reason": "Missing or corrupt local file; reinstall bundled fixtures and retry."})
            with self.store.lock, self.store.db:
                self.store.db.execute("UPDATE assets SET body=? WHERE id=?", (missing.model_dump_json(), asset_id))
            raise AppError("ASSET_MISSING", "This essential image is missing or corrupt. Restart to repair bundled assets, then retry the lesson.", 404) from None
        return data, record

    def attach(self, asset_id):
        _, record = self.read(asset_id)
        if record.status != "ready":
            raise AppError("ASSET_MISSING", "Repair the managed image before preparing this short.", 422)
        return record

    def reference(self, scenes, lesson_id, short_id):
        for scene in scenes:
            if scene.kind == "image":
                self.attach(scene.payload.asset_id)
                with self.store.lock, self.store.db:
                    self.store.db.execute("INSERT OR IGNORE INTO asset_refs VALUES (?,?,?)", (scene.payload.asset_id, lesson_id, short_id))

    def candidates(self):
        with self.store.lock:
            rows = self.store.db.execute("SELECT body FROM assets").fetchall()
        result = []
        for row in rows:
            record = AssetRecord.model_validate_json(row[0])
            try:
                result.append(self.attach(record.id).model_dump(exclude={"managed_filename"}))
            except AppError:
                continue
        return result

    def install_bundled(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        for item in manifest:
            name = item.pop("filename")
            if not re.fullmatch(r"[a-z0-9-]+\.png", name):
                raise ValueError("Invalid bundled fixture filename.")
            self.register_bytes((FIXTURES / name).read_bytes(), **item)
