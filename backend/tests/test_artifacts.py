"""T34 artifact 入库与投递测试 —— 校验（不信任 agent 输出）+ 落库 + 挂消息 + REST 读。"""

import json
import tempfile
from pathlib import Path

import httpx
import pytest

from api.app import create_app
from api.artifacts import ManifestError, ingest_run
from api.store import Store


def _make_run(tmp: Path, manifest: dict, files: dict[str, str]) -> Path:
    run_dir = tmp / "runs" / "r-1"
    run_dir.mkdir(parents=True)
    for name, content in files.items():
        (run_dir / name).write_text(content, encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def _store_with_message():
    store = Store(":memory:")
    sid = store.create_session()
    mid = store.add_message(sid, "assistant", "")
    return store, sid, mid


def test_ingest_valid_manifest_attaches_and_reads():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        chart_opt = {"series": [{"type": "heatmap", "data": []}]}
        run_dir = _make_run(
            tmp,
            manifest={
                "run_id": "r-1",
                "code_ref": "code.py",
                "artifacts": [
                    {"id": "a1", "kind": "chart", "title": "相关性热力图",
                     "path": "chart.json", "inputs": {"symbols": ["600519"]}},
                ],
            },
            files={"chart.json": json.dumps(chart_opt), "code.py": "print(1)"},
        )
        store, _sid, mid = _store_with_message()
        ids = ingest_run(store, run_dir, mid)
        assert len(ids) == 1
        art = store.get_artifact(ids[0])
        assert art["kind"] == "chart"
        assert art["message_id"] == mid
        assert art["payload"] == chart_opt  # chart 内联 payload
        assert art["inputs"]["symbols"] == ["600519"]
        # 挂到消息
        assert store.list_artifacts_for_message(mid)[0]["id"] == ids[0]


def test_reject_bad_kind():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run_dir = _make_run(
            tmp,
            manifest={"artifacts": [{"kind": "video", "path": "x.mp4"}]},
            files={"x.mp4": "data"},
        )
        store, _sid, mid = _store_with_message()
        with pytest.raises(ManifestError):
            ingest_run(store, run_dir, mid)
        # 非法 → 不落任何库
        assert store.list_artifacts_for_message(mid) == []


def test_reject_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run_dir = _make_run(
            tmp,
            manifest={"artifacts": [{"kind": "table", "path": "nope.csv"}]},
            files={},
        )
        store, _sid, mid = _store_with_message()
        with pytest.raises(ManifestError):
            ingest_run(store, run_dir, mid)


def test_reject_path_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run_dir = _make_run(
            tmp,
            manifest={"artifacts": [{"kind": "markdown", "path": "../../etc/passwd"}]},
            files={},
        )
        store, _sid, mid = _store_with_message()
        with pytest.raises(ManifestError):
            ingest_run(store, run_dir, mid)


def test_reject_malformed_chart_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run_dir = _make_run(
            tmp,
            manifest={"artifacts": [{"kind": "chart", "path": "chart.json"}]},
            files={"chart.json": "{not json"},
        )
        store, _sid, mid = _store_with_message()
        with pytest.raises(ManifestError):
            ingest_run(store, run_dir, mid)


async def test_rest_get_artifact_and_message_includes_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        chart_opt = {"series": [{"type": "line", "data": [1, 2]}]}
        run_dir = _make_run(
            tmp,
            manifest={"artifacts": [{"kind": "chart", "title": "T", "path": "chart.json"}]},
            files={"chart.json": json.dumps(chart_opt)},
        )
        app = create_app(db_path=":memory:", workspace_root=tmp)
        store = app.state.store
        sid = store.create_session()
        mid = store.add_message(sid, "assistant", "结论")
        ids = ingest_run(store, run_dir, mid)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t",
                                     trust_env=False) as client:
            r = await client.get(f"/api/artifacts/{ids[0]}")
            assert r.status_code == 200
            assert r.json()["payload"] == chart_opt

            msgs = (await client.get(f"/api/sessions/{sid}/messages")).json()
            assistant = [m for m in msgs if m["role"] == "assistant"][0]
            assert len(assistant["artifacts"]) == 1
            assert assistant["artifacts"][0]["id"] == ids[0]

            assert (await client.get("/api/artifacts/nope")).status_code == 404
