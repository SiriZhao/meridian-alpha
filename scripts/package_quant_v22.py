"""Seal completed synthetic challenger records and audit paired realized exposure."""

import argparse
import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

from meridian.config import load_policies
from meridian.quant.backtest import QuantDataset, ReplayResult
from meridian.quant.experiments import ChallengerExperimentPlan, isolated_output
from meridian.quant.integration import immutable_record
from meridian.quant.packet import build_research_packet
from meridian.quant.policy import ChallengerPolicy
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.trading_calendar import session_close


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, output = isolated_output(args.input), isolated_output(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summaries = list(source.glob("summary-*.json"))
    if len(summaries) != 1:
        raise ValueError("CHALLENGER_SUMMARY_COUNT")
    summary = json.loads(summaries[0].read_text())
    if summary["engine_source_hash"] != ENGINE_SOURCE_HASH or any(r["status"] != "REPLAY_COMPLETE" for r in summary["results"]):
        raise ValueError("CHALLENGER_INCOMPLETE_OR_DIFFERENT_ENGINE")
    dataset = QuantDataset.model_validate_json((source / "synthetic-dataset.json").read_text())
    plan = ChallengerExperimentPlan.model_validate_json((source / "plan.json").read_text())
    if dataset.evidence_status != "SYNTHETIC_DIAGNOSTIC":
        raise ValueError("CHALLENGER_PACKAGE_ONLY_SYNTHETIC")
    archive = output / "synthetic-full-registry.zip"
    # Build bytes in memory; immutable publishing never overwrites prior output.
    import io
    buffer = io.BytesIO()
    digests = {}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(source.rglob("*.json")):
            name = path.relative_to(source).as_posix()
            content = path.read_bytes()
            digests[name] = hashlib.sha256(content).hexdigest()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(entry, content)
    content = buffer.getvalue()
    if archive.exists() and archive.read_bytes() != content:
        raise ValueError("CHALLENGER_ARCHIVE_IMMUTABLE_CONFLICT")
    if not archive.exists():
        archive.write_bytes(content)
    manifest = {"version": "quant-v22-archive.v1", "archive_sha256": hashlib.sha256(content).hexdigest(),
        "files": digests, "engine_hash": ENGINE_SOURCE_HASH, "dataset_hash": dataset.digest, "plan_hash": plan.digest}
    for name, payload in (("archive-manifest.json", manifest), ("synthetic-summary.json", summary),
                          ("predeclared-plan.json", json.loads(plan.stable_json()))):
        immutable_record(output / name, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    replay_by_key = {(r["fold"], r["partition"], r["variant"]): ReplayResult.model_validate_json(
        (source / "replays" / (r["replay_hash"] + ".json")).read_text()) for r in summary["results"]}
    audits = []
    for fold in plan.folds:
        for partition in ("validation", "test"):
            control = replay_by_key[fold.name, partition, "V22_MATCHED_BUDGET"]
            for group in ("ABSOLUTE", "RELATIVE", "TREND"):
                treatment = replay_by_key[fold.name, partition, "V22_NEUTRAL_" + group]
                differences = [abs(a.exposure - b.exposure) for a, b in zip(control.days, treatment.days, strict=True)]
                maximum = max(differences)
                audits.append({"fold": fold.name, "partition": partition, "removed_signal_group": group,
                    "nominal_budget": "0.25", "max_realized_exposure_difference": str(maximum),
                    "status": "MATCHED_WITHIN_DECLARED_0.001_TOLERANCE" if maximum <= 0.001 else "NOT_MATCHED_NO_ISOLATED_ALPHA_CLAIM"})
    immutable_record(output / "matched-exposure-audit.json", json.dumps(audits, sort_keys=True, indent=2) + "\n")
    cutoff = session_close(plan.folds[0].validation_end)
    policies = replace(load_policies(Path(__file__).resolve().parents[1] / "policies"), risk=plan.risk)
    packet = build_research_packet({s.canonical_symbol: s for s in dataset.series}, tuple(m.symbol for m in dataset.memberships),
        cutoff=cutoff, policies=policies, policy=ChallengerPolicy(), metadata=dataset.security_metadata, diagnostic=True)
    immutable_record(output / "research-packet-example.json", packet.stable_json() + "\n")
    print(json.dumps({"status": "PACKAGED_SYNTHETIC_DIAGNOSTIC", "archived_files": len(digests),
        "evaluations": len(summary["results"]), "matched_exposure_pairs": len(audits), "engine_hash": ENGINE_SOURCE_HASH}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
