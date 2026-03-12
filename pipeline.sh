#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/.venv}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
PYTHON_BIN="${PYTHON_BIN:-}"

WITH_ANYTHINGLLM=0
SKIP_ANYTHINGLLM=0
ONLY_STEP=""

RUN_CONFLUENCE=1
RUN_SCRAPING=1
RUN_INDEX=1
RUN_AUDIT=1
RUN_JIRA=1

JIRA_STEP_SCRIPT="scripts/run_transform_jira.py"
if [[ ! -f "$PROJECT_ROOT/$JIRA_STEP_SCRIPT" ]]; then
  RUN_JIRA=0
fi

LOG_LEVEL_STDOUT="${LOG_LEVEL_STDOUT:-INFO}"
LOG_LEVEL_FILE="${LOG_LEVEL_FILE:-DEBUG}"
export LOG_LEVEL_STDOUT
export LOG_LEVEL_FILE

usage() {
  cat <<EOF_HELP
Usage: ./pipeline.sh [options]

Options:
  --with-anythingllm     Enable AnythingLLM ingest step.
  --skip-anythingllm     Explicitly skip AnythingLLM ingest step.
  --only <step>          Run only one step.
  --skip-confluence      Skip Confluence transform step.
  --skip-jira            Skip JIRA transform step.
  --skip-scraping        Skip scraping transform + mapping steps.
  --skip-index           Skip vector index build step.
  --skip-audit           Skip audit report step.

  -h, --help             Show this help.

Available steps for --only:
  transform-confluence
  transform-jira
  transform-scraping
  map-scraping
  ingestion
  index
  audit
  ingest-anythingllm

Examples:
  ./pipeline.sh
  ./pipeline.sh --with-anythingllm
  ./pipeline.sh --only transform-confluence
  ./pipeline.sh --only audit
EOF_HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-anythingllm)
      WITH_ANYTHINGLLM=1
      shift
      ;;
    --skip-anythingllm)
      SKIP_ANYTHINGLLM=1
      shift
      ;;
    --only)
      ONLY_STEP="${2:-}"
      if [[ -z "$ONLY_STEP" ]]; then
        echo "ERROR: --only requires a step name" >&2
        exit 2
      fi
      shift 2
      ;;
    --skip-confluence)
      RUN_CONFLUENCE=0
      shift
      ;;
    --skip-scraping)
      RUN_SCRAPING=0
      shift
      ;;
    --skip-index)
      RUN_INDEX=0
      shift
      ;;
    --skip-audit)
      RUN_AUDIT=0
      shift
      ;;
    --skip-jira)
      RUN_JIRA=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -n "$PYTHON_BIN" ]]; then
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "ERROR: PYTHON_BIN is set but not executable: $PYTHON_BIN" >&2
    exit 1
  fi
elif [[ -x "$VENV_PATH/bin/python" ]]; then
  PYTHON_BIN="$VENV_PATH/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "ERROR: no usable Python interpreter found (checked .venv/bin/python, python3, python)." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_pipeline_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

cd "$PROJECT_ROOT"

step_exists() {
  local step="$1"
  case "$step" in
    transform-confluence|transform-jira|transform-scraping|map-scraping|ingestion|index|audit|ingest-anythingllm)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

run_step() {
  local step="$1"
  local stage_label="$2"
  shift
  shift
  echo "[START] $stage_label"
  if "$@"; then
    echo "[OK]    $stage_label"
  else
    local rc=$?
    echo "[FAIL]  $stage_label (exit code $rc)"
    exit "$rc"
  fi
}

