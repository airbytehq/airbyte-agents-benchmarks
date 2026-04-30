from __future__ import annotations

import asyncio
import json

import pytest

from agent_bench.config import LiveConfig
from agent_bench.export.scorecard import render_scorecard
from agent_bench.metrics import BenchmarkResult, StepResult
from agent_bench.paths.agent_mcp import AgentMCPPath
from agent_bench.paths.agent_sdk import _DISPATCH, _translate
from agent_bench.paths.native_mcp import NativeMCPPath
from agent_bench.recordings import validate_recordings
from agent_bench.runner import Cell, RunReport
from agent_bench.scenarios.loader import Task, load_scenario


def test_scenario_loads_choreographed_format() -> None:
    gong_get = load_scenario("gong-get")
    assert gong_get.is_choreographed
    assert gong_get.paths is not None
    assert "agent-mcp" in gong_get.paths
    assert "native-mcp" in gong_get.paths

    agent_calls = gong_get.paths["agent-mcp"].tool_calls
    assert len(agent_calls) == 1
    assert agent_calls[0].server == "airbyte-agent"
    assert agent_calls[0].tool == "integrations_connectors_id_execute"
    assert agent_calls[0].args["entity"] == "calls"
    assert agent_calls[0].args["action"] == "get"
    assert agent_calls[0].args["params"]["id"] == "1005803797056190704"
    assert "id" in agent_calls[0].args["select_fields"]

    native_calls = gong_get.paths["native-mcp"].tool_calls
    assert len(native_calls) == 1
    assert native_calls[0].server == "gong"
    assert native_calls[0].tool == "get_call"


def test_multi_step_scenario_loads() -> None:
    scenario = load_scenario("gong-to-salesforce-zendesk-lookup")
    assert scenario.is_choreographed
    assert scenario.faux_prompt
    assert len(scenario.paths["agent-mcp"].tool_calls) == 3
    assert len(scenario.paths["native-mcp"].tool_calls) == 3

    agent_calls = scenario.paths["agent-mcp"].tool_calls
    assert agent_calls[0].connector_id_env == "GONG_CONNECTOR_ID"
    assert agent_calls[1].connector_id_env == "SALESFORCE_CONNECTOR_ID"
    assert agent_calls[2].connector_id_env == "ZENDESK_CONNECTOR_ID"


def test_scenario_connectors_property() -> None:
    scenario = load_scenario("gong-to-salesforce-zendesk-lookup")
    connectors = scenario.connectors
    assert "gong" in connectors
    assert "salesforce" in connectors
    assert "zendesk" in connectors


def test_not_comparable_scenarios() -> None:
    slack_get = load_scenario("slack-get")
    assert slack_get.is_comparable is False

    slack_search = load_scenario("slack-search")
    assert slack_search.is_comparable is False

    sf_search = load_scenario("salesforce-search")
    assert sf_search.is_comparable is False


def test_agent_mcp_recording_parses_execution_metadata_latency(tmp_path) -> None:
    scenario = load_scenario("linear-get")
    rec_dir = tmp_path
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "recording.json").write_text(json.dumps([{
        "tool": "mcp__airbyte-agent__execute",
        "args": {"items": [{
            "connector_id": "linear-id",
            "entity": "issues",
            "action": "get",
            "params": {"id": "issue-1"},
            "select_fields": ["id"],
        }]},
        "response": {"results": [{
            "result": {
                "status": "success",
                "result": {"id": "issue-1", "title": "One"},
                "execution_metadata": {"execution_time_ms": 123},
            },
        }]},
    }]))

    path = AgentMCPPath(_config(), rec_dir, mode="replay")
    result = _run_path(path, scenario)
    assert result.status == "ok"
    assert result.total_latency_ms == 123
    assert result.total_records == 1
    assert result.single_record_calls == 1
    assert result.single_record_tokens > 0


def test_scorecard_renders_interim_ratios(tmp_path) -> None:
    scenario = load_scenario("linear-search")
    report = RunReport(
        cells=[
            _cell(scenario, "REST Baseline (via SDK)", "agent-sdk", 400),
            _cell(scenario, "Agent MCP", "agent-mcp", 100),
            _cell(scenario, "Native MCP", "native-mcp", 300),
        ],
        requested_scenarios=["linear-search"],
        requested_paths=["agent-sdk", "agent-mcp", "native-mcp"],
    )

    out = tmp_path / "scorecard.md"
    render_scorecard(report, out)
    text = out.read_text()
    assert "Interim scorecard" in text
    assert "4.0× fewer tokens" in text
    assert "3.0× fewer tokens" in text


def test_salesforce_list_translates_to_soql() -> None:
    scenario = load_scenario("salesforce-list")
    agent_call = scenario.paths["agent-mcp"].tool_calls[0]
    task = Task(
        label="List accounts",
        action="list",
        entity=agent_call.args["entity"],
        metric_focus="bulk_list",
        params={"limit": 50},
    )
    dispatch = _DISPATCH["salesforce"]
    action, params = _translate(task, dispatch)
    assert action == "list"
    assert "q" in params
    assert params["q"].startswith("SELECT Id, Name, Type, Industry FROM Account")
    assert "LIMIT" in params["q"]


def test_salesforce_list_without_soql_raises() -> None:
    task = Task(label="test", action="list", entity="unknown_entity", metric_focus="bulk_list", params={"limit": 10})
    dispatch = {
        "list_limit_key": "q",
        "list_soql": {},
    }
    with pytest.raises(ValueError, match="requires a list_soql template"):
        _translate(task, dispatch)


def _run_path(path: AgentMCPPath, scenario) -> BenchmarkResult:
    task = scenario.task
    if task is None:
        agent_call = scenario.paths["agent-mcp"].tool_calls[0]
        action = agent_call.args.get("action", "get")
        task = Task(
            label=f"{action} {agent_call.args.get('entity', 'unknown')}",
            action=action,
            entity=agent_call.args.get("entity", "unknown"),
            metric_focus="single_record_fetch" if action == "get" else "bulk_list",
            params=agent_call.args.get("params", {}),
        )

    async def collect() -> BenchmarkResult:
        result = None
        async for _step, current in path.run_task(task, scenario):
            result = current
        assert result is not None
        return result

    return asyncio.run(collect())


def _config() -> LiveConfig:
    return LiveConfig(
        organization_id="org-id",
        client_id="client-id",
        client_secret="secret",
        connector_ids={
            "slack": "slack-id",
            "linear": "linear-id",
            "granola": "granola-id",
        },
    )


def _cell(scenario, path_name: str, path_short: str, tokens: int) -> Cell:
    result = BenchmarkResult(path_name=path_name)
    result.steps.append(StepResult(
        label="step",
        latency_ms=1,
        payload_bytes=tokens,
        tokens=tokens,
        records=1,
    ))
    result.total_records = 1
    return Cell(
        scenario=scenario,
        path_name=path_name,
        path_short=path_short,
        result=result,
    )
