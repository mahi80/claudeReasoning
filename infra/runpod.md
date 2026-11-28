# Runpod on-demand infrastructure

Everything here assumes **on-demand Pods on Secure Cloud** and vLLM as the model server.
The full reasoning, with sources, is in section 5 of
[`docs/agent-harness-open-models-runpod.docx`](../docs/agent-harness-open-models-runpod.docx).

> Prices were read from https://www.runpod.io/pricing on 27 November 2026. Runpod changes
> them often. Edit `RATE` in [`costs.py`](costs.py) and run `python infra/costs.py` to
> recalculate. One tracker recorded B200 at $8.99 on 25 to 26 November; if that is the
> live rate, every B200 figure below is 12.5% higher.

## GPU prices used

| GPU | VRAM | Secure Cloud, per hour | Community Cloud, from |
|---|---|---|---|
| B200 | 180 GB | $7.99 | not listed |
| H200 | 141 GB | $5.29 | $3.59 |
| H100 SXM | 80 GB | $4.39 | $2.69 |
| H100 NVL | 94 GB | $3.19 | not listed |
| H100 PCIe | 80 GB | $2.89 | $1.99 |
| A100 PCIe | 80 GB | $2.09 | $1.19 |
| A100 SXM | 80 GB | $2.19 | $1.39 |
| RTX PRO 6000 | 96 GB | $2.69 | not listed |
| L40S | 48 GB | $1.09 | not listed |
| RTX A6000 | 48 GB | $0.69 | not listed |
| A40 | 48 GB | $0.59 | not listed |

## Pod configurations and monthly cost

Month totals are the GPU cost plus a network volume for the weights at $0.07/GB/month.
176 h is 8 hours on 22 working days; 730 h is always on.

| ID | Model and precision | Pod | VRAM | Per hour | Month, 176 h | Month, 730 h | Basis |
|---|---|---|---|---|---|---|---|
| A1 | Gemma 4 26B-A4B, BF16 | 1x A100 PCIe | 80 GB | $2.09 | $378 | $1,536 | vLLM recipe (1x A100 or H100) |
| A2 | Gemma 4 26B-A4B, BF16 | 1x H100 PCIe | 80 GB | $2.89 | $519 | $2,120 | vLLM recipe (1x A100 or H100) |
| B1 | Gemma 4 31B, BF16 | 1x H200 | 141 GB | $5.29 | $942 | $3,872 | Sized from the 62 GB weights; the recipe lists one 80 GB GPU as the minimum |
| B2 | Gemma 4 31B, BF16 | 2x H100 PCIe | 160 GB | $5.78 | $1,028 | $4,230 | vLLM recipe (TP2) |
| C1 | Mistral Small 4, FP8 | 2x H200 | 282 GB | $10.58 | $1,880 | $7,741 | vLLM recipe; context may need cutting to 131K or 65K |
| C2 | Mistral Small 4, NVFP4 | 1x B200 | 180 GB | $7.99 | $1,424 | $5,850 | vLLM recipe, reduced context |
| C3 | Mistral Small 4, NVFP4 | 2x B200 | 360 GB | $15.98 | $2,830 | $11,683 | vLLM recipe, full 256K |
| D1 | DeepSeek V4-Flash, FP8 (0731) | 8x H200 | 1128 GB | $42.32 | $7,476 | $30,922 | vLLM recipe default (TP8 with expert parallel) |
| D2 | DeepSeek V4-Flash, NVFP4 | 4x B200 | 720 GB | $31.96 | $5,653 | $23,359 | NVIDIA Dynamo recipe |
| D3 | DeepSeek V4-Flash, FP8 (0731) | 8x H100 PCIe | 640 GB | $23.12 | $4,097 | $16,906 | Reported in the vLLM recipe; sensitive to the vLLM version |
| E1 | DeepSeek V4.1-Flash, FP8 (1017) | 4x H200 | 564 GB | $21.16 | $3,773 | $15,496 | vLLM recipe, verified (TP4, Engram tables in host memory) |
| E2 | DeepSeek V4.1-Flash, FP8 (1017) | 2x B200 | 360 GB | $15.98 | $2,861 | $11,714 | vLLM recipe, verified for low concurrency (TP2, at most 8 sequences) |
| E3 | DeepSeek V4.1-Flash, FP8 (1017) | 8x H100 PCIe | 640 GB | $23.12 | $4,118 | $16,927 | vLLM recipe: TP8 on 80 GB cards, with extra memory settings |