run_step_by_name() {
  local step="$1"
  case "$step" in
    transform-confluence)
      run_step "$step" "Transform Confluence" "$PYTHON_BIN" scripts/run_transform_confluence.py
      ;;
    transform-jira)
      if [[ ! -f "$JIRA_STEP_SCRIPT" ]]; then
        echo "[SKIP]  Transform JIRA (missing $JIRA_STEP_SCRIPT)"
        return 0
      fi
      run_step "$step" "Transform JIRA" "$PYTHON_BIN" "$JIRA_STEP_SCRIPT"
      ;;
    transform-scraping)
      local scraping_input_root
      scraping_input_root="$($PYTHON_BIN -c "from common.config import AppConfig; from pathlib import Path; p=AppConfig.get_path(None, 'scraping_transform', 'input_root', default='exports/scraping'); print(Path(p).resolve())")"
      if [[ ! -d "$scraping_input_root" ]]; then
        echo "[FAIL]  Transform Scraping (scraping input root missing: $scraping_input_root)"
        echo "        Hinweis: setze [scraping_transform].input_root in config/app.toml oder nutze --input-root im Script."
        return 1
      fi
      run_step "$step" "Transform Scraping" "$PYTHON_BIN" scripts/run_transform_scraping_exports.py
      ;;
    map-scraping)
      local scraping_output_root
      scraping_output_root="$($PYTHON_BIN -c "from common.config import AppConfig; from pathlib import Path; p=AppConfig.get_path(None, 'scraping_transform', 'output_root', default='staging/transformed'); print(Path(p).resolve())")"
      if [[ ! -d "$scraping_output_root" ]]; then
        echo "[SKIP]  Map Scraping (missing transformed root: $scraping_output_root)"
        return 0
      fi
      run_step "$step" "Map Scraping" "$PYTHON_BIN" scripts/run_map_transformed_to_domains.py
      ;;
    ingestion)
      run_step "$step" "Ingestion" "$PYTHON_BIN" scripts/run_ingestion.py
      ;;
    index)
      if ! compgen -G "$HOME/local-knowledge-data/processed/chunks/*.jsonl" > /dev/null; then
        echo "[SKIP]  Index (no chunk files found)"
        return 0
      fi
      run_step "$step" "Index" "$PYTHON_BIN" scripts/build_vector_index.py
      ;;
    audit)
      run_step "$step" "Audit" "$PYTHON_BIN" scripts/audit_report.py
      ;;
    ingest-anythingllm)
      if [[ -z "${ANYTHINGLLM_WORKSPACE:-}" ]]; then
        echo "[SKIP]  Ingest AnythingLLM (ANYTHINGLLM_WORKSPACE is not set)"
        return 0
      fi
      run_step "$step" "Ingest AnythingLLM" "$PYTHON_BIN" scripts/run_ingest_anythingllm.py
      ;;
    *)
      echo "ERROR: unsupported step: $step" >&2
      exit 2
      ;;
  esac
}

run_or_skip() {
  local enabled="$1"
  local step="$2"
  local label="$step"
  case "$step" in
    transform-confluence) label="Transform Confluence" ;;
    transform-jira) label="Transform JIRA" ;;
    transform-scraping) label="Transform Scraping" ;;
    map-scraping) label="Map Scraping" ;;
    ingestion) label="Ingestion" ;;
    index) label="Index" ;;
    audit) label="Audit" ;;
    ingest-anythingllm) label="Ingest AnythingLLM" ;;
  esac
  if [[ "$enabled" -eq 1 ]]; then
    run_step_by_name "$step"
  else
    echo "[SKIP]  $label"
  fi
}

if [[ -n "$ONLY_STEP" ]]; then
  if ! step_exists "$ONLY_STEP"; then
    echo "ERROR: unsupported step for --only: $ONLY_STEP" >&2
    usage
    exit 2
  fi

  echo "=== Local Knowledge Pipeline ==="
  echo "Mode: only"
  echo "Only step: $ONLY_STEP"
  echo "Stdout log level: $LOG_LEVEL_STDOUT"
  echo "File log level: $LOG_LEVEL_FILE"
  echo "AnythingLLM enabled: $([[ "$WITH_ANYTHINGLLM" -eq 1 ]] && echo yes || echo no)"
  echo "Python: $PYTHON_BIN"
  echo "Log file: $LOG_FILE"

  run_step_by_name "$ONLY_STEP"
  echo "=== Pipeline finished ==="
  echo "Status: SUCCESS"
  exit 0
fi

if [[ "$WITH_ANYTHINGLLM" -eq 1 && "$SKIP_ANYTHINGLLM" -eq 0 ]]; then
  RUN_ANYTHINGLLM=1
else
  RUN_ANYTHINGLLM=0
fi

echo "=== Local Knowledge Pipeline ==="
echo "Mode: incremental"
echo "Confluence: $([[ "$RUN_CONFLUENCE" -eq 1 ]] && echo on || echo off)"
echo "JIRA: $([[ "$RUN_JIRA" -eq 1 ]] && echo on || echo off)"
echo "Scraping: $([[ "$RUN_SCRAPING" -eq 1 ]] && echo on || echo off)"
echo "Index: $([[ "$RUN_INDEX" -eq 1 ]] && echo on || echo off)"
echo "Audit: $([[ "$RUN_AUDIT" -eq 1 ]] && echo on || echo off)"
echo "AnythingLLM: $([[ "$RUN_ANYTHINGLLM" -eq 1 ]] && echo on || echo off)"
echo "Stdout log level: $LOG_LEVEL_STDOUT"
echo "File log level: $LOG_LEVEL_FILE"
echo "Python: $PYTHON_BIN"
echo "Log file: $LOG_FILE"

run_or_skip "$RUN_CONFLUENCE" "transform-confluence"
run_or_skip "$RUN_JIRA" "transform-jira"
run_or_skip "$RUN_SCRAPING" "transform-scraping"
run_or_skip "$RUN_SCRAPING" "map-scraping"
run_step_by_name "ingestion"
run_or_skip "$RUN_INDEX" "index"
run_or_skip "$RUN_AUDIT" "audit"
run_or_skip "$RUN_ANYTHINGLLM" "ingest-anythingllm"

echo "=== Pipeline finished ==="
echo "Status: SUCCESS"
