// Builds docs/agent-harness-open-models-runpod.docx from the tested sources and cost data.
// Run from the repository root: bash docs/build/make.sh   (needs: npm install docx)
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, HeadingLevel, LevelFormat, BorderStyle, ImageRun, Footer, Header, PageNumber,
  ExternalHyperlink, PageBreak, VerticalAlign, LineRuleType,
} = require("docx");

const costs = JSON.parse(fs.readFileSync("docs/build/out/costs.json", "utf8"));
const ex = JSON.parse(fs.readFileSync("docs/build/out/excerpts.json", "utf8"));

const W = 9026; // content width in DXA: A4 with 1-inch side margins
const NAVY = "1F3A5F", GREY = "5B6573", RULE = "BFC8D2", HEAD_FILL = "DCE6F1";
const CODE_FILL = "F3F4F6", NOTE_FILL = "FFF7E0", NOTE_EDGE = "E3C566";
const FONT = "Arial", MONO = "Courier New";
const BODY = 21, SMALL = 18;

const numberRefs = [];
const money = (n) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const whole = (n) => "$" + Math.round(n).toLocaleString("en-US");

// ---------------------------------------------------------------- inline text
function runs(text, base = {}) {
  const size = base.size || BODY;
  return String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter((s) => s !== "").map((part) => {
    if (part.startsWith("**")) return new TextRun({ ...base, text: part.slice(2, -2), bold: true });
    if (part.startsWith("`")) return new TextRun({ ...base, text: part.slice(1, -1), font: MONO, size: size - 2 });
    return new TextRun({ ...base, text: part });
  });
}
const P = (text, o = {}) => new Paragraph({ children: runs(text, o.run), spacing: { after: 120 }, ...o.para });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const gap = (h = 100) => new Paragraph({ spacing: { before: 0, after: 0, line: h, lineRule: LineRuleType.EXACT }, children: [] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });
const bullets = (items) => items.map((t) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, children: runs(t), spacing: { after: 60 },
}));
function numbered(items) {
  const reference = "num" + (numberRefs.length + 1);
  numberRefs.push(reference);
  return items.map((t) => new Paragraph({
    numbering: { reference, level: 0 }, children: runs(t), spacing: { after: 60 },
  }));
}
const note = (text) => new Paragraph({
  children: runs(text, { size: SMALL, color: GREY, italics: true }), spacing: { before: 40, after: 160 },
});

// ---------------------------------------------------------------- tables
const edge = { style: BorderStyle.SINGLE, size: 4, color: RULE };
const borders = { top: edge, bottom: edge, left: edge, right: edge, insideHorizontal: edge, insideVertical: edge };

function table(headers, rows, fractions) {
  const widths = fractions.map((f) => Math.round(W * f));
  widths[widths.length - 1] = W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const cell = (text, i, head) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { type: ShadingType.CLEAR, fill: HEAD_FILL, color: "auto" } : undefined,
    margins: { top: 70, bottom: 50, left: 100, right: 100 },
    verticalAlign: VerticalAlign.TOP,
    children: String(text).split("\n").map((line) => new Paragraph({
      spacing: { after: 30 }, children: runs(line, { size: SMALL, bold: head ? true : undefined }),
    })),
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths, borders,
    rows: [
      new TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) })),
    ],
  });
}

function callout(title, items) {
  const noteEdge = { style: BorderStyle.SINGLE, size: 6, color: NOTE_EDGE };
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W],
    borders: { top: noteEdge, bottom: noteEdge, left: noteEdge, right: noteEdge },
    rows: [new TableRow({ children: [new TableCell({
      width: { size: W, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: NOTE_FILL, color: "auto" },
      margins: { top: 120, bottom: 80, left: 160, right: 160 },
      children: [
        new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: title, bold: true, color: NAVY })] }),
        ...items.map((t) => new Paragraph({
          numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 }, children: runs(t, { size: 20 }),
        })),
      ],
    })] })],
  });
}

// ---------------------------------------------------------------- code and figures
function code(lines) {
  const n = lines.length;
  // short blocks stay whole; long ones never leave a few orphan lines on either page
  const keep = (i) => i < n - 1 && (n <= 14 || i < 4 || i >= n - 5);
  return lines.map((line, i) => new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: CODE_FILL, color: "auto" },
    indent: { left: 80 }, keepNext: keep(i),
    spacing: { before: i === 0 ? 40 : 0, after: i === n - 1 ? 160 : 0, line: 204, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: line === "" ? " " : line, font: MONO, size: 16 })],
  }));
}
function figure(file, width, height, caption) {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, keepNext: true,
      spacing: { before: 120, after: 60, line: 240, lineRule: LineRuleType.AUTO },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width, height } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: caption, italics: true, size: SMALL, color: GREY })],
    }),
  ];
}
const link = (label, url) => new ExternalHyperlink({
  link: url, children: [new TextRun({ text: label, color: "0B57A4", underline: {}, size: SMALL })],
});

// ================================================================ content
const c = [];
const add = (...items) => items.flat().forEach((x) => c.push(x));
const byId = Object.fromEntries(costs.configs.map((r) => [r.id, r]));

// ---------------------------------------------------------------- title
add(
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Building a Claude-style agent harness on open-weight models", bold: true, size: 44, color: NAVY })] }),
  new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: "How the reference harness works, how to build the same thing, and what it needs on Runpod on-demand Pods", size: 24, color: GREY })] }),
  new Paragraph({
    spacing: { after: 200 }, border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 6 } },
    children: [new TextRun({ text: "Version 1.0  |  27 November 2026  |  Companion code: github.com/mahi80/claudeReasoning", size: SMALL, color: GREY })],
  }),
  callout("Read this first", [
    "**Scope.** A pilot for one team (roughly 1 to 10 agent sessions at a time) on Runpod on-demand Pods, with Gemma 4, Mistral Small 4 or DeepSeek V4-Flash served by vLLM.",
    "**Prices.** Read from runpod.io/pricing on 27 November 2026 (Secure Cloud, on-demand). Runpod changes rates often, so confirm in the console before budgeting.",
    "**Code.** The Python in the companion repository passed 56 automated checks, all against mock endpoints (a mock model server and a mock Runpod API). Nothing here was run on live GPUs. The serve commands come from the vLLM recipes.",
    "**Section 2** describes Claude's own harness as the model sees it from inside the loop. The harness source code is not visible to the model, so read it as an informed description, not a specification.",
  ]),
  gap(200),
  new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: "Contents", bold: true, color: NAVY, size: 24 })] }),
  ...numbered([
    "Summary", "How the reference harness works", "Target architecture", "Model options",
    "Infrastructure on Runpod on-demand Pods", "Implementation guide",
    "End-to-end flow: chat UI to on-demand GPU", "Reliability playbook for open models",
    "Security and governance", "Delivery plan", "Risks and open decisions",
  ]),
  P("Appendix A: repository map and test coverage. Appendix B: sources.", { run: { color: GREY } }),
);

