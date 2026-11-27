"""Cost arithmetic for the document, README and infra notes.

Rates: runpod.io/pricing Pods cards, read 27 Nov 2026 (Secure Cloud, on-demand).
Edit RATE and re-run from the repository root:  python infra/costs.py
"""
import json
from pathlib import Path

RATE = {  # USD per GPU-hour, on-demand
    "B200": 7.99, "H200": 5.29, "H100 SXM": 4.39, "H100 NVL": 3.19, "H100 PCIe": 2.89,
    "A100 PCIe": 2.09, "A100 SXM": 2.19, "RTX PRO 6000": 2.69, "L40S": 1.09, "RTX A6000": 0.69, "A40": 0.59,
}
VRAM = {"B200": 180, "H200": 141, "H100 SXM": 80, "H100 NVL": 94, "H100 PCIe": 80, "A100 PCIe": 80,
        "A100 SXM": 80, "RTX PRO 6000": 96, "L40S": 48, "RTX A6000": 48, "A40": 48}
COMMUNITY_FROM = {"H200": 3.59, "H100 PCIe": 1.99, "H100 SXM": 2.69, "A100 PCIe": 1.19, "A100 SXM": 1.39}

HOURS_WORK = 8 * 22          # 176 h: working hours, 22 days
HOURS_ALWAYS = 24 * 365 / 12 # 730 h: always on

configs = [
    # id, model, precision, gpu, count, volume_gb
    ("A1", "Gemma 4 26B-A4B", "BF16", "A100 PCIe", 1, 150),
    ("A2", "Gemma 4 26B-A4B", "BF16", "H100 PCIe", 1, 150),
    ("B1", "Gemma 4 31B", "BF16", "H200", 1, 150),
    ("B2", "Gemma 4 31B", "BF16", "H100 PCIe", 2, 150),
    ("C1", "Mistral Small 4", "FP8", "H200", 2, 250),
    ("C2", "Mistral Small 4", "NVFP4", "B200", 1, 250),
    ("C3", "Mistral Small 4", "NVFP4", "B200", 2, 250),
    ("D1", "DeepSeek V4-Flash", "FP8 (0731)", "H200", 8, 400),
    ("D2", "DeepSeek V4-Flash", "NVFP4", "B200", 4, 400),
    ("D3", "DeepSeek V4-Flash", "FP8 (0731)", "H100 PCIe", 8, 400),
]
NV_RATE = 0.07  # USD per GB-month, network volume under 1 TB
out = []
for cid, model, prec, gpu, n, vol in configs:
    hourly = round(RATE[gpu] * n, 2)
    storage = round(vol * NV_RATE, 2)
    out.append({
        "id": cid, "model": model, "precision": prec, "gpu": gpu, "count": n,
        "vram_total": VRAM[gpu] * n, "hourly": hourly,
        "work_month": round(hourly * HOURS_WORK, 2), "always_month": round(hourly * HOURS_ALWAYS, 2),
        "volume_gb": vol, "storage_month": storage,
        "work_total": round(hourly * HOURS_WORK + storage, 2),
        "always_total": round(hourly * HOURS_ALWAYS + storage, 2),
        "community_hourly": round(COMMUNITY_FROM[gpu] * n, 2) if gpu in COMMUNITY_FROM else None,
    })
for r in out:
    print(r)

# headroom after weights at 0.90 utilisation (arithmetic, not a benchmark)
weights = {"Gemma 4 26B-A4B BF16": 49, "Gemma 4 31B BF16": 62, "Mistral Small 4 NVFP4": 72, "DeepSeek V4-Flash FP8 preview": 160}
head = []
for label, w, gpu, n in [("Gemma 4 26B-A4B BF16", 49, "A100 PCIe", 1), ("Gemma 4 26B-A4B BF16", 49, "H200", 1),
                         ("Gemma 4 31B BF16", 62, "H100 PCIe", 1), ("Gemma 4 31B BF16", 62, "H200", 1),
                         ("Gemma 4 31B BF16", 62, "H100 PCIe", 2),
                         ("Mistral Small 4 NVFP4", 72, "B200", 1), ("Mistral Small 4 NVFP4", 72, "B200", 2),
                         ("DeepSeek V4-Flash FP8 preview", 160, "H200", 8), ("DeepSeek V4-Flash FP8 preview", 160, "H100 PCIe", 8)]:
    usable = round(VRAM[gpu] * n * 0.90, 1)
    head.append({"model": label, "gpu": f"{n}x {gpu}", "usable_gb": usable, "weights_gb": w, "headroom_gb": round(usable - w, 1)})
print()
for h in head: print(h)

# illustrative unit cost
hourly, minutes, concurrent = 2.89, 4, 6
print("\nillustrative cost per task:", round(hourly * (minutes / 60) / concurrent, 4))
# B200 sensitivity if tracker's 8.99 is right
print("B200 at 8.99: x1 =", 8.99, "x2 =", round(8.99*2,2), "x4 =", round(8.99*4,2), "uplift %", round((8.99/7.99-1)*100,1))
# cpu pod
print("cpu pod 4vCPU/8GB monthly 86.40 -> hourly", round(86.40/720, 3))
print("hours:", HOURS_WORK, HOURS_ALWAYS)
Path("docs/build/out").mkdir(parents=True, exist_ok=True)
json.dump({"configs": out, "headroom": head, "rates": RATE, "vram": VRAM, "community_from": COMMUNITY_FROM,
           "hours_work": HOURS_WORK, "hours_always": HOURS_ALWAYS}, open("docs/build/out/costs.json", "w"), indent=1)
