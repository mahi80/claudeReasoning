#!/usr/bin/env bash
# pod_test.sh - one GPU pod, one script: install vLLM, fetch a model, serve it on this
# machine only, then run the smoke test, one task and the eval set against it.
#
#   bash pod_test.sh gemma4                 # one 80 GB GPU
#   bash pod_test.sh deepseek-v41           # four H200
#   bash pod_test.sh gemma4 setup serve     # only some steps: setup serve smoke evals
#
# Written for Runpod's "PyTorch" template (Ubuntu 24.04, Python 3.12). The server binds
# to 127.0.0.1, so no port has to be exposed and no endpoint key is needed. Results and
# logs land in $OUT. Delete the pod when you are done: it bills until you do.
#
# Environment:
#   BRANCH        harness branch to test when this script has to clone it (main)
#   MODEL_HOME    where the weights go (/root/hf: the container disk, fast and disposable;
#                 put it on a volume to keep the weights across pod stops, at a slower load)
#   OUT           logs and results (/root/out)
#   EVALS         task file, relative to the repository (evals/tasks.agent.jsonl)
#   EFFORTS       effort levels to evaluate ("low medium high")
#   SHARDS        processes per level; the cases are split between them (1)
#   SERVE_EXTRA   extra `vllm serve` flags, for example "--enforce-eager"
#   READY_TIMEOUT seconds to wait for the server (3600)
set -u
PRESET=${1:?usage: pod_test.sh gemma4|deepseek-v41 [setup] [serve] [smoke] [evals]}
shift
STEPS=${*:-setup serve smoke evals}

OUT=${OUT:-/root/out}
export HF_HOME=${MODEL_HOME:-/root/hf}
export UV_CACHE_DIR=/root/.uvcache          # packages on the container disk: a network
VENV=/root/vllm-env                         # volume made the same install take minutes
HARNESS_VENV=/root/harness-env
PY=$HARNESS_VENV/bin/python
REPO=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)
[ -f "$REPO/harness/mini_harness.py" ] || REPO=/root/claudeReasoning
REPO_URL=${REPO_URL:-https://github.com/mahi80/claudeReasoning}
TEMPLATE=""
mkdir -p "$OUT"

case "$PRESET" in
  gemma4)
    MODEL=google/gemma-4-26B-A4B-it
    TEMPLATE=tool_chat_template_gemma4.jinja      # ships in vLLM's repository, not its wheel
    SERVE=(--max-model-len 32768 --gpu-memory-utilization 0.90
           --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4
           --chat-template "/root/$TEMPLATE")
    export LLM_CONTEXT_WINDOW=32768 LLM_KEEP_REASONING=1
    export LLM_THINKING_SCOPE=${LLM_THINKING_SCOPE:-task}
    export LLM_THINKING=${LLM_THINKING:-'{"off": {"chat_template_kwargs": {"enable_thinking": false}},
      "on": {"chat_template_kwargs": {"enable_thinking": true}}}'}
    ;;
  deepseek-v41)
    MODEL=deepseek-ai/DeepSeek-V4.1-Flash-1017
    SERVE=(--tokenizer-mode deepseek_v41 --tensor-parallel-size 4
           --engram-config '{"cpu_offload":true}' --language-model-only
           --enable-auto-tool-choice --tool-call-parser deepseek_v41
           --reasoning-parser deepseek_v41 --max-model-len 131072)
    export VLLM_ENGINE_READY_TIMEOUT_S=3600
    export LLM_CONTEXT_WINDOW=131072 LLM_KEEP_REASONING=1 LLM_TEMPERATURE=1.0
    export LLM_THINKING=${LLM_THINKING:-'{"off": {"chat_template_kwargs": {"thinking": false}},
      "on": {"chat_template_kwargs": {"thinking": true, "reasoning_effort": 50}},
      "max": {"chat_template_kwargs": {"thinking": true, "reasoning_effort": 100}}}'}
    ;;
  *) echo "unknown preset: $PRESET"; exit 2 ;;
esac
export LLM_BASE_URL=http://127.0.0.1:8000/v1 LLM_API_KEY=EMPTY LLM_MODEL=agent-model


setup() {
  {
    date -u +"setup started %FT%TZ"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    python3 --version
    free -g | sed -n 2p
    df -h / /dev/shm "$(dirname "$HF_HOME")" | sed 1d
  } > "$OUT/system.log" 2>&1
  python3 -m pip install -q uv || python3 -m pip install -q --break-system-packages uv
  (
    HF_HUB_DISABLE_PROGRESS_BARS=1 HF_XET_HIGH_PERFORMANCE=1 \
      uvx --from "huggingface_hub[hf_xet]" hf download "$MODEL"
    echo "download exit $?"
  ) > "$OUT/download.log" 2>&1 &
  (
    [ -d "$REPO/harness" ] || git clone -q -b "${BRANCH:-main}" "$REPO_URL" "$REPO"
    uv venv -q "$HARNESS_VENV" --python 3.12 \
      && uv pip install -q --python "$PY" -r "$REPO/requirements.txt"
    echo "harness install exit $?"
  ) > "$OUT/harness_install.log" 2>&1 &
  (
    uv venv -q "$VENV" --python 3.12 \
      && uv pip install -q --python "$VENV/bin/python" vllm pip --torch-backend=auto \
      && PATH="$VENV/bin:$PATH" vllm download-kernels
    echo "vllm install exit $?"
  ) > "$OUT/vllm_install.log" 2>&1 &
  wait
  date -u +"setup finished %FT%TZ" >> "$OUT/system.log"
  tail -q -n 1 "$OUT/download.log" "$OUT/harness_install.log" "$OUT/vllm_install.log"
}


