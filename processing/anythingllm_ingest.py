from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from time import sleep, perf_counter
from typing import Any
from urllib import error, request
import uuid

from common.config import AppConfig
from common.logging_setup import get_logger
from common.time_utils import format_duration_human
from processing.audit import AuditStage, ReasonCode, build_audit_components
from processing.manifest import generate_run_id
from sources.document import utc_now_iso


DEFAULT_ALLOWED_EXTENSIONS = {".md", ".txt", ".json", ".html", ".csv"}
TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class AnythingLLMRequestError(RuntimeError):
    """Strukturierter Request-Fehler für AnythingLLM API Calls."""

    def __init__(self, message: str, *, status_code: int | None = None, response_text: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


@dataclass(slots=True)
class AnythingLLMFileStateRecord:
    sha256: str
    size_bytes: int
    uploaded_document: str | None
    updated_at: str


@dataclass(slots=True)
class AnythingLLMState:
    files: dict[str, AnythingLLMFileStateRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "AnythingLLMState":
        target = path.expanduser().resolve()
        if not target.exists():
            return cls()
        payload = json.loads(target.read_text(encoding="utf-8"))
        records: dict[str, AnythingLLMFileStateRecord] = {}
        for key, row in payload.get("files", {}).items():
            records[key] = AnythingLLMFileStateRecord(
                sha256=str(row.get("sha256", "")),
                size_bytes=int(row.get("size_bytes", 0)),
                uploaded_document=row.get("uploaded_document"),
                updated_at=str(row.get("updated_at", "")),
            )
        return cls(files=records)

    def save(self, path: Path) -> None:
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "files": {key: asdict(value) for key, value in self.files.items()},
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(slots=True)
class PerGroupStats:
    scanned: int = 0
    uploaded: int = 0
    embedded: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass(slots=True)
class AnythingLLMIngestManifest:
    run_id: str
    started_at: str
    finished_at: str | None = None
    mode: str = "incremental"
    ingest_dir: str = ""
    files_scanned: int = 0
    files_candidate: int = 0
    files_new: int = 0
    files_changed: int = 0
    files_unchanged: int = 0
    files_uploaded: int = 0
    files_embedded: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bytes_total: int = 0
    bytes_uploaded: int = 0
    run_duration: float = 0.0
    run_duration_human: str = "0s"
    by_top_level_source: dict[str, PerGroupStats] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, ensure_ascii=False, indent=2)


@dataclass(slots=True)
class DeltaPlanEntry:
    absolute_path: Path
    relative_path: str
    top_level_group: str
    sha256: str
    size_bytes: int
    action: str  # new | changed | unchanged | filtered | too_large
    reason_code: str | None = None
    reason_detail: str | None = None


@dataclass(slots=True)
class AnythingLLMIngestConfig:
    ingest_dir: Path
    data_root: Path
    workspace: str
    document_folder: str
    allowed_extensions: set[str]
    max_file_size_bytes: int
    base_url: str
    api_key: str
    upload_path: str
    upload_file_field: str
    upload_folder_field: str
    workspace_attach_path_template: str
    timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: float
    dry_run: bool = False
    force_reupload: bool = False
    force_reembed: bool = False
    run_id: str | None = None
    source_instance: str = "anythingllm"

    @property
    def mode(self) -> str:
        if self.force_reupload:
            return "force_reupload"
        if self.force_reembed:
            return "force_reembed"
        return "incremental"

    @classmethod
    def from_env_and_args(
        cls,
        *,
        ingest_dir: Path | None,
        dry_run: bool,
        force_reupload: bool,
        force_reembed: bool,
        run_id: str | None,
        source_instance: str,
    ) -> "AnythingLLMIngestConfig":
        data_root = Path.home() / "local-knowledge-data"
        default_ingest = data_root / "ingest"
        configured_ingest = AppConfig.get_str("INGEST_DIR", "anythingllm_ingest", "ingest_dir", default=str(default_ingest))

        extensions_raw = AppConfig.get_str(
            "ANYTHINGLLM_ALLOWED_EXTENSIONS",
            "anythingllm_ingest",
            "allowed_extensions",
            default=",".join(sorted(DEFAULT_ALLOWED_EXTENSIONS)),
        )
        extensions = {part.strip().lower() for part in extensions_raw.split(",") if part.strip()}
        if not extensions:
            extensions = set(DEFAULT_ALLOWED_EXTENSIONS)

        max_file_size_mb = int(AppConfig.get_str("MAX_FILE_SIZE_MB", "anythingllm_ingest", "max_file_size_mb", default="20"))

        path_template = AppConfig.get_str(
            "ANYTHINGLLM_WORKSPACE_ATTACH_PATH_TEMPLATE",
            "anythingllm",
            "api",
            "workspace_attach_path_template",
            default="/api/v1/workspace/{workspace}/update-embeddings",
        )

        return cls(
            ingest_dir=(ingest_dir or Path(configured_ingest)).expanduser().resolve(),
            data_root=data_root,
            workspace=AppConfig.get_str("ANYTHINGLLM_WORKSPACE", "anythingllm", "workspace", default=""),
            document_folder=AppConfig.get_str("ANYTHINGLLM_DOCUMENT_FOLDER", "anythingllm", "document_folder", default="custom-documents"),
            allowed_extensions=extensions,
            max_file_size_bytes=max_file_size_mb * 1024 * 1024,
            base_url=AppConfig.get_str("ANYTHINGLLM_BASE_URL", "anythingllm", "base_url", default="http://localhost:3001"),
            api_key=AppConfig.get_str("ANYTHINGLLM_API_KEY", "anythingllm", "api_key", default=""),
            upload_path=AppConfig.get_str("ANYTHINGLLM_UPLOAD_PATH", "anythingllm", "api", "upload_path", default="/api/v1/document/upload"),
            upload_file_field=AppConfig.get_str(
                "ANYTHINGLLM_UPLOAD_FILE_FIELD",
                "anythingllm",
                "api",
                "upload_file_field",
                default="file",
            ),
            upload_folder_field=AppConfig.get_str(
                "ANYTHINGLLM_UPLOAD_FOLDER_FIELD",
                "anythingllm",
                "api",
                "upload_folder_field",
                default="folder",
            ),
            workspace_attach_path_template=path_template,
            timeout_seconds=int(AppConfig.get_str("ANYTHINGLLM_TIMEOUT_SECONDS", "anythingllm", "timeout_seconds", default="30")),
            max_retries=int(AppConfig.get_str("ANYTHINGLLM_MAX_RETRIES", "anythingllm", "max_retries", default="3")),
            retry_backoff_seconds=float(AppConfig.get_str("ANYTHINGLLM_RETRY_BACKOFF_SECONDS", "anythingllm", "retry_backoff_seconds", default="1.0")),
            dry_run=dry_run,
            force_reupload=force_reupload,
            force_reembed=force_reembed,
            run_id=run_id,
            source_instance=source_instance,
        )


class AnythingLLMClient:
    """Minimaler AnythingLLM-API Client.

    Endpunkte können zwischen AnythingLLM-Versionen driften. Prüfe konkrete Pfade/
    Payloads gegen <base_url>/api/docs und passe die konfigurierbaren Pfade in app.toml/ENV an.
    """

    def __init__(self, config: AnythingLLMIngestConfig):
        self.config = config
        self.workspace_slug = config.workspace.lower().strip()

    def upload_file(self, file_path: Path) -> str:
        content_type, body = _build_multipart_upload_request(
            file_path=file_path,
            file_field_name=self.config.upload_file_field,
            folder_field_name=self.config.upload_folder_field,
            folder_value=self.config.document_folder,
        )
        response = self._request(
            self.config.upload_path,
            method="POST",
            body=body,
            headers={"Content-Type": content_type},
            request_context={
                "file_field": self.config.upload_file_field,
                "folder_field": self.config.upload_folder_field,
            },
        )
        location = _extract_document_location(response)
        if not location:
            raise RuntimeError(
                "AnythingLLM upload response enthält keinen Dokumentpfad. "
                "Möglicher API-Drift: prüfe Upload-Response gegen <base_url>/api/docs"
            )
        return location

    def embed_in_workspace(self, *, workspace: str, document_location: str, force_reembed: bool) -> None:
        _ = workspace
        _ = force_reembed
        path = self.config.workspace_attach_path_template.format(workspace=self.workspace_slug)
        payload: dict[str, Any] = {"adds": [document_location]}
        self._request(
            path,
            method="POST",
            json_body=payload,
            request_context={"workspace_slug": self.workspace_slug, "embed_payload": json.dumps(payload, ensure_ascii=False)},
        )

    def _request(
        self,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        request_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        merged_headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }
        if headers:
            merged_headers.update(headers)
        data = body
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            merged_headers["Content-Type"] = "application/json"

        for attempt in range(1, self.config.max_retries + 1):
            req = request.Request(url=url, data=data, method=method, headers=merged_headers)
            try:
                with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                    return json.loads(payload) if payload else {}
            except error.HTTPError as exc:
                response_text = exc.read().decode("utf-8", errors="replace")
                context_parts: list[str] = []
                if request_context:
                    context_parts = [f"{key}={value}" for key, value in sorted(request_context.items())]
                context_msg = f" context=({', '.join(context_parts)})" if context_parts else ""

                if _is_non_transient_api_drift_error(response_text):
                    raise AnythingLLMRequestError(
                        f"AnythingLLM request failed ({exc.code}) {method} {path}:{context_msg} {response_text}. "
                        "Erkannter nicht-transienter API-Fehler (z.B. Feldname/Schema). "
                        "Bitte Endpoint/Payload gegen <base_url>/api/docs prüfen.",
                        status_code=exc.code,
                        response_text=response_text,
                    ) from exc

                if exc.code in TRANSIENT_STATUS_CODES and attempt < self.config.max_retries:
                    sleep(self.config.retry_backoff_seconds * attempt)
                    continue
                raise AnythingLLMRequestError(
                    f"AnythingLLM request failed ({exc.code}) {method} {path}:{context_msg} {response_text}. "
                    "Falls Endpoint/Payload nicht passt: API-Drift gegen <base_url>/api/docs prüfen.",
                    status_code=exc.code,
                    response_text=response_text,
                ) from exc
            except (error.URLError, TimeoutError) as exc:
                if attempt < self.config.max_retries:
                    sleep(self.config.retry_backoff_seconds * attempt)
                    continue
                raise AnythingLLMRequestError(f"AnythingLLM request timeout/network error for {method} {path}: {exc}") from exc
        raise AnythingLLMRequestError(f"AnythingLLM request failed after retries for {method} {path}")


def run_anythingllm_ingest(config: AnythingLLMIngestConfig) -> tuple[int, AnythingLLMIngestManifest]:
    run_id = config.run_id or generate_run_id()
    logger = get_logger("run_ingest_anythingllm", run_id=run_id)

    if not config.workspace:
        raise ValueError("ANYTHINGLLM_WORKSPACE muss gesetzt sein")
    if not config.dry_run and (not config.api_key.strip()):
        raise ValueError("ANYTHINGLLM_API_KEY muss gesetzt sein (außer im --dry-run)")

    manifests_dir = config.data_root / "system" / "anythingllm_ingest"
    state_path = manifests_dir / "latest_state.json"
    state = AnythingLLMState.load(state_path)

    manifest = AnythingLLMIngestManifest(
        run_id=run_id,
        started_at=utc_now_iso(),
        mode=config.mode,
        ingest_dir=str(config.ingest_dir),
    )
    started = perf_counter()

    run_context, audit = build_audit_components(
        data_root=config.data_root,
        source_type="anythingllm_ingest",
        source_instance=config.source_instance,
        mode=config.mode,
        run_id=run_id,
    )

    client = AnythingLLMClient(config)
    final_status = "running"
    exit_code = 1

    try:
        entries = build_delta_plan(config.ingest_dir, config.allowed_extensions, config.max_file_size_bytes, state)

        for entry in entries:
            _touch_group(manifest, entry.top_level_group).scanned += 1
            manifest.files_scanned += 1
            manifest.bytes_total += entry.size_bytes
            with audit.stage(
                run_id=run_context.run_id,
                source_type="anythingllm_ingest",
                source_instance=config.source_instance,
                stage=AuditStage.DISCOVER,
                document_id=entry.relative_path,
                document_uri=entry.absolute_path.as_uri(),
                document_title=entry.absolute_path.name,
            ):
                pass

            if entry.action in {"filtered", "too_large"}:
                logger.info("File discovered but filtered. file=%s reason=%s", entry.relative_path, entry.action)
                manifest.files_skipped += 1
                _touch_group(manifest, entry.top_level_group).skipped += 1
                with audit.stage(
                    run_id=run_context.run_id,
                    source_type="anythingllm_ingest",
                    source_instance=config.source_instance,
                    stage=AuditStage.FILTER,
                    document_id=entry.relative_path,
                    document_uri=entry.absolute_path.as_uri(),
                    document_title=entry.absolute_path.name,
                    extra_json={"is_dirty": None},
                ) as filter_evt:
                    reason_code = entry.reason_code or (ReasonCode.FILE_TOO_LARGE if entry.action == "too_large" else ReasonCode.FILTERED_BY_RULE)
                    filter_evt.skipped(reason_code, entry.reason_detail or f"Filtered action={entry.action}")
                manifest.records.append(_record(entry, status="skipped", reason=entry.action))
                continue

            if entry.action == "unchanged" and not config.force_reupload and not config.force_reembed:
                logger.info("File skipped unchanged by delta. file=%s", entry.relative_path)
                manifest.files_unchanged += 1
                manifest.files_skipped += 1
                _touch_group(manifest, entry.top_level_group).skipped += 1
                with audit.stage(
                    run_id=run_context.run_id,
                    source_type="anythingllm_ingest",
                    source_instance=config.source_instance,
                    stage=AuditStage.FILTER,
                    document_id=entry.relative_path,
                    document_uri=entry.absolute_path.as_uri(),
                    document_title=entry.absolute_path.name,
                    extra_json={"is_dirty": None},
                ) as filter_evt:
                    filter_evt.skipped(ReasonCode.UNCHANGED_INCREMENTAL, "Datei unverändert")
                manifest.records.append(_record(entry, status="skipped", reason="unchanged"))
                continue

            manifest.files_candidate += 1
            if entry.action == "new":
                manifest.files_new += 1
            elif entry.action == "changed":
                manifest.files_changed += 1

            should_upload = config.force_reupload or entry.action in {"new", "changed"}
            logger.info("Upload started. file=%s upload=%s", entry.relative_path, should_upload)
            uploaded_document: str | None = None
            if should_upload:
                with audit.stage(
                    run_id=run_context.run_id,
                    source_type="anythingllm_ingest",
                    source_instance=config.source_instance,
                    stage=AuditStage.LOAD,
                    document_id=entry.relative_path,
                    document_uri=entry.absolute_path.as_uri(),
                    document_title=entry.absolute_path.name,
                    extra_json={"changed_flag": True, "is_dirty": True},
                ):
                    pass

            try:
                if config.dry_run:
                    uploaded_document = state.files.get(entry.relative_path).uploaded_document if entry.relative_path in state.files else f"dry-run/{entry.relative_path}"
                elif should_upload:
                    uploaded_document = client.upload_file(entry.absolute_path)
                    manifest.files_uploaded += 1
                    manifest.bytes_uploaded += entry.size_bytes
                    _touch_group(manifest, entry.top_level_group).uploaded += 1
                    logger.info("Upload successful. file=%s doc=%s", entry.relative_path, uploaded_document)
                else:
                    uploaded_document = state.files.get(entry.relative_path).uploaded_document if entry.relative_path in state.files else None

                if not uploaded_document:
                    raise RuntimeError("Kein Dokument-Identifier für Embedding vorhanden")

                logger.info("Embedding started. file=%s workspace=%s", entry.relative_path, config.workspace)
                with audit.stage(
                    run_id=run_context.run_id,
                    source_type="anythingllm_ingest",
                    source_instance=config.source_instance,
                    stage=AuditStage.EMBED,
                    document_id=entry.relative_path,
                    document_uri=entry.absolute_path.as_uri(),
                    document_title=entry.absolute_path.name,
                    extra_json={"changed_flag": True, "is_dirty": True},
                ):
                    pass
                if not config.dry_run:
                    client.embed_in_workspace(
                        workspace=config.workspace,
                        document_location=uploaded_document,
                        force_reembed=config.force_reembed,
                    )
                manifest.files_embedded += 1
                _touch_group(manifest, entry.top_level_group).embedded += 1
                logger.info("Embedding successful. file=%s", entry.relative_path)
                state.files[entry.relative_path] = AnythingLLMFileStateRecord(
                    sha256=entry.sha256,
                    size_bytes=entry.size_bytes,
                    uploaded_document=uploaded_document,
                    updated_at=utc_now_iso(),
                )
                manifest.records.append(_record(entry, status="ok", uploaded_document=uploaded_document))
            except Exception as exc:  # noqa: BLE001
                manifest.files_failed += 1
                _touch_group(manifest, entry.top_level_group).failed += 1
                logger.exception("File processing failed. file=%s error=%s", entry.relative_path, exc)
                manifest.records.append(_record(entry, status="error", reason=str(exc)))

        final_status = "finished" if manifest.files_failed == 0 else "finished_with_errors"
        exit_code = 0 if manifest.files_failed == 0 else 1
    except Exception:
        final_status = "failed"
        manifest.files_failed += 1
        logger.exception("AnythingLLM ingest aborted unexpectedly. run_id=%s", manifest.run_id)
        raise
    finally:
        manifest.finished_at = utc_now_iso()
        manifest.run_duration = perf_counter() - started
        manifest.run_duration_human = format_duration_human(manifest.run_duration)

        manifests_dir.mkdir(parents=True, exist_ok=True)
        run_manifest_path = manifests_dir / f"run_{manifest.run_id}.json"
        latest_manifest_path = manifests_dir / "latest_manifest.json"
        run_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        latest_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        state.save(state_path)

        logger.info(
            "AnythingLLM ingest completed. run_id=%s scanned=%s candidate=%s uploaded=%s embedded=%s skipped=%s failed=%s duration=%.2fs (%s)",
            manifest.run_id,
            manifest.files_scanned,
            manifest.files_candidate,
            manifest.files_uploaded,
            manifest.files_embedded,
            manifest.files_skipped,
            manifest.files_failed,
            manifest.run_duration,
            manifest.run_duration_human,
        )

        run_context.finish(status=final_status)

    return exit_code, manifest


def build_delta_plan(
    ingest_dir: Path,
    allowed_extensions: set[str],
    max_file_size_bytes: int,
    state: AnythingLLMState,
) -> list[DeltaPlanEntry]:
    if not ingest_dir.exists():
        return []

    entries: list[DeltaPlanEntry] = []
    for path in sorted(p for p in ingest_dir.rglob("*") if p.is_file()):
        rel_path = path.relative_to(ingest_dir).as_posix()
        ext = path.suffix.lower()
        size = path.stat().st_size
        if ext not in allowed_extensions:
            entries.append(
                DeltaPlanEntry(
                    path,
                    rel_path,
                    infer_top_level_group(rel_path),
                    "",
                    size,
                    "filtered",
                    reason_code=_classify_filtered_reason(path),
                    reason_detail=f"Datei gefiltert: {path.name}",
                )
            )
            continue
        if size > max_file_size_bytes:
            entries.append(
                DeltaPlanEntry(
                    path,
                    rel_path,
                    infer_top_level_group(rel_path),
                    "",
                    size,
                    "too_large",
                    reason_code=ReasonCode.FILE_TOO_LARGE,
                    reason_detail=f"Dateigröße {size} > Limit {max_file_size_bytes}",
                )
            )
            continue

        sha = sha256_file(path)
        existing = state.files.get(rel_path)
        if existing is None:
            action = "new"
        elif existing.sha256 != sha:
            action = "changed"
        else:
            action = "unchanged"

        entries.append(DeltaPlanEntry(path, rel_path, infer_top_level_group(rel_path), sha, size, action))
    return entries


def _classify_filtered_reason(path: Path) -> str:
    lower_name = path.name.lower()
    if path.name.startswith("."):
        return ReasonCode.IGNORE_HIDDEN_FILE
    if lower_name == "_index.md":
        return ReasonCode.IGNORE_INDEX_FILE
    if lower_name in {"readme.md", "thumbs.db", ".ds_store"}:
        return ReasonCode.IGNORE_SYSTEM_FILE
    return ReasonCode.UNSUPPORTED_FILE_EXTENSION


def infer_top_level_group(relative_path: str) -> str:
    first = relative_path.split("/", 1)[0].strip().lower()
    return first or "sonstige"


def is_allowed_extension(path: Path, allowed_extensions: set[str]) -> bool:
    return path.suffix.lower() in allowed_extensions


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _record(entry: DeltaPlanEntry, *, status: str, reason: str | None = None, uploaded_document: str | None = None) -> dict[str, Any]:
    return {
        "relative_path": entry.relative_path,
        "top_level_group": entry.top_level_group,
        "size_bytes": entry.size_bytes,
        "action": entry.action,
        "status": status,
        "reason": reason,
        "uploaded_document": uploaded_document,
    }


def _touch_group(manifest: AnythingLLMIngestManifest, key: str) -> PerGroupStats:
    if key not in manifest.by_top_level_source:
        manifest.by_top_level_source[key] = PerGroupStats()
    return manifest.by_top_level_source[key]


def _extract_document_location(response: dict[str, Any]) -> str | None:
    for key in ("location", "localFilePath", "filePath", "document"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    documents = response.get("documents")
    if isinstance(documents, list):
        for item in documents:
            if isinstance(item, dict):
                for key in ("location", "localFilePath", "filePath", "document"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            elif isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _build_multipart_upload_request(
    *,
    file_path: Path,
    file_field_name: str,
    folder_field_name: str,
    folder_value: str,
) -> tuple[str, bytes]:
    boundary = f"----localknowledgeanythingllm-{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    body = b"\r\n".join(
        [
            f"--{boundary}".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_path.name}"'
            ).encode("utf-8"),
            b"Content-Type: application/octet-stream",
            b"",
            file_bytes,
            f"--{boundary}".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{folder_field_name}"'
            ).encode("utf-8"),
            b"",
            folder_value.encode("utf-8"),
            f"--{boundary}--".encode("utf-8"),
            b"",
        ]
    )
    content_type = f"multipart/form-data; boundary={boundary}"
    return content_type, body


def _is_non_transient_api_drift_error(response_text: str) -> bool:
    text = response_text.lower()
    markers = [
        "unexpected field",
        "invalid file upload",
        "validation",
        "invalid multipart",
        "missing field",
    ]
    return any(marker in text for marker in markers)