Not included: a host for the harness (a 4 vCPU, 8 GB CPU pod is about $86 a month always
on) and container disk. Multi-GPU on-demand capacity for H200 and B200 was limited in
November 2026, so keep a fallback configuration for the C, D and E rows.

The D rows are the configurations the V4-Flash recipe publishes, all on 8-GPU nodes. Its
0731 checkpoint needs about 200 GB of GPU memory with headroom, and the recipe mentions
reports of 4x H100 working, so a smaller pod may run it. Treat that as an experiment.

## Pod template

| Setting | Value |
|---|---|
| Container image | `vllm/vllm-openai` with a pinned tag, not `latest`. Gemma 4 on H100 or H200: `gemma4-0505-cu129`. DeepSeek V4-Flash recipe image: `v0.28.0`. DeepSeek V4.1-Flash: a release at or above 0.31.0. Mistral Small 4: a release at or above 0.20.0. |
| Start command | `vllm serve <model> <flags>` as below. If the pod log shows an argument error on first boot, the image's entrypoint already runs the server: remove the leading `vllm serve`. |
| Environment | `HF_TOKEN` for gated models, `HF_HOME=/workspace/hf` so the cache sits on the volume, `VLLM_API_KEY` for the endpoint key, `VLLM_WORKER_MULTIPROC_METHOD=spawn` on multi-GPU pods. |
| Storage | Network volume mounted at `/workspace` (150 GB for Gemma 4, 250 GB for Mistral Small 4, 400 GB for DeepSeek V4-Flash, 700 GB for DeepSeek V4.1-Flash). Container disk 30 to 50 GB. |
| Ports | Expose HTTP port 8000 only if you use the proxy. The server must bind to `0.0.0.0`. |
| Cloud | Secure Cloud. Switch on global networking if other GPU pods need private access. |

Create the network volume first, in a data centre that offers your GPU type: a volume
lives in one data centre and has to be attached when the pod is created.

## Serve commands

The larger configurations below come from the vLLM recipes, with host, port and a
stable served model name added; they remain untested on live GPUs for this repository.
A separate one-B300 DeepSeek V4-Flash experiment is described below. Do not treat it as
validation of the eight-GPU recipe, V4.1, Gemma or Mistral presets.

### Gemma 4 26B-A4B on one 80 GB GPU (A1, A2)

```bash
vllm serve google/gemma-4-26B-A4B-it \
  --host 0.0.0.0 --port 8000 --served-model-name agent-model \
  --max-model-len 32768 --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \
  --chat-template examples/tool_chat_template_gemma4.jinja
```

For the 31B model on one H200 (B1) use `google/gemma-4-31B-it`. On two H100s (B2) also
add `--tensor-parallel-size 2`. The chat template ships in the vLLM repository's
`examples` folder; if the image does not contain it, download it to the volume and pass
the full path.

### Mistral Small 4 on two H200s (C1)

```bash
vllm serve mistralai/Mistral-Small-4-119B-2603 \
  --host 0.0.0.0 --port 8000 --served-model-name agent-model \
  --max-model-len 131072 --tensor-parallel-size 2 \
  --enable-auto-tool-choice --tool-call-parser mistral --reasoning-parser mistral
```

The recipe's own command uses 262144 and warns that the full context can run out of
memory on two H200s. It needs vLLM 0.20.0 or later and `mistral_common` 1.11.0 or later.

### DeepSeek V4-Flash on eight H200s (D1)

