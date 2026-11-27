#!/usr/bin/env bash
# Rebuild the Word document from the code, the cost data and the figures.
# Run from the repository root:  bash docs/build/make.sh
# Needs: Python with matplotlib and pillow, Node.js with the "docx" package (npm install docx).
set -euo pipefail

python3 infra/costs.py > /dev/null          # docs/build/out/costs.json
python3 docs/build/excerpts.py > /dev/null  # docs/build/out/excerpts.json (cut from the code)
python3 docs/build/figures.py               # docs/img/fig_loop.png, fig_deploy.png
python3 docs/build/ui_figure.py             # docs/img/ui-flow.png, if new screenshots exist
node docs/build/build_doc.js               # docs/agent-harness-open-models-runpod.docx
# Word can refuse a file whose ZIP has folder entries when it is opened through a cloud
# co-editing service, so drop them.
zip -d docs/agent-harness-open-models-runpod.docx '*/' > /dev/null 2>&1 || true
