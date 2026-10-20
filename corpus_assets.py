"""Validate, publish, and resolve public corpus images without editing source YAML."""

import copy
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

import yaml

BUCKET = "poemai-assets"
REGION = "eu-central-2"
CACHE_CONTROL = "public,max-age=31536000,immutable"
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/vnd.microsoft.icon",
    ".avif": "image/avif",
}
IMAGE_FIELDS = (
    ("bot_logo_url",),
    ("chat_title_image_url",),
    ("ui_settings", "case_manager", "case_manager_welcome_image_url"),
)
_logger = logging.getLogger(__name__)


def config_files(path):
    """Discover configuration YAML, never files inside an assets directory."""
    path = Path(path)
    return sorted(
        file
        for file in path.rglob("*")
        if file.suffix in {".yaml", ".yml"}
        and "assets" not in file.relative_to(path).parts
        and file.is_file()
    )


@dataclass(frozen=True)
class Asset:
    source: Path
    content: bytes
    key: str
    content_type: str

    @property
    def url(self):
        return f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{quote(self.key, safe='/')}"


@dataclass
class AssetPlan:
    assets: list
    replacements: dict

    def resolve(self, obj, filename):
        """Return a copy with references resolved using the original source file."""
        result = copy.deepcopy(obj)
        if not isinstance(result, dict):
            return result
        for field, urls in self.replacements.get(Path(filename).absolute(), {}).items():
            parent = result
            for part in field[:-1]:
                parent = parent.get(part, {}) if isinstance(parent, dict) else {}
            if not isinstance(parent, dict):
                continue
            value = parent.get(field[-1])
            url = urls.get(value) if isinstance(value, str) else None
            if url:
                parent[field[-1]] = url
                _logger.info("Resolved %s in %s to %s", ".".join(field), filename, url)
        return result

    def publish(self, s3_client):
        """Upload only; old content remains available for existing links/rollback."""
        for asset in self.assets:
            s3_client.put_object(
                Bucket=BUCKET,
                Key=asset.key,
                Body=asset.content,
                ContentType=asset.content_type,
                CacheControl=CACHE_CONTROL,
            )
            _logger.info(
                "Published %s to s3://%s/%s (%s)",
                asset.source,
                BUCKET,
                asset.key,
                asset.url,
            )


def prepare_corpus_assets(corpus_root, environment):
    """Validate an entire corpus tree before permitting any external writes.

    corpus_root is either the environment's corpus_keys directory or one corpus
    directory (used by temporary test deployments). No AWS calls are made here.
    """
    root = Path(corpus_root).absolute()
    if root.is_symlink():
        raise ValueError(f"Symlink corpus root is not supported: {root}")
    assets = []
    by_source = {}
    replacements = {}
    corpus_dirs = (
        [root]
        if any(
            (root / name).exists()
            for name in ("corpus_metadata.yaml", "corpus_metadata.yml")
        )
        else sorted(root.iterdir()) if root.exists() else []
    )
    for corpus in corpus_dirs:
        if corpus.is_symlink():
            raise ValueError(f"Symlink corpus directory is not supported: {corpus}")
        if not corpus.is_dir():
            continue
        asset_root = corpus / "assets"
        if asset_root.is_symlink():
            raise ValueError(f"Symlink assets directory is not supported: {asset_root}")
        if asset_root.exists():
            if not asset_root.is_dir():
                raise ValueError(f"Assets must be a directory: {asset_root}")
            for source in sorted(asset_root.rglob("*")):
                if source.is_symlink():
                    raise ValueError(f"Symlink asset is not supported: {source}")
                if source.is_dir():
                    continue
                if not source.is_file() or source.suffix.lower() not in MIME_TYPES:
                    raise ValueError(f"Unsupported asset file: {source}")
                if environment not in {"staging", "production"}:
                    raise ValueError(
                        "Corpus assets are supported only in staging and production"
                    )
                content = source.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                relative = source.relative_to(asset_root).as_posix()
                key = f"config/{environment}/corpus_keys/{corpus.name}/assets/{digest}/{relative}"
                asset = Asset(source, content, key, MIME_TYPES[source.suffix.lower()])
                assets.append(asset)
                by_source[source] = asset

        for metadata in (
            corpus / "corpus_metadata.yaml",
            corpus / "corpus_metadata.yml",
        ):
            if not metadata.exists():
                continue
            with metadata.open(encoding="utf-8") as stream:
                documents = list(yaml.safe_load_all(stream))
            for obj in documents:
                if not isinstance(obj, dict):
                    continue
                for field in IMAGE_FIELDS:
                    value = obj
                    for part in field:
                        value = value.get(part) if isinstance(value, dict) else None
                    if value is None or value == "":
                        continue
                    if not isinstance(value, str):
                        raise ValueError(
                            f"{metadata}: {'.'.join(field)} must be a URL or assets/... path"
                        )
                    if urlsplit(value).scheme or value.startswith("//"):
                        continue
                    if environment not in {"staging", "production"}:
                        raise ValueError(
                            f"{metadata}: relative asset references are supported only in staging and production"
                        )
                    relative = PurePosixPath(value)
                    if (
                        not value.startswith("assets/")
                        or ".." in relative.parts
                        or "\\" in value
                        or "?" in value
                        or "#" in value
                    ):
                        raise ValueError(
                            f"{metadata}: invalid asset reference {value!r}; use assets/<filename>"
                        )
                    source = corpus / relative
                    if source not in by_source:
                        raise ValueError(
                            f"{metadata}: missing or unsupported asset {value!r}"
                        )
                    replacements.setdefault(metadata.absolute(), {}).setdefault(
                        field, {}
                    )[value] = by_source[source].url
    return AssetPlan(assets, replacements)