```bash
export VLLM_USE_RUST_FRONTEND=1
vllm serve deepseek-ai/DeepSeek-V4-Flash-0731 \
  --host 0.0.0.0 --port 8000 --served-model-name agent-model \
  --trust-remote-code --kv-cache-dtype fp8 --block-size 256 \
  --enable-expert-parallel --tensor-parallel-size 8 \
  --tokenizer-mode deepseek_v4 --tool-call-parser deepseek_v4 \
  --enable-auto-tool-choice --reasoning-parser deepseek_v4 \
  --reasoning-config '{"reasoning_parser":"deepseek_v4","reasoning_start_str":"","reasoning_end_str":""}' \
  --speculative-config '{"method":"dspark","num_speculative_tokens":7,"draft_sample_method":"probabilistic"}'
```

Needs vLLM 0.25.0 or later. `--trust-remote-code` runs code from the model repository,
so pin the revision and review it first.

### DeepSeek V4.1-Flash on four H200s (E1)

```bash
export VLLM_ENGINE_READY_TIMEOUT_S=3600
export VLLM_USE_RUST_FRONTEND=1
vllm serve deepseek-ai/DeepSeek-V4.1-Flash-1017 \
  --host 0.0.0.0 --port 8000 --served-model-name agent-model \
  --tokenizer-mode deepseek_v41 --tensor-parallel-size 4 \
  --engram-config '{"cpu_offload":true}' \
  --tool-call-parser deepseek_v41 --enable-auto-tool-choice \
  --reasoning-parser deepseek_v41 \
  --language-model-only
```

Assembled from the recipe's H200 settings (TP4, Engram tables in host memory, tool and
reasoning parsers) with host, port and served name added. It was not run for this
repository. Needs vLLM 0.31.0 or later.

- **What the model is.** V4.1-Flash is the successor to V4-Flash: 552B backbone
  parameters plus 196B of Engram memory tables, 8B active per prompt token and 16B per
  output token, text and image input, 1M context, MIT licence. Released 9 September
  2026; the `-1017` repository holds the 17 October weight update the recipe recommends.
- **Text only.** `--language-model-only` skips the vision encoder and leaves that
  memory for the KV cache. Drop it to accept images; the recipe then adds
  `--mm-encoder-tp-mode data`.
- **Host memory.** `cpu_offload` moves the Engram tables (183 GiB) into pinned system
  memory. On H200 the recipe reports 81.2 GiB of weights and 38.5 GiB of KV cache per
  GPU afterwards. Runpod lists 276 GB of system RAM per H200 and 283 GB per B200, so a
  4x H200 pod should have about 1,100 GB.
- **Not proven on Runpod.** The recipe's Docker example runs the container privileged
  with host IPC, and Runpod's documented pod settings include neither. Whether the
  host-memory offload starts cleanly in a pod is the first thing to test.
- **Checkpoint and cold start.** The checkpoint is about 511 GB, so use a 700 GB
  volume and expect a long first download. The recipe allows 3,600 seconds for the
  server to become ready. Set `POD_START_TIMEOUT=3900` for the pod manager and choose
  the idle timeout with that reload time in mind.
- **Two B200s (E2).** The recipe uses `--tensor-parallel-size 2` with its Blackwell
  attention settings, THP-backed Engram offload, `--max-num-seqs 8` and
  `--max-num-batched-tokens 4096`. It is tuned for one agent session at a time; the
  recipe points to TP4 for more interactivity.
- **Eight H100s (E3).** On 80 GB cards the recipe needs all eight: TP8, Engram
  offload, `--max-num-batched-tokens 4096`,
  `--gpu-memory-utilization 0.92`, `VLLM_USE_V2_MODEL_RUNNER=1` and
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.

Take the exact B200 and H100 commands from the recipe page's command builder.

## Disposable-pod test script and observed results

`infra/pod_test.sh` runs inside a Linux GPU pod using the PyTorch template. Choose
`gemma4`, `deepseek-v4` or `deepseek-v41`; omitted steps run `setup serve smoke evals`.
It installs vLLM and downloads weights, so pin versions/revisions separately for a
repeatable deployment. It uses `--trust-remote-code` for V4: review and pin that code.