// ---------------------------------------------------------------- 1
add(
  pageBreak(), H1("1. Summary"),
  P("The agent this document copies is small. A model reads the conversation, asks for a tool, receives the result, and repeats until it answers in plain text. There is no graph framework. The routing lives in plain-language instructions and tool descriptions, and the model decides the next step on every turn."),
  P("The same design runs on open-weight models. What changes is reliability: open models call tools less dependably, so the model server and the harness have to enforce more."),
  H3("Recommended starting point"),
  table(["Decision", "Recommendation", "Why"], [
    ["Model", "Gemma 4 26B-A4B, BF16", "Apache 2.0, native function calling, fits one 80 GB GPU"],
    ["Pod", "1x A100 PCIe 80 GB at " + money(byId.A1.hourly) + "/h, or 1x H100 PCIe 80 GB at " + money(byId.A2.hourly) + "/h (Secure Cloud)", "This configuration is in the vLLM Gemma 4 recipe"],
    ["Serving", "vLLM with a pinned image tag, the tool-call parser for the exact model version, strict tool schemas and an API key", "Parsers are version-specific, and the Runpod proxy URL is public"],
    ["Harness", "About 420 lines of Python: loop, tools, subagents, skills, plan, checkpoints, compaction, trace", "In the companion repository, tested against a mock endpoint"],
    ["Front end", "HTMX chat page on FastAPI with live progress, approvals and on-demand GPU start", "Section 7; tested in headless Chrome"],
    ["Monthly cost", whole(byId.A1.work_total) + " to " + whole(byId.A2.work_total) + " at 176 working hours, storage included", "Section 5.4"],
    ["Next step up", "A bake-off on your own evals: Gemma 4 31B (" + money(byId.B1.hourly) + "/h), Mistral Small 4 (" + money(byId.C1.hourly) + "/h), DeepSeek V4-Flash (from " + money(byId.D3.hourly) + "/h)", "Choose from eval results and cost, not from model cards"],
  ], [0.16, 0.5, 0.34]),
  gap(),
  H3("Three things decide whether it works"),
  ...numbered([
    "**Tool-call reliability.** Enforced in the server with strict schemas, and in the loop with error feedback, repeat detection and a step cap.",
    "**Context discipline.** Clip tool output, fold old turns into a summary, and give heavy reading to subagents with their own context.",
    "**An eval set you re-run on every change.** Move a decision out of the prompt and into code only where the evals show the model cannot hold it.",
  ]),
);

// ---------------------------------------------------------------- 2
add(
  H1("2. How the reference harness works"),
  P("Claude runs in Anthropic's own harness (the Claude Agent SDK, the same base as Claude Code). It does not use LangGraph, CrewAI, AutoGen or a similar framework. The whole control structure is one loop."),
  H2("2.1 The loop"),
  ...numbered([
    "The model receives a system prompt with operating instructions, a list of tools (name, description, argument schema) and the conversation so far.",
    "It replies with text, or with one or more tool calls.",
    "The harness runs the calls and appends the results to the conversation.",
    "The model is called again. The loop ends when it replies without a tool call.",
  ]),
  P("No nodes, edges or state schema are declared anywhere. A subagent is just another tool call: it starts a second copy of the same loop with a fresh context and returns only a report."),
  ...figure("docs/img/fig_loop.png", 600, 338, "Figure 1. The loop and the four things it can reach"),
  H2("2.2 How it decides how many tools, skills and agents to use"),
  P("There is no formula. The choice is a judgment made at run time from what the model has been given."),
  table(["Decision", "What the model is given", "How the choice gets made"], [
    ["Which tool", "Each tool's name, description and argument schema", "It matches each sub-task against the descriptions. A good description says what the tool does and when to use it."],
    ["Whether to load a skill", "One line per skill: its name and when it applies", "It loads the full instructions only when the task matches, so an unused skill costs one line of context."],
    ["Whether to delegate", "A spawn tool whose description says when delegation pays off", "It splits the task into parts. Independent parts can go to parallel agents. Dependent parts stay in sequence."],
    ["How many agents", "No fixed number", "Roughly one per independent chunk, weighed against cost. A fresh agent starts with no context and needs a full brief."],
    ["What to do next", "The tool results and agent reports so far", "It re-plans after every result. The plan is not frozen at the start."],
    ["When to stop or ask", "Instructions on when to ask and when to proceed", "It stops when the task is done or when a decision belongs to the user."],
  ], [0.2, 0.33, 0.47]),
  note("This is the logic as the model can describe it, not a trace of its internals. It sometimes splits work too much or too little. An explicit instruction such as \"use three agents\" or \"no subagents\" overrides the default."),
  H2("2.3 What the harness does and what the model decides"),
  table(["Harness (code)", "Model (judgment)"], [
    ["Runs tools; enforces permissions and approvals", "Chooses the tool and its arguments"],
    ["Keeps the message list; compacts it when long", "Makes the plan and revises it after each result"],
    ["Starts subagents as separate loops and returns their report", "Decides whether to delegate and writes the brief"],
    ["Lists skills; loads a skill's text on request", "Decides when a skill applies"],
    ["Step caps, timeouts, logging", "Decides when the task is finished"],
  ], [0.5, 0.5]),
  gap(),
  H2("2.4 Thin loop or explicit graph"),
  table(["", "Thin loop (this design)", "Explicit graph (LangGraph style)"], [
    ["Control flow", "Chosen by the model at run time", "Declared in code as nodes and edges"],
    ["Best for", "Open-ended tasks with an unknown number of steps", "Fixed, repeatable workflows"],
    ["Audit and replay", "Weaker; relies on traces", "Stronger; paths are declared"],
    ["Adding a capability", "Add a tool and a description", "Add nodes, edges and state"],
    ["Typical failure", "The model wanders, loops or stops early", "Breaks on cases the graph did not foresee"],
    ["With weaker models", "Needs more guardrails", "Holds up better"],
  ], [0.2, 0.4, 0.4]),
  note("Rule of thumb: start thin. Wherever the evals show the model keeps failing a decision, move that decision into code. A fixed sub-workflow can sit behind a single tool."),
);

add(
  H2("2.5 Long-running tasks"),
  P("A long task uses the same rule: the model re-decides after every result. What changes is that the harness has to keep those decisions good over hundreds of steps, when the early turns no longer fit in the context."),
  table(["Mechanism", "What it does", "In the reference harness"], [
    ["A written plan", "The model writes a checklist first and ticks steps off. The harness pins the saved plan into every prompt, so it survives summarisation. At each step the model takes the next open item and picks the tool, skill or subagent for that item alone.", "`update_plan`; the plan is re-read from disk on every turn"],
    ["Skills loaded late", "Only the one-line index stays in context. A skill's full text is loaded when its stage starts.", "`load_skill`"],
    ["Subagents as context isolation", "Heavy or independent chunks go to workers and only reports come back. On a long run this protects the main context more than it saves time.", "`spawn_agent`"],
    ["Compaction", "Older turns are folded into a summary when the prompt passes its budget.", "`compact`"],
    ["Checkpoints", "State is saved after every finished step, so a crash or a stopped pod loses at most one step.", "`save_checkpoint`; `resume=True` or `--resume`"],
    ["Budgets", "Caps on steps, time and spend force a stop-and-report instead of drift.", "A step cap per agent; add time and spend caps for production"],
  ], [0.22, 0.5, 0.28]),
  note("In Claude's own harness the same roles are played by a task list the model maintains, skills loaded on demand and subagents."),
);

