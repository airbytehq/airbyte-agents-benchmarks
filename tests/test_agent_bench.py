from __future__ import annotations

import asyncio
import json

from agent_bench.config import LiveConfig
from agent_bench.export.scorecard import render_scorecard
from agent_bench.metrics import BenchmarkResult, StepResult
from agent_bench.paths.agent_engine_mcp import AgentEngineMCPPath
from agent_bench.paths.claude_mcp import ClaudeMCPPath
from agent_bench.recordings import validate_recordings
from agent_bench.runner import Cell, RunReport
from agent_bench.scenarios.loader import load_scenario


def test_scenario_targets_match_launch_plan() -> None:
    slack = load_scenario("slack")
    slack_get = next(task for task in slack.tasks if task.action == "get")
    assert slack_get.params["id"] == "C02TD5CB7PZ"
    assert slack_get.params["name_hint"] == "feedback_survey_results"

    granola = load_scenario("granola")
    granola_search = next(task for task in granola.tasks if task.action == "search")
    granola_get = next(task for task in granola.tasks if task.action == "get")
    granola_list = next(task for task in granola.tasks if task.action == "list")
    assert granola_search.params["limit"] == 1
    assert granola_get.params["id"] == "not_ES3idLqBAmN9L1"
    assert granola_get.params["claude_mcp_id"] == "96457d50-5ed1-4d81-a2fc-f43c2b93530d"
    assert granola_list.params["limit"] == 25


def test_path_planning_uses_connector_specific_shapes(tmp_path) -> None:
    config = _config()

    granola = load_scenario("granola")
    granola_get = next(task for task in granola.tasks if task.action == "get")
    ae_plan = AgentEngineMCPPath(config, tmp_path).plan(granola_get, granola)
    ae_item = ae_plan.calls[0].args["items"][0]
    assert ae_item["params"] == {"note_id": "not_ES3idLqBAmN9L1"}
    assert ae_item["select_fields"] == [
        "id",
        "title",
        "created_at",
        "updated_at",
        "attendees",
        "summary_text",
    ]
    assert "describe_connector" in ae_plan.notes[0]

    claude_plan = ClaudeMCPPath(tmp_path).plan(granola_get, granola)
    assert claude_plan.calls[0].args["meeting_id"] == "96457d50-5ed1-4d81-a2fc-f43c2b93530d"


def test_ae_mcp_recording_parses_execution_metadata_latency(tmp_path) -> None:
    scenario = load_scenario("linear")
    task = next(task for task in scenario.tasks if task.action == "get")
    rec_dir = tmp_path / "recordings" / "ae-mcp" / "linear"
    rec_dir.mkdir(parents=True)
    (rec_dir / "get.json").write_text(json.dumps([{
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

    path = AgentEngineMCPPath(_config(), tmp_path / "recordings" / "ae-mcp")
    result = _run_path(path, task, scenario)
    assert result.status == "ok"
    assert result.total_latency_ms == 123
    assert result.total_records == 1
    assert result.single_record_calls == 1
    assert result.single_record_tokens > 0


def test_validation_flags_stale_ae_mcp_recordings(tmp_path) -> None:
    rec_dir = tmp_path / "ae-mcp" / "linear"
    rec_dir.mkdir(parents=True)
    (rec_dir / "get.json").write_text(json.dumps([{
        "tool": "mcp__airbyte-agent__execute",
        "args": {"items": [{
            "connector_id": "linear-id",
            "entity": "issues",
            "action": "get",
            "params": {"id": "ec6e00c7-dd96-4875-952c-69ecc33ce06d"},
        }]},
        "wall_clock_ms": 9,
        "response": {"results": [{
            "result": {
                "status": "success",
                "result": {"id": "issue-1"},
                "execution_metadata": {"execution_time_ms": 9},
            },
        }]},
    }]))

    issues = validate_recordings(["linear"], ["ae-mcp"], tmp_path, _config())
    messages = [issue.message for issue in issues]
    assert any("missing mandatory select_fields" in message for message in messages)


def test_scorecard_renders_interim_ratios(tmp_path) -> None:
    scenario = load_scenario("linear")
    task = scenario.tasks[0]
    report = RunReport(
        cells=[
            _cell(scenario, task, "Agent Engine SDK", "ae-sdk", 400),
            _cell(scenario, task, "Agent Engine MCP", "ae-mcp", 100),
            _cell(scenario, task, "Claude MCP", "claude", 300),
        ],
        requested_scenarios=["linear"],
        requested_paths=["ae-sdk", "ae-mcp", "claude"],
    )

    out = tmp_path / "scorecard.md"
    render_scorecard(report, out)
    text = out.read_text()
    assert "Interim scorecard" in text
    assert "4.0× fewer tokens" in text
    assert "3.0× fewer tokens" in text


def _run_path(path: AgentEngineMCPPath, task, scenario) -> BenchmarkResult:
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


def _cell(scenario, task, path_name: str, path_short: str, tokens: int) -> Cell:
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
        task=task,
        path_name=path_name,
        path_short=path_short,
        result=result,
    )