```bash
bash infra/pod_test.sh gemma4 setup serve smoke
OUT=/root/eval-round-1 EVALS=evals/tasks.agent.jsonl EFFORTS="low medium" SHARDS=2 \
  bash infra/pod_test.sh gemma4 evals
```

`EVALS` selects the task file; `tasks.agent.jsonl` contains 19 cases, the last of which
(`make-tests-pass`) expects the runner argument `--delivery evals/delivery.evals.json` so
the agent can run the tests itself. `SHARDS=2` splits
those cases over two processes per effort level (runner arguments `--shard 0/2` and
`--shard 1/2`). All levels/shards run concurrently, so choose concurrency the GPU can
support. Use a new `OUT` directory per experiment to avoid mixing previous results.
Outputs include `system.log`, `download.log`, `vllm.log`, `smoke.log`, `task.log`, and
`evals_<level>_<shard>.json` plus `.err`, `.trace.jsonl`, workspaces and checkpoints.
Inspect failed answers and traces, not just artifact files or shell exit codes.

The V4 script defaults to 131,072 context. `SERVE_EXTRA` can append flags such as
`--max-model-len 32768 --max-num-seqs 2`; if you change the server context, set
`LLM_CONTEXT_WINDOW=32768` on the harness too. The script's V4 preset exports 131,072
internally, so run the harness directly with matching settings rather than assume an
environment override on `pod_test.sh smoke/evals` is retained. Do not add
`--enforce-eager` to the revalidated B300 configuration below.

**Initial experiment on 27 November 2026, commit `f00e4ea`:** one B300 (288 GB),
vLLM 0.34.0, `deepseek-ai/DeepSeek-V4-Flash-0731` revision
`7872f01b1d1fe23eabc4c98b48bffcef5a386062`, localhost-only serving, 32,768 context,
`--max-num-seqs 2`, eager execution and `VLLM_DEEP_GEMM_WARMUP=skip`. Protocol probes
passed 8/8 and shared-budget stop checks passed 4/4. Both full workflows passed 10/13
checks but stopped at 600 seconds without independent PASS. Four selected cases at
low/medium passed 3/8 under 90-second limits, not a full 18-case benchmark. The pod
quoted $10.49/hour; conservative rental estimate was $9.57 and shutdown was verified
at $0/hour. These initial results remain separate from the revalidation below.

### Revalidated B300 configuration

The current local reviewer-evidence, reply-reservation and approval fixes were tested
on 27 November 2026 as an uncommitted source snapshot based on `f00e4ea`. Forced eager
execution still timed out. On the same pod, replacing it with decode CUDA graphs and
kernel warmup completed the original workflow in 63.9 seconds: all 17 checks passed,
including an independent reviewer workspace read and recorded PASS. The 600-second
limit, xhigh/high-native thinking, worker scopes, approvals and review policy were
unchanged. No runtime source edits were needed for this serving fix.

Use vLLM **0.34.0** and the pinned model revision with this tested command:

```bash
export HF_HOME=/root/hf VLLM_DEEP_GEMM_WARMUP=skip VLLM_ENGINE_READY_TIMEOUT_S=600
vllm serve deepseek-ai/DeepSeek-V4-Flash-0731 \
  --revision 7872f01b1d1fe23eabc4c98b48bffcef5a386062 \
  --host 127.0.0.1 --port 8000 --served-model-name agent-model \
  --trust-remote-code --kv-cache-dtype fp8 --block-size 256 \
  --tensor-parallel-size 1 --gpu-memory-utilization 0.92 \
  --attention_config.indexer_kv_dtype mxfp4 --no-enable-flashinfer-autotune \
  --tokenizer-mode deepseek_v4 --enable-auto-tool-choice --tool-call-parser deepseek_v4 \
  --reasoning-parser deepseek_v4 --reasoning-config \
  '{"reasoning_parser":"deepseek_v4","reasoning_start_str":"","reasoning_end_str":""}' \
  --max-model-len 32768 --max-num-seqs 2 \
  --compilation-config '{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,2]}'
```