// ---------------------------------------------------------------- 3
add(
  H1("3. Target architecture"),
  H2("3.1 Components"),
  table(["Component", "Role", "Where it runs on Runpod"], [
    ["Model server", "vLLM with an OpenAI-compatible API, tool-call and reasoning parsers", "GPU pod, port 8000"],
    ["Agent harness", "The loop, tool registry, context control, approvals", "CPU pod, your own VM, or the GPU pod itself for a first test"],
    ["Tool layer", "Built-in file and shell tools, plus MCP servers for your systems", "With the harness"],
    ["Workspace", "The files and shell the agent may touch", "A disposable pod or VM that holds no secrets"],
    ["Skills store", "A folder of SKILL.md files", "With the harness (git or a volume)"],
    ["Pod manager", "Starts the GPU pod on demand and stops it when idle", "With the harness"],
    ["Chat UI", "HTMX page that streams progress and collects approvals", "With the harness"],
    ["Trace and evals", "One JSON line per model call and tool call; a fixed task set replayed on each change", "With the harness; keep traces on durable storage"],
  ], [0.2, 0.47, 0.33]),
  gap(),
  H2("3.2 Request flow"),
  ...numbered([
    "A task arrives at the harness, from the chat UI or the command line.",
    "The harness builds the messages: the rules, the one-line skills index, the task and, when one exists, the saved plan.",
    "It calls vLLM with the messages and the tool schemas, streaming the reply.",
    "The model returns text or tool calls.",
    "For each call the harness validates the arguments, checks approval, runs the tool, clips the output and appends the result.",
    "A `spawn_agent` call runs the same loop with a fresh message list and returns only the worker's report. Several in one turn run in parallel.",
    "When the prompt passes its token budget, older turns are folded into a summary.",
    "The loop ends on a plain-text answer or at the step cap. Every step is traced.",
  ]),
  ...figure("docs/img/fig_deploy.png", 600, 338, "Figure 2. Deployment on Runpod on-demand Pods"),
);

// ---------------------------------------------------------------- 4
add(
  H1("4. Model options"),
  H2("4.1 Comparison"),
  table(["", "Gemma 4 26B-A4B", "Gemma 4 31B", "Mistral Small 4", "DeepSeek V4-Flash"], [
    ["Licence", "Apache 2.0", "Apache 2.0", "Apache 2.0", "MIT"],
    ["Size", "26B MoE, 4B active", "31B dense", "119B MoE, 6.5B active", "284B MoE, 13B active"],
    ["Context", "Up to 256K", "Up to 256K", "256K", "1M"],
    ["Weights", "About 49 GB (BF16)", "About 62 GB (BF16)", "About 72 GB (NVFP4). FP8 is the native format; the recipe gives no size", "About 160 GB (FP8 preview)"],
    ["Function calling", "Native", "Native", "Native", "Supported"],
    ["vLLM parsers", "`gemma4` for tools and reasoning, plus the Gemma 4 tool chat template", "Same as 26B-A4B", "`mistral` for tools and reasoning", "`deepseek_v4` for tokenizer, tools and reasoning"],
    ["Minimum vLLM", "0.19.1", "0.19.1", "0.20.0", "0.25.0"],
    ["Hardware in the recipes", "1x A100 or H100 80 GB", "2x A100 or H100 (TP2); one 80 GB GPU is the listed minimum", "2x H200 or 2x B200 (FP8); 1x B200 with reduced context (NVFP4)", "8x H200 (default); 8x H100 reported; 4x B200 with NVFP4"],
    ["Plan for", "Parser bugs in early vLLM builds. Structured output does not see schema descriptions", "Same as 26B-A4B", "A required tool call is not guaranteed. `reasoning_effort` is only none or high. 256K can run out of memory on 2x H200", "Version-sensitive on H100 (0.26.0 works, 0.27.0 fails at start). Needs `--trust-remote-code`"],
  ], [0.14, 0.2, 0.19, 0.23, 0.24]),
  note("Sources: S10, S12 to S18, S21. MoE means mixture of experts: all weights sit in GPU memory, but only the active part is read per token."),
  H2("4.2 What the evidence says about tool-calling reliability"),
  ...bullets([
    "Model cards for all three families claim function calling. Small independent tests found a gap between that claim and dependable multi-turn tool use on the small Gemma 4 sizes: the E2B model scored 0 of 5 in one agent test, and a developer's E4B test landed mid-table. [S19] [S20]",
    "In the same June 2026 test, the community's usual local pick (Qwen3.6 35B) was judged usable but not dependable enough for unattended tool use, and frontier hosted models were ahead. [S19]",
    "In one DGX Spark benchmark, Gemma 4's 26B-A4B decoded about 6.4 times faster than the dense 31B. For an interactive loop that is a reason to start with the MoE model. [S18]",
    "Qwen3.6 35B-A3B is worth adding to a bake-off; the OpenHands local-model guide recommends it as the first model to try. [S23]",
  ]),
  P("The practical reading: budget for guardrails and evals, and choose the model from your own eval results."),
  H2("4.3 Splitting orchestrator and workers"),
  P("Nothing forces one model for everything. A stronger model can orchestrate while a cheaper one runs the worker agents, each behind its own endpoint. The costs add up, so try this only after the single-model pilot shows where the weak point is."),
);

