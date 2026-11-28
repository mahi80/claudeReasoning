from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "app"))
import mock_integrations
import mock_llm


class Fixture:
    def __init__(self, origin="http://127.0.0.1:8085"):
        self.temp = tempfile.TemporaryDirectory(prefix="coding-ui-fixture-")
        self.state = Path(self.temp.name)
        self.workspace = self.state / "workspace"
        self.workspace.mkdir()
        self.model, llm_port = mock_llm.start()
        self.provider, provider_port = mock_integrations.start()
        config = self.state / "checks.json"
        config.write_text(json.dumps({"checks": {"tests": {"argv": [sys.executable, "-I", "-c",
            "import runpy; m=runpy.run_path('app.py'); assert m['add'](2, 3)==5"], "timeout": 10}}, "gate": ["tests"]}))
        integrations = self.state / "integrations.json"
        integrations.write_text(json.dumps(mock_integrations.configuration(provider_port)))
        self.token = "local-chat-fixture-alice-" + "a" * 32
        self.other_token = "local-chat-fixture-bob-" + "b" * 32
        self.headers = {"Authorization": "Bearer " + self.token}
        self.auth_config = self.state / "access.json"
        self.auth_config.write_text(json.dumps({"tenant": "fixture-team", "origin": origin,
            "users": {"alice": {"token_env": "FIXTURE_CHAT_ALICE"}, "bob": {"token_env": "FIXTURE_CHAT_BOB"}}}))
        os.environ.update(AGENT_CHAT_AUTH_CONFIG=str(self.auth_config), FIXTURE_CHAT_ALICE=self.token,
                          FIXTURE_CHAT_BOB=self.other_token, LLM_BASE_URL=f"http://127.0.0.1:{llm_port}/v1", LLM_API_KEY="test-key", LLM_MODEL="mock",
                          AGENT_WORKSPACE=str(self.workspace), AGENT_SKILLS=str(ROOT / "skills"),
                          AGENT_TRACE=str(self.state / "trace.jsonl"), AGENT_CHECKPOINTS=str(self.state / "checkpoints"),
                          AGENT_DELIVERY_CONFIG=str(config), AGENT_INTEGRATIONS_CONFIG=str(integrations),
                          AGENT_MCP_CONFIG="", RUNPOD_POD_ID="", AGENT_AUTO_APPROVE="0",
                          FIXTURE_CONNECTOR_TOKEN="fixture-token", NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
        import server
        self.server = server

    def close(self):
        self.model.shutdown()
        self.provider.shutdown()
        self.server.h.client.close()
        self.temp.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8085)
    args = parser.parse_args()
    fixture = Fixture(f"http://127.0.0.1:{args.port}")
    print(f"Fixture workspace: {fixture.workspace}", flush=True)
    print(f"Local fixture sign-in token: {fixture.token}", flush=True)
    import uvicorn
    try:
        uvicorn.run(fixture.server.app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        fixture.close()