Wait for `/health` before starting the harness. Set `LLM_CONTEXT_WINDOW=32768`,
`LLM_THINKING_SCOPE=task` and `LLM_KEEP_REASONING=1`; use the DeepSeek V4 thinking
settings below with high native thinking for xhigh. This is a one-B300, low-concurrency
configuration, not validation of the larger presets, other contexts or max thinking.

The graph-enabled run passed protocol checks 8/8, shared-budget stop checks 4/4 and
missing/denied reviewer-evidence rejection checks 3/3. Separately labeled token/cost
admission checks passed 7/7; the initial exact-OK response-format failure is preserved.
All four selected cases at low/medium passed 8/8 under both the original 90-second
limits and separately labeled 180-second limits. The full 18-case benchmark was not run.

Both baseline and final evidence archives were downloaded and every recorded output
and source hash verified before stopping the new pod. Compute and container storage
were confirmed not running at $0/hour; the conservative new-spend estimate was $11.05
within the authorized $20 cap, not a final invoice. The script does not stop a pod or
enforce a rental cap. Export results, stop the pod and verify billing has stopped.
Agent time/token budgets do not include setup or rental.

## Smoke tests

```bash
curl https://<POD_ID>-8000.proxy.runpod.net/health
curl https://<POD_ID>-8000.proxy.runpod.net/v1/models -H "Authorization: Bearer $KEY"
LLM_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1 LLM_API_KEY=$KEY \
    python harness/smoke_test.py
```

The last command fails unless the reply contains a parsed tool call whose arguments
match a strict schema. A tool call that arrives as plain text means the parser or chat
template is wrong for that model.

## Thinking switches for the effort levels

The harness turns the model's own thinking on and off per call, according to the effort
level. Each model takes different request fields, so they are configuration:
`LLM_THINKING` is a JSON map with `off`, `on` and optionally `max` and `brief`. Set
`LLM_CONTEXT_WINDOW` to the `--max-model-len` you serve. `LLM_THINKING_SCOPE=step` is
the default; `task` keeps medium on throughout using `brief` if defined, otherwise
`on`. Low remains off and high remains on.

These fields come from the vLLM documentation, recipes and source at commit `c58be70`
(27 November 2026). The separate V4-Flash 0731 experiment exercised live thinking/tool
probes; the other models and max-thinking configurations below were not validated live.
With `LLM_THINKING` set, `harness/smoke_test.py` sends one request per fragment and fails
if `on` returns no reasoning or `off` returns some.

### Gemma 4

```bash
export LLM_THINKING='{"off": {"chat_template_kwargs": {"enable_thinking": false}},
                      "on":  {"chat_template_kwargs": {"enable_thinking": true}}}'
export LLM_KEEP_REASONING=1
export LLM_CONTEXT_WINDOW=32768
```

Thinking is off unless switched on. Google says thoughts must stay in place between
function calls, and vLLM's Gemma 4 template renders returned reasoning for the messages
after the last user message, hence `LLM_KEEP_REASONING=1`. The switch is a token at the
top of the system turn, so each flip defeats the server's prefix cache for that call.
Google describes thinking as a conversation-level setting, so use
`LLM_THINKING_SCOPE=task` for medium effort (the Gemma pod-test preset already does).
Medium then uses `on` throughout, or a configured `brief` fragment; no change to
`EFFORTS` is needed. Validate the switch with your exact model/template.

### Mistral Small 4

```bash
export LLM_THINKING='{"off": {"reasoning_effort": "none"},
                      "on":  {"reasoning_effort": "high", "temperature": 0.7}}'
export LLM_CONTEXT_WINDOW=131072
```

Only two settings exist, and they are made to be switched per request. The recipe asks
for temperature 0.7 with reasoning; a fragment can carry it. Leave `LLM_KEEP_REASONING`
unset: nothing in vLLM's Mistral-specific code reads returned reasoning.

### DeepSeek V4-Flash