// ---------------------------------------------------------------- 5
const priceRows = [
  ["B200", "180 GB", money(costs.rates["B200"]), "not listed", "Mistral Small 4 and DeepSeek V4-Flash in NVFP4"],
  ["H200", "141 GB", money(costs.rates["H200"]), money(costs.community_from["H200"]), "Gemma 4 31B, Mistral Small 4 FP8, DeepSeek V4-Flash FP8"],
  ["H100 SXM", "80 GB", money(costs.rates["H100 SXM"]), money(costs.community_from["H100 SXM"]), "Alternative to H100 PCIe"],
  ["H100 NVL", "94 GB", money(costs.rates["H100 NVL"]), "not listed", "More headroom for Gemma 4"],
  ["H100 PCIe", "80 GB", money(costs.rates["H100 PCIe"]), money(costs.community_from["H100 PCIe"]), "Gemma 4 starter pod; DeepSeek on 8 GPUs"],
  ["A100 SXM", "80 GB", money(costs.rates["A100 SXM"]), money(costs.community_from["A100 SXM"]), "Alternative to A100 PCIe"],
  ["A100 PCIe", "80 GB", money(costs.rates["A100 PCIe"]), money(costs.community_from["A100 PCIe"]), "Cheapest pod for Gemma 4 26B-A4B"],
  ["RTX PRO 6000", "96 GB", money(costs.rates["RTX PRO 6000"]), "not listed", "DeepSeek on 8 GPUs, verified without speculative decoding"],
  ["L40S", "48 GB", money(costs.rates["L40S"]), "not listed", "Small worker models such as Gemma 4 12B"],
  ["A40", "48 GB", money(costs.rates["A40"]), "not listed", "Small worker models"],
];
const basis = {
  A1: "In the vLLM recipe (1x A100 or H100)", A2: "In the vLLM recipe (1x A100 or H100)",
  B1: "Sized from the 62 GB weights; the recipe lists one 80 GB GPU as the minimum",
  B2: "In the vLLM recipe (TP2)", C1: "In the vLLM recipe; context may need cutting to 131K or 65K",
  C2: "In the vLLM recipe, with reduced context", C3: "In the vLLM recipe for the full 256K",
  D1: "vLLM recipe default (TP8 with expert parallel)", D2: "NVIDIA Dynamo recipe",
  D3: "Reported in the vLLM recipe; sensitive to the vLLM version",
};
add(
  H1("5. Infrastructure on Runpod on-demand Pods"),
  H2("5.1 Platform facts that shape the design"),
  table(["Topic", "What Runpod does", "What it means here"], [
    ["On-demand Pods", "Pay as you go. The GPU is dedicated to your pod and cannot be displaced by other users. Deploying needs at least one hour of credit. [S2]", "No pre-emption handling. Capacity is only yours while the pod exists."],
    ["Billing", "Compute and disks are billed per second. There are no data ingress or egress fees. [S2]", "Stopping an idle pod saves money at once."],
    ["Stop and terminate", "Stop releases the GPU and keeps the disk. At a zero balance pods stop, and a pod without a network volume is terminated and loses its data. [S2] [S7]", "Keep weights on a network volume. Turn on low-balance alerts."],
    ["Storage prices", "Container disk $0.10/GB/month, erased on stop. Volume disk $0.10 running and $0.20 stopped. Network volume $0.07/GB/month under 1 TB, $0.05 above. [S1] [S2]", "A 150 GB weights volume costs $10.50 a month."],
    ["Network volumes", "Mount at /workspace, must be attached when the pod is created, and live in one data centre, which limits the GPU types they can pair with. They cannot be encrypted. [S5]", "Create the volume where your GPU type is offered. Keep sensitive data off it."],
    ["HTTP proxy", "`https://[POD_ID]-[PORT].proxy.runpod.net`. The URL is public, and a connection with no traffic closes after 100 seconds. [S3]", "Authenticate the endpoint and always stream."],
    ["TCP ports", "A public IP with a mapped port. Traffic is not encrypted unless you add TLS. [S3]", "Use only with your own TLS."],
    ["Global networking", "Private `POD_ID.runpod.internal` names between pods in the account, at 100 Mbps, for NVIDIA GPU pods in supported Secure Cloud data centres. [S4]", "A CPU pod cannot join, so a harness on a CPU pod reaches vLLM through the proxy."],
    ["Containers", "A pod is one container. Docker and Compose cannot run inside a GPU pod, and current CPU pods do not support nested Docker. [S6]", "The agent's sandbox has to be a separate pod or VM."],
    ["Multi-GPU", "One pod generally scales to 8 GPUs. A tracker showed multi-GPU H200 and B200 on-demand capacity as limited in November 2026. [S9] [S22]", "Keep a fallback configuration for the larger tiers."],
    ["Spend limit", "A default limit of $80 an hour across all resources. [S2]", "The 8x H200 tier fits. Two large pods at once may not."],
  ], [0.15, 0.52, 0.33]),
  gap(),
  H2("5.2 On-demand GPU prices (27 November 2026)"),
  table(["GPU", "VRAM", "Secure Cloud, per hour", "Community Cloud, from", "Use in this design"], priceRows, [0.15, 0.1, 0.17, 0.17, 0.41]),
  note("Source: runpod.io/pricing [S1]. Community Cloud figures are the \"from\" prices in that page's FAQ. One tracker recorded B200 at $8.99 on 25 to 26 November [S22]; if that is the live rate, every B200 figure below is 12.5% higher."),
  H2("5.3 Pod configurations"),
  table(["ID", "Model and precision", "Pod", "VRAM", "Per hour", "Basis"],
    costs.configs.map((r) => [r.id, r.model + ", " + r.precision, r.count + "x " + r.gpu, r.vram_total + " GB", money(r.hourly), basis[r.id]]),
    [0.06, 0.24, 0.16, 0.1, 0.1, 0.34]),
  note("Secure Cloud on-demand rates. The DeepSeek recipe also mentions reports of 4x H100 working with lower memory utilisation; treat anything below the listed configurations as an experiment. [S14]"),
  H2("5.4 Monthly cost"),
  table(["ID", "Per hour", "GPU, 176 h", "GPU, 730 h", "Weights volume", "Month total, 176 h", "Month total, 730 h"],
    costs.configs.map((r) => [r.id, money(r.hourly), whole(r.work_month), whole(r.always_month), r.volume_gb + " GB = " + money(r.storage_month), whole(r.work_total), whole(r.always_total)]),
    [0.07, 0.11, 0.14, 0.14, 0.22, 0.16, 0.16]),
  note("176 h is 8 hours on 22 working days. 730 h is always on. Totals add the network volume at $0.07/GB/month. Not included: a harness host (a 4 vCPU, 8 GB CPU pod is about $86 a month always on [S22]) and container disk."),
  P("Unit cost follows from the hourly rate: cost per task = hourly rate x task minutes / 60 / sessions running at once. As an illustration only, a " + money(byId.A2.hourly) + " pod serving 6 sessions with 4-minute tasks works out at about $0.03 a task. Measure your own task length and concurrency before quoting a figure."),
  H2("5.5 Memory headroom check"),
  P("Weights have to fit with room left for the KV cache, which grows with context length and the number of sessions. The table is arithmetic from published weight sizes at vLLM's usual 0.90 memory setting. It is not a benchmark."),
  table(["Model", "Pod", "Usable at 0.90", "Weights", "Left for KV cache"],
    costs.headroom.filter((r) => !r.model.startsWith("DeepSeek")).map((r) => [r.model, r.gpu, r.usable_gb + " GB", r.weights_gb + " GB", r.headroom_gb + " GB"]),
    [0.3, 0.2, 0.17, 0.14, 0.19]),
  note("vLLM logs the cache size and the maximum concurrency at start-up; read that line before choosing `--max-model-len`. For Gemma 4 the recipe notes that `--kv-cache-dtype fp8` cuts KV memory by about half. [S12]"),
  H2("5.6 Reaching the model server"),
  table(["Pattern", "How", "Good for", "Watch out"], [
    ["Same pod", "The harness runs next to vLLM and calls `http://localhost:8000/v1`. No port is exposed.", "A first test", "The agent's shell shares a container with the model server and its secrets."],
    ["Runpod HTTPS proxy", "`https://POD_ID-8000.proxy.runpod.net/v1` with an API key, streaming every response.", "A pilot with non-sensitive data", "The URL is public. vLLM's API key covers only the /v1, /v2 and /inference paths, so other endpoints stay open. [S11]"],
    ["Private between GPU pods", "`http://POD_ID.runpod.internal:8000/v1` with global networking enabled.", "A harness that itself runs on a GPU pod", "GPU pods only, in supported Secure Cloud data centres."],
    ["Reverse proxy or tunnel", "vLLM bound to localhost behind an authenticating proxy in the same image, or reached through an SSH tunnel.", "Sensitive data", "Needs a custom image, or an image that runs an SSH daemon."],
  ], [0.17, 0.35, 0.18, 0.3]),
  gap(),
  H2("5.7 Pod template and serve commands"),
  table(["Setting", "Value"], [
    ["Container image", "`vllm/vllm-openai` with a pinned tag, not `latest`. Gemma 4 on H100 or H200: `gemma4-0505-cu129`. DeepSeek recipe image: `v0.28.0`. Mistral Small 4: a release at or above 0.20.0. [S8] [S12] [S13] [S14]"],
    ["Start command", "`vllm serve <model> <flags>`, as in Runpod's vLLM guides. If the pod log shows an argument error on first boot, the image's entrypoint already runs the server: remove the leading `vllm serve`. [S8]"],
    ["Environment", "`HF_TOKEN` for gated models. `HF_HOME=/workspace/hf` so the model cache sits on the volume. `VLLM_API_KEY` for the endpoint key. `VLLM_WORKER_MULTIPROC_METHOD=spawn` on multi-GPU pods. [S8] [S11]"],
    ["Storage", "Network volume mounted at /workspace, sized as in 5.4. Container disk 30 to 50 GB."],
    ["Ports", "Expose HTTP port 8000 only if you use the proxy pattern. The server must bind to `0.0.0.0`. [S8]"],
    ["Cloud", "Secure Cloud, with global networking switched on if other GPU pods need private access."],
  ], [0.2, 0.8]),
  gap(),
  H3("Gemma 4 26B-A4B on one 80 GB GPU (A1, A2)"),
  ...code([
    "vllm serve google/gemma-4-26B-A4B-it \\",
    "  --host 0.0.0.0 --port 8000 --served-model-name agent-model \\",
    "  --max-model-len 32768 --gpu-memory-utilization 0.90 \\",
    "  --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \\",
    "  --chat-template examples/tool_chat_template_gemma4.jinja",
  ]),
  P("For the 31B model on one H200 (B1) change the model to `google/gemma-4-31B-it`. On two H100s (B2) also add `--tensor-parallel-size 2`. The chat template ships in the vLLM repository's examples folder; if the image does not contain it, download it to the volume and pass the full path. [S12]"),
  H3("Mistral Small 4 on two H200s (C1)"),
  ...code([
    "vllm serve mistralai/Mistral-Small-4-119B-2603 \\",
    "  --host 0.0.0.0 --port 8000 --served-model-name agent-model \\",
    "  --max-model-len 131072 --tensor-parallel-size 2 \\",
    "  --enable-auto-tool-choice --tool-call-parser mistral --reasoning-parser mistral",
  ]),
  P("The recipe's own command uses 262144. Start at 131072, because the recipe warns that the full context can run out of memory on two H200s. It also asks for `mistral_common` 1.11.0 or later. [S13]"),
  H3("DeepSeek V4-Flash on eight H200s (D1)"),
  ...code([
    "export VLLM_USE_RUST_FRONTEND=1",
    "vllm serve deepseek-ai/DeepSeek-V4-Flash-0731 \\",
    "  --host 0.0.0.0 --port 8000 --served-model-name agent-model \\",
    "  --trust-remote-code --kv-cache-dtype fp8 --block-size 256 \\",
    "  --enable-expert-parallel --tensor-parallel-size 8 \\",
    "  --tokenizer-mode deepseek_v4 --tool-call-parser deepseek_v4 \\",
    "  --enable-auto-tool-choice --reasoning-parser deepseek_v4 \\",
    "  --reasoning-config '{\"reasoning_parser\":\"deepseek_v4\",\"reasoning_start_str\":\"\",\"reasoning_end_str\":\"\"}' \\",
    "  --speculative-config '{\"method\":\"dspark\",\"num_speculative_tokens\":7,\"draft_sample_method\":\"probabilistic\"}'",
  ]),
  P("`--trust-remote-code` runs code from the model repository, so pin the revision and review it first. [S14]"),
  H3("Smoke tests"),
  ...code([
    "curl https://<POD_ID>-8000.proxy.runpod.net/health",
    "curl https://<POD_ID>-8000.proxy.runpod.net/v1/models -H \"Authorization: Bearer $KEY\"",
    "LLM_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1 LLM_API_KEY=$KEY \\",
    "    python harness/smoke_test.py",
  ]),
  P("The third command sends one request with a strict tool schema and fails unless the reply contains a parsed tool call whose arguments match the schema. Run it after every image or model change. A tool call that arrives as plain text means the parser or chat template is wrong for that model."),
  H2("5.8 Operating on-demand pods"),
  ...bullets([
    "**Treat pods as disposable.** Everything durable sits on the network volume, so a pod can be terminated and redeployed from the template on any free GPU in that data centre.",
    "**Stop when idle.** `runpodctl pod stop POD_ID` and `runpodctl pod start POD_ID`, or `POST https://rest.runpod.io/v1/pods/{podId}/stop` with a bearer token. The pod manager in section 7 does this automatically. [S7]",
    "**Expect a cold start.** A started pod has to boot the container and load the weights from the volume before `/health` answers. Measure it for your model and show it in the UI.",
    "**Have a capacity fallback.** If the first-choice GPU is not available, step along a list you decided in advance, for example A100 PCIe, H100 PCIe, H100 NVL, H200.",
    "**Guard the budget.** Keep the spend limit, switch on low-balance notifications, and re-check prices monthly.",
    "**Pin versions.** Record the vLLM image tag and model revision with every eval run.",
  ]),
);

