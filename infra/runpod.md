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

Not included: a host for the harness (a 4 vCPU, 8 GB CPU pod is about $86 a month always
on) and container disk. Multi-GPU on-demand capacity for H200 and B200 was limited in
November 2026, so keep a fallback configuration for the C and D rows.

## Pod template

| Setting | Value |
|---|---|
| Container image | `vllm/vllm-openai` with a pinned tag, not `latest`. Gemma 4 on H100 or H200: `gemma4-0505-cu129`. DeepSeek recipe image: `v0.28.0`. Mistral Small 4: a release at or above 0.20.0. |
| Start command | `vllm serve <model> <flags>` as below. If the pod log shows an argument error on first boot, the image's entrypoint already runs the server: remove the leading `vllm serve`. |
| Environment | `HF_TOKEN` for gated models, `HF_HOME=/workspace/hf` so the cache sits on the volume, `VLLM_API_KEY` for the endpoint key, `VLLM_WORKER_MULTIPROC_METHOD=spawn` on multi-GPU pods. |
| Storage | Network volume mounted at `/workspace` (150 GB for Gemma 4, 250 GB for Mistral Small 4, 400 GB for DeepSeek V4-Flash). Container disk 30 to 50 GB. |
| Ports | Expose HTTP port 8000 only if you use the proxy. The server must bind to `0.0.0.0`. |
| Cloud | Secure Cloud. Switch on global networking if other GPU pods need private access. |

Create the network volume first, in a data centre that offers your GPU type: a volume
lives in one data centre and has to be attached when the pod is created.

## Serve commands

Taken from the vLLM recipes, with host, port and a stable served model name added.
None of them was run on a live GPU for this repository.

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