```bash
export LLM_THINKING='{"off": {"chat_template_kwargs": {"thinking": false}},
  "on":  {"chat_template_kwargs": {"thinking": true, "reasoning_effort": "high"}},
  "max": {"chat_template_kwargs": {"thinking": true, "reasoning_effort": "max"}}}'
export LLM_KEEP_REASONING=1
export LLM_TEMPERATURE=1.0
export LLM_EXTRA_BODY='{"top_p": 0.95}'
```

vLLM's DeepSeek V4 tokenizer turns thinking on when no switch is sent, so the `off`
fragment matters. With tools in the request the encoder keeps reasoning for the whole
conversation, provided the client sends it back. The recipe asks for `--max-model-len`
of at least 393216 in max mode; set `LLM_CONTEXT_WINDOW` to whatever you serve. The 0731
release also has a `low` level, which you can use for `on` to make high effort cheaper.

### DeepSeek V4.1-Flash

```bash
export LLM_THINKING='{"off": {"chat_template_kwargs": {"thinking": false}},
  "on":  {"chat_template_kwargs": {"thinking": true, "reasoning_effort": 50}},
  "max": {"chat_template_kwargs": {"thinking": true, "reasoning_effort": 100}}}'
export LLM_KEEP_REASONING=1
export LLM_TEMPERATURE=1.0
export LLM_EXTRA_BODY='{"top_p": 0.95}'
export LLM_CONTEXT_WINDOW=1048576
```

Thinking is on unless switched off, so the `off` fragment matters here too. Effort is a
number from 1 to 100. The names `low`, `high`, `xhigh` and `max` also work, but the
recipe and vLLM's source map them to different numbers, so send the number. The encoder
keeps reasoning across a tool-calling conversation, as for V4-Flash.

Watch the reply budget. The recipe warns that a small `max_tokens` can return an empty
reply when thinking uses it up, and DeepSeek ran its effort-100 benchmarks with at
least 256K output tokens. The harness retries an empty reply once without thinking and
records a `blank` event in the trace. If you see those, raise `max_tokens` for the
level in `EFFORTS`, or lower the effort number in the `on` fragment.

### Room for thinking

Thinking counts against the reply budget (4,096 tokens at low and medium effort, 8,192
at high and xhigh, 16,384 at max), and prompt plus reply must fit `--max-model-len`. The
harness lowers its prompt budget to fit the window you declare. With 32,768 it keeps
24,000 prompt tokens at low and medium, 20,480 at high and xhigh, and 12,288 at max, so
serve a larger window (65536 if the KV cache can hold it) for regular use of xhigh or
max. vLLM's `thinking_token_budget` request field caps reasoning tokens per call; add it
to the `on` fragment if replies come back empty.

## Reaching the model server

| Pattern | How | Watch out |
|---|---|---|
| Same pod | The harness runs next to vLLM and calls `http://localhost:8000/v1`. Nothing is exposed. | The agent's shell shares a container with the model server and its secrets. |
| Runpod HTTPS proxy | `https://POD_ID-8000.proxy.runpod.net/v1` with an API key. Stream every response: an idle connection closes after 100 seconds. | The URL is public. vLLM's API key covers only the `/v1`, `/v2` and `/inference` paths, so other endpoints stay open. |
| Private between GPU pods | `http://POD_ID.runpod.internal:8000/v1` with global networking. | GPU pods only, in supported Secure Cloud data centres. |
| Reverse proxy or tunnel | vLLM bound to localhost behind an authenticating proxy in the same image, or reached through an SSH tunnel. | Needs a custom image, or an image that runs an SSH daemon. |

## Operating notes

- Treat pods as disposable. Everything durable sits on the network volume.
- Stop idle pods: `runpodctl pod stop POD_ID`, or let `harness/pod_manager.py` do it.
- A started pod has to boot and load the weights before `/health` answers. Measure that
  cold start for your model and show it in the UI.
- A pod is one container: Docker cannot run inside it. Put the agent's workspace on a
  separate disposable pod or VM that holds no credentials.
- Network volumes cannot be encrypted. Keep sensitive data off them.
- The default spend limit is $80 an hour across all resources.