// ---------------------------------------------------------------- 6
add(
  H1("6. Implementation guide"),
  P("The listings below are cut directly from `harness/mini_harness.py` in the companion repository, the file the tests ran against. Build in this order; each step is useful on its own."),
  H2("6.1 Call the model"),
  P("One streamed completion per step. Streaming keeps bytes flowing, which the Runpod proxy needs, and tool calls arrive in fragments that have to be reassembled by index. The prompt token count from the final chunk drives compaction later."),
  ...code(ex.call_model),
  table(["Model", "Sampling and reasoning settings from the recipes", "How to set them"], [
    ["Mistral Small 4", "`reasoning_effort` accepts only none or high. Temperature 0.0 to 0.7 without reasoning, 0.7 with it. [S13]", "`LLM_TEMPERATURE`, and `LLM_EXTRA_BODY='{\"reasoning_effort\": \"high\"}'`"],
    ["DeepSeek V4-Flash", "Temperature 1.0, with top-p 0.95 for agentic work on the 0731 release. Thinking is switched through `chat_template_kwargs`. [S14]", "`LLM_TEMPERATURE=1.0`, and `LLM_EXTRA_BODY` for top-p and the thinking switch"],
    ["Gemma 4", "The recipe gives no sampling values. Start from the harness default of 0.2 and tune on your evals.", "`LLM_TEMPERATURE`"],
  ], [0.18, 0.47, 0.35]),
  gap(),
  H2("6.2 The loop"),
  P("This is the whole agent. A reply without tool calls ends the run. Calls run one by one unless every tool in the turn is marked safe to run in parallel, because a model often emits a write and then an edit that depends on it. The plan and checkpoint lines are explained in 6.9."),
  ...code(ex.run_agent),
  H2("6.3 Tools"),
  P("A tool is a name, a description, a JSON schema and a Python function. The description is the routing logic, so it gets the most care."),
  ...code(ex.registry),
  ...code(ex.edit_file),
  ...bullets([
    "Say what the tool does, when to use it and when not to. Name the alternative tool where there is one.",
    "Describe every argument. Use the strict schema style: every field required, `additionalProperties` false, optional fields expressed as nullable. For tools marked strict, vLLM constrains the arguments to the schema where the model's parser supports it. [S10]",
    "Start with five to eight tools. Each extra tool costs context and makes a wrong pick more likely.",
    "Return failures as text that tells the model what to fix.",
  ]),
  H2("6.4 Running a tool call"),
  P("Open models make more mistakes here than anywhere else, so every failure path feeds a usable message back into the loop."),
  ...code(ex.execute),
  table(["What went wrong", "What the model gets back"], [
    ["Unknown tool name", "The error and the list of real tool names"],
    ["Arguments are not valid JSON", "The parser error and a request to send the call again"],
    ["The same call for the third time", "A refusal and an instruction to change approach or answer"],
    ["Action not approved", "DENIED, and an instruction to continue without it"],
    ["Wrong or missing fields", "The expected field names"],
    ["The tool raised an exception", "The exception type and message"],
  ], [0.4, 0.6]),
  gap(),
  H2("6.5 Subagents"),
  P("A subagent is the same loop behind one tool. It gets a fresh message list, a smaller tool set without the spawn tool (so no nesting), and returns only its final report. Several spawn calls in one turn run side by side in a thread pool."),
  ...code(ex.subagents),
  H2("6.6 The operating instructions"),
  P("The rules for splitting work, delegating and stopping are plain language in the system prompt. This is where the behaviour described in section 2.2 is set."),
  ...code(ex.orchestrator),
  H2("6.7 Skills"),
  P("A skill is a folder with a SKILL.md file. The prompt carries one line per skill; the body is loaded only when the model asks for it."),
  ...code(ex.skills),
  ...code([
    "---",
    "name: report-style",
    "description: House style for written reports; load before drafting any report.",
    "---",
    "",
    "Use short sentences. End with a list of open items.",
  ]),
  H2("6.8 Context control"),
  P("When the prompt passes its token budget, older turns are replaced by a summary the model writes for itself. The summary is folded into the first user message, so the roles still alternate for chat templates that insist on it, and a tool result is never separated from its call."),
  ...code(ex.context),
  ...bullets([
    "Set `AGENT_CONTEXT_BUDGET` to roughly 60% of the server's `--max-model-len`.",
    "Tool output is clipped to 6,000 characters before it enters the context. Have tools write large results to a file and return the path.",
    "Keep the system prompt and tool list stable between turns so the server can reuse its prefix cache.",
  ]),
  H2("6.9 Long tasks: plan, checkpoints and budgets"),
  P("Three small additions make the loop usable for work that runs for hours. The plan is a file the model rewrites through one tool, and the harness reads it back into the first user message on every turn. A checkpoint is written after each finished step. A run that hit the step cap, crashed or lost its GPU continues with `resume=True`."),
  ...code(ex.longtask),
  ...bullets([
    "The plan lives outside the message list, so compaction cannot lose it. A new task starts without the previous task's plan.",
    "Checkpoints are written with an atomic rename, so a crash in mid-write leaves the previous checkpoint intact.",
    "Only the orchestrator plans and checkpoints. Workers are short-lived by design: if one fails, the orchestrator receives an error report and decides again.",
    "On-demand pods are why resume matters. When the idle watchdog or a capacity problem stops the GPU, the task continues from its last step once the pod is back.",
    "The step cap applies to each agent. For production add wall-clock and spend limits, and make the stop message say what is left.",
  ]),
  H2("6.10 Guardrails"),
  P("File tools are confined to the workspace. Shell commands run without approval only when they are a single allow-listed read-only command with no shell operators and no path that leaves the workspace. Everything else waits for a person. The shell gets a stripped environment."),
  ...code(ex.guard),
  P("This is a permission layer, not a sandbox. Runpod pods cannot run nested containers, so put the workspace on a separate disposable pod or VM that holds no credentials."),
  H2("6.11 MCP servers"),
  P("`harness/mcp_bridge.py` registers every tool of an MCP server as a harness tool. It targets version 2 of the Python SDK, whose client API differs from version 1."),
  ...code([
    "from mcp import StdioServerParameters",
    "import mcp_bridge",
    "",
    "names = mcp_bridge.connect(\"tickets\", \"https://mcp.example.internal/mcp\")",
    "names += mcp_bridge.connect(\"files\", StdioServerParameters(",
    "    command=\"python\", args=[\"fs_server.py\"]))",
    "answer = run_agent(task, orchestrator_system(), ORCHESTRATOR_TOOLS + names)",
  ]),
  ...bullets([
    "Tool names are prefixed with the server name, so two servers cannot clash.",
    "Third-party schemas are rarely in strict style, so these tools are registered without the strict flag.",
    "Give each agent only the MCP tools its job needs.",
  ]),
  H2("6.12 Tracing and evals"),
  P("Every model call and tool call appends one JSON line with the run id. The same events drive the live status in the chat UI and the eval metrics."),
  ...code(ex.trace),
  P("The eval runner replays a task file and scores each run from the workspace and the trace. The last argument is the number of repeats."),
  ...code([
    "AGENT_WORKSPACE=/tmp/eval-workspace python harness/run_evals.py evals/tasks.jsonl 3",
  ]),
  table(["Metric", "Meaning", "Use"], [
    ["pass_rate", "Share of runs whose check command succeeded", "The headline number; compare with the previous run"],
    ["avg_steps", "Model calls per run", "Rising steps for the same pass rate means wasted work"],
    ["tool_failure_rate", "Tool calls that came back as ERROR or DENIED", "Tracks schema and description problems"],
    ["step_limit_rate", "Runs stopped by the step cap", "Tracks loops and tasks that are too big"],
  ], [0.22, 0.4, 0.38]),
  note("Each eval case is a task, optional starting files and a shell check that runs in the workspace with the final answer on standard input. Start with 20 to 30 real tasks and run each several times, because the same model does not behave identically twice."),
);

