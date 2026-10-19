"""Model/effort OpenCode 1.x và 2.x: mọi tiến trình đều dùng tests/fakebin."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest

from conftest import FAKEBIN, ateam, tasks, write_project_config
from ateam.config import agent_from_dict, parse_model_efforts, parse_models, parse_opencode_catalog, provider_template
from ateam.opencode import major_version, standard_models


def test_v2_catalog_parser():
    output = json.dumps({"location": {"directory": "/project"}, "data": [
        {"providerID": "openrouter", "id": "team/model", "enabled": True,
         "variants": [{"id": "low"}, {"id": "deep"}, {"id": "low"}, {}, None],
         "settings": {"apiKey": "FAKE_CATALOG_SECRET"}},
        {"providerID": "xai", "id": "grok-build-0.1", "variants": []},
        {"providerID": "xai", "id": "disabled", "enabled": False, "variants": []},
        {"providerID": "xai", "id": "incomplete"},
        {"providerID": "xai", "id": 42, "variants": []}, None,
    ]})
    assert parse_models(output) == ["openrouter/team/model", "xai/grok-build-0.1"]
    assert parse_models(output, "openrouter") == ["openrouter/team/model"]
    assert parse_model_efforts(output) == {"openrouter/team/model": ["low", "deep"], "xai/grok-build-0.1": []}
    assert "FAKE_CATALOG_SECRET" not in repr(parse_opencode_catalog(output))
    assert parse_opencode_catalog('{"location":{},"data":[]}') == []
    for bad in ('{"invalid":', '{"data":"bad"}', '{"error":"HTTP 500"}', '[]', ''):
        assert parse_opencode_catalog(bad) is None


@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("syntax", [["--variant", "{effort}"], ["--model", "{model}#{effort}"]])
def test_effort_arguments_follow_version_without_rewriting_config(major, syntax):
    a = agent_from_dict("deepseek", {**provider_template("opencode"), "effort_args": syntax})
    a.opencode_major = major
    a.model = "opencode/deepseek-v4.1-flash-free"
    a.model_efforts = {a.model: ["low", "high", "max"], "xai/grok-build-0.1": []}
    a.effort = "low"
    expected = (["--model", a.model, "--variant", "high"] if major == 1
                else ["--model", a.model + "#high"])
    assert a.argv("P", effort="medium") == ["opencode", "run"] + expected + ["P"]
    assert a.effort_args == syntax
    assert a.argv("P", model="xai/grok-build-0.1", effort="high") == [
        "opencode", "run", "--model", "xai/grok-build-0.1", "P"]
    if major == 2:
        assert a.argv("P", model=a.model + "#max", effort="low")[-2] == a.model + "#low"
        assert a.argv("P", model=a.model + "#max")[-2] == a.model + "#max"
        assert a.label(a.model + "#max") == a.model + " · max"
        assert a.label(a.model + "#max", "low") == a.model + " · low"
        a.model = ""
        assert a.argv("P", effort="high") == ["opencode", "run", "P"]
        assert a.argv("P", model="provider/unknown", effort="high") == [
            "opencode", "run", "--model", "provider/unknown", "P"]


def test_version_and_custom_commands():
    assert major_version("opencode v2.0.32") == 2
    assert major_version("1.19.3") == 1
    assert major_version("not a version") is None
    a = agent_from_dict("custom", provider_template("opencode"))
    assert standard_models(a)
    a.models_command += ["--server", "http://localhost:1234"]
    assert not standard_models(a)
    a.effort_args = ["--custom-effort", "{effort}"]
    a.opencode_major = 2
    a.model = "xai/grok-4.7"
    a.model_efforts = {a.model: ["high"]}
    assert "--custom-effort" in a.argv("P", effort="high")


@pytest.mark.parametrize("version", ["1.19.3", "2.0.32"])
def test_refresh_run_and_doctor_with_fake_cli(env, project, tmp_path, version):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = version
    env["ATEAM_FAKE_OPENCODE_LOG"] = str(tmp_path / "opencode.log")
    write_project_config(project, '[agents.opencode]\nmodel = "opencode/deepseek-v4.1-flash-free"\neffort = "medium"\n')
    refreshed = ateam(env, project, "models", "opencode", "--refresh")
    assert "tìm thấy 6 model" in refreshed.stdout
    state = json.loads((Path(env["XDG_CONFIG_HOME"]) / "ateam/state.json").read_text())
    assert state["model_efforts"]["opencode"]["opencode/deepseek-v4.1-flash-free"] == ["low", "high", "max"]
    assert state["model_efforts"]["opencode"]["xai/grok-build-0.1"] == []
    ateam(env, project, "add", "--to", "opencode", "tạo b")
    ateam(env, project, "run", "-q")
    assert tasks(project)[0].status == "done"
    args = (tmp_path / "args.log").read_text()
    doctor = ateam(env, project, "doctor").stdout
    if version.startswith("2"):
        assert "--verbose" not in refreshed.stdout
        assert "--model opencode/deepseek-v4.1-flash-free#high" in args and "--variant" not in args
        assert "--model opencode/deepseek-v4.1-flash-free#high" in doctor
        calls = (tmp_path / "opencode.log").read_text()
        assert "location[directory]=" + str(project) in calls and "--verbose" not in calls
    else:
        assert "--variant high" in args and "--variant high" in doctor
    assert "FAKE_CATALOG_SECRET" not in refreshed.stdout + doctor + repr(state)


def test_web_snapshot_and_options_use_v2_model_metadata(env, project, monkeypatch):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "2.0.32"
    o = _orch(env, project, monkeypatch)
    from ateam.web import WebApp
    app = WebApp(project, o.cfg, o.db)
    a = app.cfg.agents["opencode"]
    a.model = "opencode/deepseek-v4.1-flash-free"
    a.effort = "medium"

    async def main():
        await app.orch.setup()
        state = next(x for x in app.snapshot()["agents"] if x["name"] == a.name)
        assert state["efforts"] == ["low", "high", "max"] and state["effort"] == "high"
        assert "xai/grok-4.7" in state["models"]
        reply = await app.handle({"op": "agent_option", "agent": a.name, "key": "model",
                                  "value": "xai/grok-build-0.1"})
        assert reply[2]["agent"]["efforts"] == [] and reply[2]["agent"]["effort"] == ""
    asyncio.run(main())


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from ateam import config
    importlib.reload(config)
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    return Orchestrator(project, config.load_config(project), DB(project / ".ateam/team.db"))


def test_startup_replaces_old_cache_and_shares_probe_across_aliases(env, project, tmp_path, monkeypatch):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "2.0.32"
    env["ATEAM_FAKE_OPENCODE_LOG"] = str(tmp_path / "queries.log")
    o = _orch(env, project, monkeypatch)
    a = o.cfg.agents["opencode"]
    a.models = ["old/stale"]
    a.model_efforts = {"opencode/deepseek-v4.1-flash-free": ["ultra"]}
    alias = agent_from_dict("deepseek", {**provider_template("opencode"),
                                        "command": [str(FAKEBIN / "opencode"), "run", "{prompt}"]})
    o.cfg.agents[alias.name] = alias

    async def main():
        await o.setup()
        await asyncio.gather(o.prepare_agent(a), o.prepare_agent(alias))
        assert a.opencode_major == alias.opencode_major == 2
        assert a.model_efforts["opencode/deepseek-v4.1-flash-free"] == ["low", "high", "max"]
        assert "old/stale" not in a.models
        assert "anthropic/claude-sonnet-5-5" in alias.models  # alias không bị lọc ngầm theo tên
        # Reload cấu hình tạo đối tượng mới vẫn dùng cache runtime, không dò lại binary/catalog.
        fresh = agent_from_dict("deepseek", {**provider_template("opencode"), "models_filter": "xai"})
        await o.prepare_agent(fresh)
        assert set(fresh.model_efforts) == {"xai/grok-build-0.1", "xai/grok-4.7", "xai/grok-5-fast"}
    asyncio.run(main())
    queries = (tmp_path / "queries.log").read_text().splitlines()
    assert queries.count("--version") == 1
    assert sum(q.startswith("api model.list") for q in queries) == 1
    assert "FAKE_CATALOG_SECRET" not in (o.logs / "system.log").read_text()


@pytest.mark.parametrize("failure", ["error", "invalid", "empty", "timeout"])
def test_v2_metadata_failure_falls_back_without_guessing_effort(env, project, monkeypatch, failure):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "2.0.32"
    env["ATEAM_FAKE_OPENCODE_CATALOG"] = failure
    o = _orch(env, project, monkeypatch)
    a = o.cfg.agents["opencode"]
    a.model_efforts = {"xai/grok-4.7": ["ultra"]}
    msg = asyncio.run(o.discover_models(a.name, timeout=0.3 if failure == "timeout" else 5))
    assert "tìm thấy 6 model" in msg and "thiếu metadata effort" in msg
    assert a.model_efforts == {} and a.efforts_for("xai/grok-4.7") == []
    assert "#" not in " ".join(a.argv("P", model="xai/grok-4.7", effort="high"))
    assert "FAKE_CATALOG_SECRET" not in msg


def test_total_failure_preserves_cache_and_refresh_can_recover(env, project, monkeypatch):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "2.0.32"
    env["ATEAM_FAKE_OPENCODE_CATALOG"] = "error"
    env["ATEAM_FAKE_OPENCODE_MODELS_FAIL"] = "1"
    o = _orch(env, project, monkeypatch)
    a = o.cfg.agents["opencode"]
    a.models, a.model_efforts = ["cached/model"], {"cached/model": ["low"]}

    async def main():
        msg = await o.discover_models(a.name)
        assert "giữ danh sách đã lưu" in msg
        assert a.models == ["cached/model"] and a.model_efforts == {"cached/model": ["low"]}
        monkeypatch.delenv("ATEAM_FAKE_OPENCODE_MODELS_FAIL")
        monkeypatch.delenv("ATEAM_FAKE_OPENCODE_CATALOG")
        msg = await o.discover_models(a.name)
        assert "tìm thấy 6 model" in msg
        assert a.model_efforts["xai/grok-build-0.1"] == []
    asyncio.run(main())


def test_failed_version_probe_preserves_custom_syntax(env, project, tmp_path, monkeypatch):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "fail"
    env["ATEAM_FAKE_OPENCODE_LOG"] = str(tmp_path / "queries.log")
    o = _orch(env, project, monkeypatch)
    a = o.cfg.agents["opencode"]
    a.effort_args = ["--model", "{model}#{effort}"]
    a.model = "xai/grok-4.7"
    a.effort = "high"

    async def main():
        await o.prepare_agent(a)
        await o.prepare_agent(a)
    asyncio.run(main())
    assert a.opencode_major is None
    assert a.argv("P") == ["opencode", "run", "--model", "xai/grok-4.7#high", "P"]
    assert (tmp_path / "queries.log").read_text().splitlines().count("--version") == 1
    assert "Không nhận diện được phiên bản OpenCode" in (o.logs / "system.log").read_text()


def test_cancelling_one_alias_keeps_shared_catalog_alive(env, project, monkeypatch):
    from ateam.opencode import Catalog
    o = _orch(env, project, monkeypatch)
    a = o.cfg.agents["opencode"]

    async def main():
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_catalog(_binary, _timeout):
            entered.set()
            await release.wait()
            return Catalog(["xai/grok-4.7"], {"xai/grok-4.7": ["high"]})

        monkeypatch.setattr(o.opencode, "_catalog", slow_catalog)
        first = asyncio.create_task(o.opencode.catalog(a))
        second = asyncio.create_task(o.opencode.catalog(a))
        await entered.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second).efforts == {"xai/grok-4.7": ["high"]}
    asyncio.run(main())


def test_cancelling_catalog_stops_its_process(env, project, monkeypatch):
    env["ATEAM_FAKE_OPENCODE_VERSION"] = "2.0.32"
    env["ATEAM_FAKE_OPENCODE_CATALOG"] = "timeout"
    o = _orch(env, project, monkeypatch)
    from ateam import opencode
    original = opencode.Run
    runs = []

    def capture(*args, **kwargs):
        run = original(*args, **kwargs)
        runs.append(run)
        return run

    monkeypatch.setattr(opencode, "Run", capture)

    async def main():
        job = asyncio.create_task(o.opencode.catalog(o.cfg.agents["opencode"]))
        async def started():
            while not runs or runs[0].proc is None:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(started(), 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        # Truy vấn được chia sẻ tự dọn khi không còn alias nào chờ.
        query = next(iter(o.opencode._catalogs.values()))
        with pytest.raises(asyncio.CancelledError):
            await query
        assert runs[0].proc.returncode is not None
    asyncio.run(main())
