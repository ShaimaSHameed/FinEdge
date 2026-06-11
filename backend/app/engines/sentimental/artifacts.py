import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.utils.logger import get_logger


logger = get_logger(__name__)


class SentimentalArtifactStore:
    REQUIRED_FIELDS = {
        "ticker",
        "market",
        "as_of",
        "overall_sentiment",
        "score",
        "news_breakdown",
        "trend",
        "confidence",
        "analysis_summary",
        "influential_articles",
    }

    def load_latest(self, ticker: str, market: str) -> dict[str, Any] | None:
        normalized_ticker = ticker.upper()
        normalized_market = market.upper()

        for root in self._artifact_roots():
            artifact_path = root / "latest" / f"{normalized_ticker}.json"
            if not artifact_path.exists():
                continue

            try:
                with artifact_path.open("r", encoding="utf-8") as handle:
                    artifact = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to read sentimental artifact {artifact_path}: {exc}")
                continue

            self._validate_artifact(artifact, artifact_path)
            age_hours = self._artifact_age_hours(artifact_path.stat().st_mtime)
            if (
                age_hours is not None
                and age_hours > settings.SENTIMENTAL_MAX_ARTIFACT_AGE_HOURS
            ):
                raise ValueError(
                    f"Sentimental model artifact {artifact_path} is stale "
                    f"({age_hours}h old; max {settings.SENTIMENTAL_MAX_ARTIFACT_AGE_HOURS}h)."
                )

            artifact_ticker = str(artifact.get("ticker", "")).upper()
            artifact_market = str(artifact.get("market", "")).upper()
            if artifact_ticker != normalized_ticker:
                raise ValueError(
                    f"Sentimental artifact {artifact_path} is for {artifact_ticker}, not {normalized_ticker}."
                )
            if artifact_market != normalized_market:
                raise ValueError(
                    f"Sentimental artifact {artifact_path} is for market {artifact_market}, not {normalized_market}."
                )

            artifact["_artifact_path"] = str(artifact_path)
            return artifact

        return None

    def artifact_status(self) -> dict[str, Any]:
        configured_root = Path(settings.SENTIMENTAL_ARTIFACT_DIR)
        roots = list(self._artifact_roots())
        latest_dirs = [root / "latest" for root in roots]
        manifests = [latest_dir / "manifest.json" for latest_dir in latest_dirs]
        artifact_files = self._latest_artifact_files(latest_dirs)
        manifest = self._read_first_manifest(manifests)
        latest_mtime = max((path.stat().st_mtime for path in artifact_files), default=None)
        latest_mtime_iso = (
            datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            if latest_mtime is not None
            else None
        )
        latest_age_hours = self._artifact_age_hours(latest_mtime)
        artifact_is_fresh = (
            latest_age_hours is not None
            and latest_age_hours <= settings.SENTIMENTAL_MAX_ARTIFACT_AGE_HOURS
        )

        covered_tickers = manifest.get("covered_tickers") if isinstance(manifest, dict) else None
        if not covered_tickers:
            covered_tickers = sorted(path.stem for path in artifact_files)

        using_real_model_artifacts = (
            any(latest_dir.exists() for latest_dir in latest_dirs)
            and len(artifact_files) > 0
            and any(manifest_path.exists() for manifest_path in manifests)
            and artifact_is_fresh
        )

        return {
            "artifact_dir": str(configured_root),
            "artifact_dir_exists": configured_root.exists(),
            "require_model_artifact": settings.SENTIMENTAL_REQUIRE_MODEL_ARTIFACT,
            "latest_dir_exists": any(latest_dir.exists() for latest_dir in latest_dirs),
            "manifest_exists": any(manifest_path.exists() for manifest_path in manifests),
            "covered_tickers": covered_tickers,
            "default_model": settings.SENTIMENTAL_DEFAULT_MODEL,
            "artifact_file_count": len(artifact_files),
            "latest_artifact_mtime": latest_mtime_iso,
            "latest_artifact_age_hours": latest_age_hours,
            "max_artifact_age_hours": settings.SENTIMENTAL_MAX_ARTIFACT_AGE_HOURS,
            "artifact_is_fresh": artifact_is_fresh,
            "using_real_model_artifacts": using_real_model_artifacts,
        }

    def _artifact_roots(self) -> list[Path]:
        roots: list[Path] = []
        configured = Path(settings.SENTIMENTAL_ARTIFACT_DIR)
        roots.append(configured)

        repo_root = Path(__file__).resolve().parents[4]
        local_outputs = repo_root / "Sentimental_Model" / "outputs"
        if local_outputs not in roots:
            roots.append(local_outputs)

        return roots

    def _validate_artifact(self, artifact: dict[str, Any], artifact_path: Path) -> None:
        missing = sorted(field for field in self.REQUIRED_FIELDS if field not in artifact)
        if missing:
            raise ValueError(
                f"Sentimental model artifact {artifact_path} is missing required fields: {', '.join(missing)}."
            )

    def _latest_artifact_files(self, latest_dirs: list[Path]) -> list[Path]:
        files: dict[str, Path] = {}
        for latest_dir in latest_dirs:
            if not latest_dir.exists():
                continue
            for path in latest_dir.glob("*.json"):
                if path.name == "manifest.json":
                    continue
                files[path.stem] = path
        return sorted(files.values(), key=lambda path: path.name)

    def _read_first_manifest(self, manifests: list[Path]) -> dict[str, Any]:
        for manifest_path in manifests:
            if not manifest_path.exists():
                continue
            try:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    manifest = json.load(handle)
                return manifest if isinstance(manifest, dict) else {}
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to read sentimental manifest {manifest_path}: {exc}")
        return {}

    def _artifact_age_hours(self, mtime: float | None) -> float | None:
        if mtime is None:
            return None
        age_seconds = datetime.now(timezone.utc).timestamp() - mtime
        return round(max(age_seconds, 0.0) / 3600, 2)