// ---------------------------------------------------------------- 7
add(
  pageBreak(), H1("7. End-to-end flow: chat UI to on-demand GPU"),
  P("The repository includes a working example of the full path: an HTMX chat page, a FastAPI backend, the harness, and a pod manager that starts the Runpod pod when work arrives and stops it when idle."),
  H2("7.1 What happens, step by step"),
  table(["#", "Who acts", "What happens", "What the user sees"], [
    ["1", "Browser (HTMX)", "The form posts the task to `/chat`.", "Their message appears"],
    ["2", "Backend (FastAPI)", "Creates a run, starts a worker thread and returns two chat bubbles. The second opens a server-sent event stream.", "Queued"],
    ["3", "Pod manager", "Checks `/health`. If the model server is down, calls Runpod's start endpoint and polls until it is healthy.", "Starting the GPU pod, then Model server is ready"],
    ["4", "Harness loop", "The model picks tools, the harness runs them, the model reads the results and decides the next step.", "The agent's checklist on longer tasks, and a status line such as Agent step 3: read_file"],
    ["5", "Approval gate", "An action outside the read-only allow-list pauses the run.", "Approve and Deny buttons in the chat"],
    ["6", "Harness", "The model answers in plain text. The trace is complete.", "The answer replaces the status line"],
    ["7", "Idle watchdog", "No runs for the idle period: calls Runpod's stop endpoint.", "Nothing. The next request cold-starts"],
  ], [0.05, 0.17, 0.5, 0.28]),
  ...figure("docs/img/ui-flow.png", 500, 299, "Figure 3. The reference chat UI in headless Chrome against the mock endpoints: GPU start and a plan checklist (left), approval prompt (right)"),
  H2("7.2 Who decides what"),
  table(["Decision", "Decided by", "Why"], [
    ["Start or stop the GPU", "Code (pod manager)", "The model runs on that GPU, so it cannot decide its own start. A rule or a small always-on model can route chit-chat away from the GPU."],
    ["Which tool, how many steps, whether to delegate", "The model", "This is the loop"],
    ["Whether a risky action runs", "A person, through the approval gate", "The model proposes; it does not approve itself"],
    ["Whether a result is good enough to report", "The model in the loop, checked later by evals", "In-loop checks catch slips; evals measure the rate"],
    ["Whether a change ships", "Eval metrics", "Compared against the previous run"],
  ], [0.3, 0.26, 0.44]),
  gap(),
  H2("7.3 The pod manager"),
  ...code(ex.pod),
  ...bullets([
    "Concurrent requests share one start: the lock means the second request waits for the first one's start and then finds the server healthy.",
    "Readiness is judged by the model server's own `/health`, not by Runpod's pod status, because a running pod may still be loading weights.",
    "If the pod does not become healthy in time, the run fails with a message that names capacity and the pod log as the things to check.",
    "The idle timeout is the cost dial. A long timeout keeps the model warm for the next user; a short one saves money and causes more cold starts.",
  ]),
  H2("7.4 The chat endpoint"),
  ...code(ex.chat),
  ...bullets([
    "The page uses htmx 2.0.10 and its SSE extension 2.2.4, served from the app's own static folder. The agent bubble connects with `sse-connect`, each part listens with `sse-swap`, and `sse-close` ends the stream on the done event.",
    "Browsers drop server-sent events whose data is empty, so the server clears a region by sending a placeholder element.",
    "The stream sends a comment line every 15 seconds while idle, so a proxy with an idle limit does not close it.",
    "All user and model text is escaped before it reaches the page. Model output is untrusted HTML.",
    "The example has no login and one shared workspace. Put it behind your own authentication, and give each session its own sandbox, before real users touch it.",
    "htmx 4 renames the SSE attributes (`hx-sse:connect`, `hx-sse:close`), so the markup needs adjusting if you move to it.",
  ]),
);

