#!/usr/bin/env bash
set -euo pipefail

WITH_ANYTHINGLLM=0
ONLY_STEP=""
SKIP_ANYTHINGLLM=0

usage() {
  cat <<'EOF'
Usage: ./pipeline.sh [options]

Options:
  --with-anythingllm       Enable AnythingLLM ingest step.
  --skip-anythingllm       Explicitly skip AnythingLLM ingest step.
  --only <step>            Run only one step. Supported: ingestion, index, ingest-anythingllm
  -h, --help               Show this help.

Examples:
  ./pipeline.sh
  ./pipeline.sh --with-anythingllm
  ./pipeline.sh --only ingest-anythingllm
EOF
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

run_step() {
  local step="$1"
  shift
  echo "==> Running step: ${step}"
  "$@"
}

if [[ -n "$ONLY_STEP" ]]; then
  case "$ONLY_STEP" in
    ingestion)
      run_step "ingestion" python scripts/run_ingestion.py
      ;;
    index)
      run_step "index" python scripts/build_vector_index.py
      ;;
    ingest-anythingllm)
      run_step "ingest-anythingllm" python scripts/run_ingest_anythingllm.py
      ;;
    *)
      echo "ERROR: unsupported step for --only: $ONLY_STEP" >&2
      exit 2
      ;;
  esac
  exit 0
fi

run_step "ingestion" python scripts/run_ingestion.py
run_step "index" python scripts/build_vector_index.py

if [[ "$WITH_ANYTHINGLLM" -eq 1 && "$SKIP_ANYTHINGLLM" -eq 0 ]]; then
  run_step "ingest-anythingllm" python scripts/run_ingest_anythingllm.py
else
  echo "==> Skipping step: ingest-anythingllm"
fi
