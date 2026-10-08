"""Verify published quant contracts and every archived diagnostic experiment.

No extraction, network access, account data or canonical-runtime writes.
The optional current-engine check is for release acceptance; historical
archives may remain valid records of a previous engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from meridian.quant.backtest import QuantDataset, ReplayResult
from meridian.quant.experiments import ExperimentPlan
from meridian.quant.features import FeatureSnapshot
from meridian.quant.integration import QuantShadowRecord
from meridian.quant.policy import QuantPolicy
from meridian.quant.version import ENGINE_SOURCE_HASH


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate(root: Path, *, current_engine: bool = False) -> dict[str, object]:
    models = {"quant-v2-policy.schema.json": QuantPolicy,
              "quant-v2-features.schema.json": FeatureSnapshot,
              "quant-v2-dataset.schema.json": QuantDataset,
              "quant-v2-experiment-plan.schema.json": ExperimentPlan,
              "quant-shadow-comparison.v1.schema.json": QuantShadowRecord}
    for filename, model in models.items():
        saved = json.loads((root / "schemas" / filename).read_text(encoding="utf-8"))
        generated = model.model_json_schema()
        generated.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
                          "$id": "https://meridian-alpha.local/schemas/" + filename})
        require(saved == generated, "QUANT_SCHEMA_DRIFT:" + filename)
    directory = root / "docs/quant-v2/experiments"
    manifest = json.loads((directory / "archive-manifest.json").read_text(encoding="utf-8"))
    archive = directory / "synthetic-full-registry.zip"
    require(sha(archive.read_bytes()) == manifest["archive_sha256"], "QUANT_ARCHIVE_DIGEST_MISMATCH")
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        require(len(names) == len(set(names)), "QUANT_ARCHIVE_DUPLICATE_MEMBER")
        require(set(names) == set(manifest["files"]), "QUANT_ARCHIVE_MEMBER_MISMATCH")
        objects = {}
        for name, digest in manifest["files"].items():
            # Read in memory only, so archive names cannot escape into files.
            content = source.read(name)
            require(sha(content) == digest, "QUANT_ARCHIVED_FILE_DIGEST_MISMATCH:" + name)
            objects[name] = json.loads(content)
    dataset = QuantDataset.model_validate(objects["synthetic-dataset.json"])
    plan = ExperimentPlan.model_validate(objects["plan.json"])
    summary_paths = [n for n in names if n.startswith("summary-")]
    require(len(summary_paths) == 1, "QUANT_ARCHIVE_SUMMARY_COUNT")
    summary = objects[summary_paths[0]]
    require(summary == json.loads((directory / "synthetic-summary.json").read_text(encoding="utf-8")),
            "QUANT_DELIVERY_SUMMARY_MISMATCH")
    require(plan.stable_json() == ExperimentPlan.model_validate_json(
        (directory / "predeclared-plan.json").read_text(encoding="utf-8")).stable_json(), "QUANT_DELIVERY_PLAN_MISMATCH")
    require(dataset.evidence_status == summary["evidence_status"] == "SYNTHETIC_DIAGNOSTIC",
            "QUANT_DIAGNOSTIC_EVIDENCE_MISMATCH")
    require(summary["dataset_hash"] == dataset.digest and summary["plan_hash"] == plan.digest,
            "QUANT_ARCHIVE_INPUT_IDENTITY_MISMATCH")
    require(not summary["financial_alpha_demonstrated"] and not summary["automatic_promotion"],
            "QUANT_DIAGNOSTIC_AUTHORITY_MISMATCH")
    if current_engine:
        require(summary["engine_source_hash"] == ENGINE_SOURCE_HASH, "QUANT_ARCHIVED_ENGINE_NOT_CURRENT")
    expected = {(f.name, p, v.name) for f in plan.folds for p in ("validation", "test") for v in plan.variants}
    actual = {(r["fold"], r["partition"], r["variant"]) for r in summary["results"]}
    require(actual == expected and len(summary["results"]) == len(expected), "QUANT_EVALUATION_COVERAGE_MISMATCH")
    variants = {v.name: v for v in plan.variants}
    used = set()
    for row in summary["results"]:
        require(row["status"] == "REPLAY_COMPLETE", "QUANT_DIAGNOSTIC_REPLAY_INCOMPLETE")
        filename = "replays/" + row["replay_hash"] + ".json"
        replay = ReplayResult.model_validate(objects[filename])
        used.add(filename)
        variant = variants[row["variant"]]
        require(sha(replay.stable_json().encode()) == row["replay_hash"], "QUANT_REPLAY_IDENTITY_MISMATCH")
        require(replay.dataset_hash == dataset.digest and replay.engine_hash == summary["engine_source_hash"],
                "QUANT_REPLAY_INPUT_MISMATCH")
        require(replay.policy_hash == sha(variant.policy.stable_json().encode())
                and replay.cost_hash == sha(variant.costs.stable_json().encode())
                and replay.risk_hash == sha(plan.risk.model_dump_json().encode()), "QUANT_REPLAY_POLICY_MISMATCH")
        require(replay.fold == row["fold"] and replay.partition == row["partition"]
                and replay.strategy == variant.strategy, "QUANT_REPLAY_ATTRIBUTION_MISMATCH")
        require(replay.evidence_status == "SYNTHETIC_DIAGNOSTIC" and not replay.automatic_promotion,
                "QUANT_REPLAY_AUTHORITY_MISMATCH")
        require(len(replay.days) == row["metrics"]["sessions"], "QUANT_REPLAY_SESSION_COUNT_MISMATCH")
    require(used == {n for n in names if n.startswith("replays/")}, "QUANT_UNREFERENCED_REPLAY")
    return {"status": "PASS", "schemas": len(models), "archived_files": len(names),
            "replays": len(used), "evaluations": len(expected),
            "engine_source_hash": summary["engine_source_hash"], "current_engine_checked": current_engine,
            "financial_alpha_demonstrated": False, "canonical_runtime_written": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-current-engine", action="store_true")
    args = parser.parse_args()
    result = validate(Path(__file__).resolve().parents[1], current_engine=args.require_current_engine)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
