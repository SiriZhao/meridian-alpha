"""Verify additive contracts and the complete V2.2 registry, read-only."""

import hashlib
import json
import subprocess
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

import yaml

from meridian.quant.backtest import QuantDataset, ReplayResult
from meridian.quant.experiments import ChallengerExperimentPlan
from meridian.quant.packet import QuantResearchPacketV22
from meridian.quant.policy import ChallengerPolicy
from meridian.quant.version import ENGINE_SOURCE_HASH


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/generate_quant_v22_contracts.py"), "--check"], check=True, cwd=root)
    policy = ChallengerPolicy.model_validate(yaml.safe_load((root / "policies/quant-v22.yaml").read_text()))
    require(policy == ChallengerPolicy(), "CHALLENGER_SHIPPED_POLICY_DRIFT")
    directory = root / "docs/quant-v2/experiments-v22"
    manifest = json.loads((directory / "archive-manifest.json").read_text())
    archive = directory / "synthetic-full-registry.zip"
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"], "CHALLENGER_ZIP_HASH")
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        require(len(names) == len(set(names)) and set(names) == set(manifest["files"]), "CHALLENGER_ARCHIVE_MEMBERS")
        objects = {}
        for name, digest in manifest["files"].items():
            content = zipped.read(name)
            require(hashlib.sha256(content).hexdigest() == digest, "CHALLENGER_MEMBER_HASH:" + name)
            objects[name] = json.loads(content)
    summary_name = next(n for n in names if n.startswith("summary-"))
    summary = objects[summary_name]
    require(summary == json.loads((directory / "synthetic-summary.json").read_text()), "CHALLENGER_SUMMARY_DRIFT")
    dataset = QuantDataset.model_validate(objects["synthetic-dataset.json"])
    plan = ChallengerExperimentPlan.model_validate(objects["plan.json"])
    require(plan == ChallengerExperimentPlan.model_validate_json((directory / "predeclared-plan.json").read_text()), "CHALLENGER_PLAN_DRIFT")
    require(dataset.digest == manifest["dataset_hash"] == summary["dataset_hash"], "CHALLENGER_DATA_HASH")
    require(plan.digest == manifest["plan_hash"] == summary["plan_hash"], "CHALLENGER_PLAN_HASH")
    require(ENGINE_SOURCE_HASH == manifest["engine_hash"] == summary["engine_source_hash"], "CHALLENGER_CURRENT_ENGINE_DRIFT")
    require(dataset.evidence_status == summary["evidence_status"] == "SYNTHETIC_DIAGNOSTIC"
            and not summary["automatic_promotion"] and not summary["financial_alpha_demonstrated"], "CHALLENGER_AUTHORITY")
    expected = {(f.name, partition, v.name) for f in plan.folds for partition in ("validation", "test") for v in plan.variants}
    require(expected == {(r["fold"], r["partition"], r["variant"]) for r in summary["results"]}
            and len(expected) == len(summary["results"]), "CHALLENGER_EVALUATION_COVERAGE")
    variants = {v.name: v for v in plan.variants}
    used = set()
    replay_by_key = {}
    for row in summary["results"]:
        require(row["status"] == "REPLAY_COMPLETE", "CHALLENGER_REPLAY_INCOMPLETE")
        name = "replays/" + row["replay_hash"] + ".json"
        replay = ReplayResult.model_validate(objects[name])
        replay_by_key[row["fold"], row["partition"], row["variant"]] = replay
        used.add(name)
        require(hashlib.sha256(replay.stable_json().encode()).hexdigest() == row["replay_hash"], "CHALLENGER_REPLAY_HASH")
        variant = variants[row["variant"]]
        strategy = variant.challenger or variant.policy
        require(replay.policy_hash == hashlib.sha256(strategy.stable_json().encode()).hexdigest(), "CHALLENGER_POLICY_HASH")
        require(replay.cost_hash == hashlib.sha256(variant.costs.stable_json().encode()).hexdigest()
                and replay.risk_hash == hashlib.sha256(plan.risk.model_dump_json().encode()).hexdigest(), "CHALLENGER_COST_RISK_HASH")
        require(replay.engine_hash == ENGINE_SOURCE_HASH and replay.dataset_hash == dataset.digest
                and replay.fold == row["fold"] and replay.partition == row["partition"] and replay.strategy == variant.strategy,
                "CHALLENGER_REPLAY_ATTRIBUTION")
        require(all(d.cash >= 0 and d.costs >= 0 and (d.turnover > 0 or d.costs == 0) for d in replay.days), "CHALLENGER_CASH_COST_INVARIANTS")
    require(used == {n for n in names if n.startswith("replays/")}, "CHALLENGER_UNREFERENCED_REPLAY")
    audits = json.loads((directory / "matched-exposure-audit.json").read_text())
    require(len(audits) == len(plan.folds) * 2 * 3, "CHALLENGER_EXPOSURE_AUDIT_COVERAGE")
    require(len({(r["fold"], r["partition"], r["removed_signal_group"]) for r in audits}) == len(audits), "CHALLENGER_DUPLICATE_EXPOSURE_AUDIT")
    for row in audits:
        control = replay_by_key[row["fold"], row["partition"], "V22_MATCHED_BUDGET"]
        treatment = replay_by_key[row["fold"], row["partition"], "V22_NEUTRAL_" + row["removed_signal_group"]]
        maximum = max(abs(a.exposure - b.exposure) for a, b in zip(control.days, treatment.days, strict=True))
        status = "MATCHED_WITHIN_DECLARED_0.001_TOLERANCE" if maximum <= Decimal(".001") else "NOT_MATCHED_NO_ISOLATED_ALPHA_CLAIM"
        require(Decimal(row["max_realized_exposure_difference"]) == maximum and row["status"] == status,
                "CHALLENGER_EXPOSURE_AUDIT_MISMATCH")
    packet = QuantResearchPacketV22.model_validate_json((directory / "research-packet-example.json").read_text())
    require(packet.engine_hash == ENGINE_SOURCE_HASH and packet.data_certification_class == "SYNTHETIC_DIAGNOSTIC"
            and not packet.trade_authorized and not packet.eligible_hypothetical_drafts
            and all(r.current_exposure is None for r in packet.symbols), "CHALLENGER_EXAMPLE_AUTHORITY")
    print(json.dumps({"status": "PASS", "contracts": 7, "archived_files": len(names), "evaluations": len(expected),
        "replays": len(used), "engine_hash": ENGINE_SOURCE_HASH, "financial_alpha_demonstrated": False,
        "canonical_runtime_written": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