serve() {
  if [ -n "$TEMPLATE" ]; then
    version=$("$VENV/bin/python" -c "import vllm; print(vllm.__version__)")
    raw=https://raw.githubusercontent.com/vllm-project/vllm
    curl -fsSL -o "/root/$TEMPLATE" "$raw/v$version/examples/$TEMPLATE" \
      || curl -fsSL -o "/root/$TEMPLATE" "$raw/main/examples/$TEMPLATE"
  fi
  date -u +"serve started %FT%TZ" >> "$OUT/system.log"
  # shellcheck disable=SC2086
  setsid nohup "$VENV/bin/vllm" serve "$MODEL" \
    --host 127.0.0.1 --port 8000 --served-model-name agent-model \
    "${SERVE[@]}" ${SERVE_EXTRA:-} > "$OUT/vllm.log" 2>&1 &
  sleep 5
  for _ in $(seq 1 $(( ${READY_TIMEOUT:-3600} / 10 ))); do
    code=$(curl -s -o /dev/null -m 3 -w '%{http_code}' http://127.0.0.1:8000/health)
    if [ "$code" = 200 ]; then
      date -u +"server ready %FT%TZ" >> "$OUT/system.log"
      echo "server ready"
      return 0
    fi
    if ! pgrep -f "bin/vllm serve" > /dev/null; then
      echo "the server stopped; last lines of $OUT/vllm.log:"
      tail -n 15 "$OUT/vllm.log"
      return 1
    fi
    sleep 10
  done
  echo "the server was not ready in time"
  return 1
}


smoke() {
  cd "$REPO" || return 1
  curl -s http://127.0.0.1:8000/v1/models | head -c 400 > "$OUT/models.json"
  $PY harness/smoke_test.py > "$OUT/smoke.log" 2>&1
  echo "exit $?" >> "$OUT/smoke.log"
  AGENT_WORKSPACE=/root/task-workspace AGENT_TRACE=$OUT/task_trace.jsonl \
    AGENT_CHECKPOINTS=/root/task-checkpoints \
    $PY harness/mini_harness.py "Create notes/todo.md with three items and read it back" \
    > "$OUT/task.log" 2>&1
  echo "exit $?" >> "$OUT/task.log"
  cat "$OUT/smoke.log"
  tail -n 6 "$OUT/task.log"
}


evals() {
  cd "$REPO" || return 1
  shards=${SHARDS:-1}
  for level in ${EFFORTS:-low medium high}; do          # all of them side by side
    for shard in $(seq 0 $((shards - 1))); do
      run=$OUT/evals_${level}_$shard
      AGENT_WORKSPACE=$run-eval-workspace AGENT_TRACE=$run.trace.jsonl \
        AGENT_CHECKPOINTS=$run-checkpoints \
        $PY harness/run_evals.py "${EVALS:-evals/tasks.agent.jsonl}" 1 --effort "$level" \
        --shard "$shard/$shards" > "$run.json" 2> "$run.err" &
    done
  done
  wait
  date -u +"evals finished %FT%TZ" >> "$OUT/system.log"
  $PY - "$OUT" ${EFFORTS:-low medium high} <<'EOF'
import glob, json, sys
out, levels = sys.argv[1], sys.argv[2:]
print(f"{'effort':8}{'passed':>8}{'avg steps':>11}{'avg output tokens':>19}"
      f"{'avg reasoning chars':>21}{'avg seconds':>13}{'tool failures':>15}")
for level in levels:
    rows = []
    for path in sorted(glob.glob(f"{out}/evals_{level}_*.json")):
        try:
            rows += json.load(open(path))["rows"]
        except (OSError, ValueError):
            print(f"{level:8}  no result in {path}: see its .err file")
    if not rows:
        continue
    n, calls = len(rows), sum(r["tool_calls"] for r in rows) or 1
    mean = lambda key: sum(r[key] for r in rows) / n
    print(f"{level:8}{sum(r['passed'] for r in rows):>5}/{n:<2}{mean('steps'):>11.1f}"
          f"{mean('output_tokens'):>19.0f}{mean('reasoning_chars'):>21.0f}{mean('seconds'):>13.1f}"
          f"{sum(r['tool_failures'] for r in rows) / calls:>15.3f}")
    for row in rows:
        if not row["passed"]:
            print(f"    failed {row['id']}: {' '.join(row['why'].split())[-110:]}")
EOF
}


for step in $STEPS; do
  case "$step" in
    setup|serve|smoke|evals) echo "== $step ==" ;;
    *) echo "unknown step: $step"; exit 2 ;;
  esac
  "$step" || { echo "$step failed"; exit 1; }
done
