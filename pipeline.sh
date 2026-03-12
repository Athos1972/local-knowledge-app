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
RUN_JIRA=0

HAS_JIRA_STEP=0
if [[ -f "$PROJECT_ROOT/scripts/run_transform_jira.py" ]]; then
  HAS_JIRA_STEP=1
  RUN_JIRA=1
fi

usage() {
  cat <<EOF_HELP
Usage: ./pipeline.sh [options]

Options:
  --with-anythingllm     Enable AnythingLLM ingest step.
  --skip-anythingllm     Explicitly skip AnythingLLM ingest step.
  --only <step>          Run only one step.
  --skip-confluence      Skip Confluence transform step.
  --skip-scraping        Skip scraping transform + mapping steps.
  --skip-index           Skip vector index build step.
  --skip-audit           Skip audit report step.
EOF_HELP

  if [[ "$HAS_JIRA_STEP" -eq 1 ]]; then
    cat <<'EOF_HELP_JIRA'
  --skip-jira            Skip JIRA transform step.
EOF_HELP_JIRA
  fi

  cat <<'EOF_HELP_TAIL'
  -h, --help             Show this help.

Available steps for --only:
  transform-confluence
EOF_HELP_TAIL

  if [[ "$HAS_JIRA_STEP" -eq 1 ]]; then
    cat <<'EOF_HELP_STEPS_JIRA'
  transform-jira
EOF_HELP_STEPS_JIRA
  fi

  cat <<'EOF_HELP_STEPS'
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
EOF_HELP_STEPS
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
      if [[ "$HAS_JIRA_STEP" -eq 1 ]]; then
        RUN_JIRA=0
        shift
      else
        echo "ERROR: unknown argument: --skip-jira" >&2
        usage
        exit 2
      fi
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
    transform-confluence|transform-scraping|map-scraping|ingestion|index|audit|ingest-anythingllm)
      return 0
      ;;
    transform-jira)
      [[ "$HAS_JIRA_STEP" -eq 1 ]]
      return
      ;;
    *)
      return 1
      ;;
  esac
}

run_step() {
  local step="$1"
  shift
  echo "[START] $step"
  if "$@"; then
    echo "[OK]    $step"
  else
    local rc=$?
    echo "[FAIL]  $step (exit code $rc)"
    exit "$rc"
  fi
}

run_step_by_name() {
  local step="$1"
  case "$step" in
    transform-confluence)
      run_step "$step" "$PYTHON_BIN" scripts/run_transform_confluence.py
      ;;
    transform-jira)
      run_step "$step" "$PYTHON_BIN" scripts/run_transform_jira.py
      ;;
    transform-scraping)
      if [[ ! -d "exports/scraping" ]]; then
        echo "[SKIP]  $step (missing exports/scraping)"
        return 0
      fi
      run_step "$step" "$PYTHON_BIN" scripts/run_transform_scraping_exports.py
      ;;
    map-scraping)
      if [[ ! -d "staging/transformed" ]]; then
        echo "[SKIP]  $step (missing staging/transformed)"
        return 0
      fi
      run_step "$step" "$PYTHON_BIN" scripts/run_map_transformed_to_domains.py
      ;;
    ingestion)
      run_step "$step" "$PYTHON_BIN" scripts/run_ingestion.py
      ;;
    index)
      if ! compgen -G "$HOME/local-knowledge-data/processed/chunks/*.jsonl" > /dev/null; then
        echo "[SKIP]  $step (no chunk files found)"
        return 0
      fi
      run_step "$step" "$PYTHON_BIN" scripts/build_vector_index.py
      ;;
    audit)
      run_step "$step" "$PYTHON_BIN" scripts/audit_report.py
      ;;
    ingest-anythingllm)
      if [[ -z "${ANYTHINGLLM_WORKSPACE:-}" ]]; then
        echo "[SKIP]  $step (ANYTHINGLLM_WORKSPACE is not set)"
        return 0
      fi
      run_step "$step" "$PYTHON_BIN" scripts/run_ingest_anythingllm.py
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
  if [[ "$enabled" -eq 1 ]]; then
    run_step_by_name "$step"
  else
    echo "[SKIP]  $step"
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
echo "Confluence: $([[ "$RUN_CONFLUENCE" -eq 1 ]] && echo on || echo off)"
if [[ "$HAS_JIRA_STEP" -eq 1 ]]; then
  echo "JIRA: $([[ "$RUN_JIRA" -eq 1 ]] && echo on || echo off)"
fi
echo "Scraping: $([[ "$RUN_SCRAPING" -eq 1 ]] && echo on || echo off)"
echo "Index: $([[ "$RUN_INDEX" -eq 1 ]] && echo on || echo off)"
echo "Audit: $([[ "$RUN_AUDIT" -eq 1 ]] && echo on || echo off)"
echo "AnythingLLM: $([[ "$RUN_ANYTHINGLLM" -eq 1 ]] && echo on || echo off)"
echo "Python: $PYTHON_BIN"
echo "Log file: $LOG_FILE"

run_or_skip "$RUN_CONFLUENCE" "transform-confluence"
if [[ "$HAS_JIRA_STEP" -eq 1 ]]; then
  run_or_skip "$RUN_JIRA" "transform-jira"
fi
run_or_skip "$RUN_SCRAPING" "transform-scraping"
run_or_skip "$RUN_SCRAPING" "map-scraping"
run_step_by_name "ingestion"
run_or_skip "$RUN_INDEX" "index"
run_or_skip "$RUN_AUDIT" "audit"
run_or_skip "$RUN_ANYTHINGLLM" "ingest-anythingllm"

echo "=== Pipeline finished ==="
echo "Status: SUCCESS"