// ---------------------------------------------------------------- 8
add(
  H1("8. Reliability playbook for open models"),
  table(["Symptom", "Likely cause", "Fix in the server", "Fix in the harness"], [
    ["Malformed or schema-breaking arguments", "Free generation under automatic tool choice", "Mark tools strict so arguments are constrained [S10]", "Feed the JSON error back; the model retries"],
    ["Tool call arrives as text, or raw tokens leak", "Wrong or outdated parser or chat template", "Pin a vLLM build that has the model's parser; run the smoke test [S21]", "None; this is a serving fault"],
    ["Picks the wrong tool", "Too many similar tools; vague descriptions", "None", "Fewer tools, sharper descriptions, a smaller tool set per agent"],
    ["Stops early or asks needless questions", "Weak instruction following", "None", "Prompt rules; workers told they cannot ask; a check step before the final answer"],
    ["Repeats the same call", "The model is stuck", "None", "Repeat detection on the third identical call; step cap"],
    ["Runs out of context", "Long tool outputs and long sessions", "A lower `--max-model-len` that fits memory; FP8 KV cache", "Clip outputs; compact; give heavy reading to subagents"],
    ["No tool call when one is required (Mistral)", "Known behaviour of the official tokenizer format under required or named choice [S10]", "Use automatic tool choice", "Detect the missing call and prompt again"],
    ["Loses the thread on a long task", "Early turns were summarised away and no plan was kept", "None", "Pinned plan; checkpoints; subagents for heavy reading"],
    ["Client timeouts through the proxy", "100-second idle limit", "None", "Stream every response"],
    ["Slow multi-step runs", "Dense-model decode speed; long prompts", "An MoE model; a stable prompt prefix for cache reuse", "Parallel subagents; a smaller worker model"],
  ], [0.2, 0.22, 0.29, 0.29]),
  gap(),
);

// ---------------------------------------------------------------- 9
add(
  H1("9. Security and governance"),
  table(["Area", "Control"], [
    ["Endpoint", "Set an API key. Remember that vLLM's key protects only the /v1, /v2 and /inference paths; other endpoints such as /invocations stay open, and vLLM's own documentation says not to rely on the key alone. For anything sensitive, do not expose port 8000: use private networking, a tunnel or an authenticating reverse proxy. [S3] [S11]"],
    ["Data location", "Use Secure Cloud for client data and choose the data centre for residency. Network volumes and container disks cannot be encrypted, so keep sensitive data off them or encrypt it in the application. [S5]"],
    ["Model supply chain", "Pin model revisions. Use `--trust-remote-code` only for repositories you have reviewed."],
    ["Agent actions", "Approval for anything that is not read-only; workspace confinement; no credentials in the agent's environment; a separate sandbox pod or VM."],
    ["Prompt injection", "Treat tool, web and MCP output as data. Never let it trigger a privileged tool without approval."],
    ["Chat UI", "Add authentication. Escape all model output. Give each session its own workspace."],
    ["Audit", "Keep the trace with the run id for every model call and tool call, alongside the eval reports."],
    ["Cost", "Spend limit, low-balance alerts, idle shutdown."],
    ["Licences", "Apache 2.0 for Gemma 4 and Mistral Small 4, MIT for DeepSeek V4-Flash. Read each model card for conditions of use. [S15] [S16] [S17]"],
  ], [0.2, 0.8]),
  gap(),
);

// ---------------------------------------------------------------- 10
add(
  H1("10. Delivery plan"),
  P("Durations are indicative, for one engineer who knows Python and has not used Runpod before."),
  table(["Phase", "Duration", "Work", "Exit check"], [
    ["0. Foundation", "1 to 2 days", "Runpod account and API key, network volume, pod template, starter pod A1 or A2", "`/health` answers; the smoke test returns a parsed tool call"],
    ["1. Core loop", "3 to 4 days", "Harness with the built-in tools, approvals and trace; a 20-task eval set", "Baseline eval numbers recorded"],
    ["2. Capabilities", "1 week", "Skills, subagents, MCP servers for your systems, the chat UI and pod manager", "Evals cover each new capability"],
    ["3. Hardening and bake-off", "1 week", "Work through the reliability playbook; run the eval set on Gemma 4 31B and Mistral Small 4, and on DeepSeek V4-Flash for a day", "A model chosen from eval data and cost"],
    ["4. Pilot", "1 to 2 weeks", "Real users; idle shutdown tuned; a review of cost and failures; decide which workflows move into explicit code", "Go or no-go"],
  ], [0.2, 0.13, 0.4, 0.27]),
  gap(),
);

// ---------------------------------------------------------------- 11
add(
  H1("11. Risks and open decisions"),
  table(["Risk", "Effect", "Mitigation"], [
    ["Multi-GPU on-demand capacity is limited", "The larger tiers may not start when needed", "Fallback configurations; start on a smaller tier; look at Runpod Clusters or reserved capacity if demand is steady"],
    ["Prices move", "Budget drift", "Re-check the console monthly; the cost script in the repository recalculates the tables"],
    ["Parser regressions between vLLM releases", "Tool calls break after an upgrade", "Pin tags; run the smoke test and evals before upgrading"],
    ["Open models trail frontier hosted models on agent work", "Lower task completion", "Guardrails and evals; optionally a hosted model as orchestrator"],
    ["No nested containers on Runpod", "Weaker isolation for agent actions", "Sandbox pod or VM; least-privilege tools"],
    ["Unencrypted network volumes", "Exposure of data at rest", "Keep sensitive data off the volume, or encrypt in the application"],
    ["Cold starts", "Minutes of waiting after an idle period", "Show progress; tune the idle timeout; keep the pod up during working hours"],
  ], [0.3, 0.27, 0.43]),
  gap(),
  P("**Open decisions:** which model tier to pilot; Secure or Community Cloud; where the harness runs; the sandbox approach; the tracing stack; the idle timeout; which workflows to hard-code."),
);

// ---------------------------------------------------------------- appendix A
add(
  H1("Appendix A: repository map and test coverage"),
  table(["Path", "What it holds"], [
    ["`harness/mini_harness.py`", "The loop, tools, subagents, skills, plan, checkpoints, compaction, trace"],
    ["`harness/mcp_bridge.py`", "MCP servers as harness tools (mcp SDK 2.x)"],
    ["`harness/pod_manager.py`", "Start the Runpod pod on demand; stop it when idle"],
    ["`harness/run_evals.py`", "Eval runner and metrics"],
    ["`harness/smoke_test.py`", "One-request check that an endpoint returns parsed tool calls"],
    ["`app/server.py`, `app/static/`", "HTMX chat UI on FastAPI; htmx 2.0.10 and its SSE extension 2.2.4"],
    ["`infra/runpod.md`, `infra/costs.py`", "Pod template settings, serve commands and the cost arithmetic"],
    ["`skills/`, `evals/`", "An example skill and example eval tasks"],
    ["`tests/`", "Mock model endpoint, mock Runpod API and four test scripts"],
  ], [0.36, 0.64]),
  gap(),
  table(["Test script", "Checks", "What it proves"], [
    ["`tests/test_harness.py`", "27", "Tool loop; recovery from bad JSON and unknown tools; repeat detection; parallel subagents with fresh context and no nesting; compaction; step cap; pinned plan; checkpoint and resume; approvals; workspace confinement; skills; ordered execution; MCP bridge; streaming; smoke test; API key"],
    ["`tests/test_evals.py`", "1", "Eval runner scoring and metrics on four cases"],
    ["`tests/test_app.py`", "18", "One pod start for concurrent requests; status stream; approvals; escaping; replay for a reconnecting browser; idle stop and restart; start-timeout error"],
    ["`tests/test_ui_browser.py`", "10", "Headless Chrome: HTMX wiring, live updates, approval buttons, plan checklist, no JavaScript errors"],
  ], [0.28, 0.1, 0.62]),
  note("Tested with Python 3.13, openai 3.60.0, mcp 2.3.0, fastapi 0.165.0 and uvicorn 0.54.0. Every check ran against mock endpoints. None ran against a live GPU or the real Runpod API."),
);

// ---------------------------------------------------------------- appendix B
const sources = [
  ["S1", "Runpod pricing page (read 27 November 2026)", ["https://www.runpod.io/pricing"]],
  ["S2", "Runpod docs: Pod pricing", ["https://docs.runpod.io/pods/pricing"]],
  ["S3", "Runpod docs: Expose ports", ["https://docs.runpod.io/pods/configuration/expose-ports"]],
  ["S4", "Runpod docs: Global networking", ["https://docs.runpod.io/pods/networking"]],
  ["S5", "Runpod docs: Storage types; Network volumes", ["https://docs.runpod.io/pods/storage/types.md", "https://docs.runpod.io/storage/network-volumes"]],
  ["S6", "Runpod docs and blog: Pod limitations and Docker", ["https://docs.runpod.io/docs/pods", "https://docs.runpod.io/tutorials/pods/build-docker-images", "https://www.runpod.io/blog/enhanced-cpu-pods-docker-network"]],
  ["S7", "Runpod docs: Manage Pods; REST API stop", ["https://docs.runpod.io/pods/manage-pods.md", "https://docs.runpod.io/api-reference/pods/POST/pods/podId/stop.md"]],
  ["S8", "Runpod guides: Deploy vLLM on Runpod", ["https://www.runpod.io/articles/guides/deploy-vllm-runpod-llm-inference", "https://www.runpod.io/articles/guides/deploy-vllm-runpod-docker"]],
  ["S9", "Runpod blog: Clusters announcement (8 GPUs per pod)", ["https://www.runpod.io/blog/bare-metal-vs-instant-clusters-whats-best-for-your-ai-workload"]],
  ["S10", "vLLM docs: Tool calling", ["https://docs.vllm.ai/en/stable/features/tool_calling/"]],
  ["S11", "vLLM docs: Security and API key limits", ["https://docs.vllm.ai/en/latest/usage/security/?h=api+key", "https://docs.vllm.ai/en/v0.30.0/serving/online_serving/openai_compatible_server/"]],
  ["S12", "vLLM recipes: Gemma 4", ["https://recipes.vllm.ai/Google/gemma-4-31B-it", "https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html"]],
  ["S13", "vLLM recipe: Mistral Small 4", ["https://recipes.vllm.ai/mistralai/Mistral-Small-4-119B-2603"]],
  ["S14", "vLLM recipe and NVIDIA Dynamo recipe: DeepSeek V4-Flash", ["https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Flash", "https://docs.dynamo.nvidia.com/dynamo/recipes/deepseek-v4-flash"]],
  ["S15", "Google: Gemma 4 announcement and model card", ["https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/", "https://ai.google.dev/gemma/docs/core/model_card_4"]],
  ["S16", "Mistral: Mistral Small 4", ["https://docs.mistral.ai/models/mistral-small-4-0-26-03.md", "https://mistral.ai/news/mistral-small-4/"]],
  ["S17", "DeepSeek V4: release coverage and model listing", ["https://rits.shanghai.nyu.edu/ai/deepseek-releases-v4-open-source-1-6t-moe-with-1m-context", "https://venturebeat.com/technology/deepseek-v4-arrives-with-near-state-of-the-art-intelligence-at-1-6th-the-cost-of-opus-4-7-gpt-5-5", "https://openrouter.ai/models/deepseek/deepseek-v4-flash-20260731"]],
  ["S18", "NVIDIA developer forum: Gemma 4 on DGX Spark, preliminary benchmarks", ["https://forums.developer.nvidia.com/t/gemma-4-day-1-inference-on-nvidia-dgx-spark-preliminary-benchmarks/365503"]],
  ["S19", "S. Raschka: Using Local Coding Agents; Components of a Coding Agent", ["https://magazine.sebastianraschka.com/p/using-local-coding-agents", "https://magazine.sebastianraschka.com/p/components-of-a-coding-agent"]],
  ["S20", "Developer test of Gemma 4 E4B function calling", ["https://dev.to/vystartasv/google-said-it-had-native-function-calling-i-tested-it-54i7"]],
  ["S21", "vLLM GitHub: Gemma 4 parser fix and issue", ["https://github.com/vllm-project/vllm/pull/38847", "https://github.com/vllm-project/vllm/issues/44522"]],
  ["S22", "Price and availability trackers", ["https://gpueconomy.com/providers/runpod", "https://gpufinder.dev/providers/runpod", "https://getdeploying.com/runpod"]],
  ["S23", "MarkTechPost: open-source agent harnesses for local LLMs", ["https://www.marktechpost.com/2026/09/18/best-open-source-agent-harnesses-for-local-llms-in-2026/"]],
  ["S24", "htmx: Server Sent Event extension", ["https://htmx.org/extensions/sse"]],
];
add(H1("Appendix B: sources"), P("Web sources were read on 27 November 2026.", { run: { color: GREY, size: SMALL } }));
for (const [id, title, urls] of sources) {
  add(new Paragraph({ spacing: { after: 20 }, keepNext: true, children: [new TextRun({ text: id + "  " + title, size: SMALL, bold: true })] }));
  urls.forEach((u, i) => add(new Paragraph({ indent: { left: 400 }, spacing: { after: i === urls.length - 1 ? 90 : 10 }, children: [link(u, u)] })));
}

// ================================================================ document
const heading = (size, before, after) => ({
  run: { font: FONT, size, bold: true, color: NAVY },
  paragraph: { spacing: { before, after }, keepNext: true },
});
const doc = new Document({
  creator: "Claude", title: "Building a Claude-style agent harness on open-weight models",
  description: "Design, implementation and Runpod on-demand infrastructure",
  styles: {
    default: {
      document: { run: { font: FONT, size: BODY }, paragraph: { spacing: { line: 276, lineRule: LineRuleType.AUTO } } },
      heading1: heading(32, 400, 160), heading2: heading(25, 260, 110), heading3: heading(21, 200, 80),
    },
    paragraphStyles: [
      { id: "Furniture", name: "Furniture", basedOn: "Normal", run: { font: FONT, size: 16, color: GREY } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 250 } } } }] },
      ...numberRefs.map((reference) => ({ reference, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 320 } } } }] })),
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1300, right: 1440, bottom: 1250, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ style: "Furniture", alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Agent harness on open-weight models: design and Runpod infrastructure", size: 16, color: GREY })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ style: "Furniture", alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: "Page ", size: 16, color: GREY }),
      new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
      new TextRun({ text: " of ", size: 16, color: GREY }),
      new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY }),
    ] })] }) },
    children: c,
  }],
});

const out = "docs/agent-harness-open-models-runpod.docx";
fs.mkdirSync("docs", { recursive: true });
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log("wrote", out, buffer.length, "bytes;", c.length, "blocks");
});
