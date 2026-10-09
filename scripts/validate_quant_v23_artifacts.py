"""Bounded archive/schema/metrics/authority checks, never live network or ledger."""
import hashlib
import json
import zipfile
from pathlib import Path

import yaml

from meridian.quant.backtest import QuantDataset, ReplayResult
from meridian.quant.flagship_experiments import FlagshipExperimentPlan
from meridian.quant.flagship_metrics import flagship_metrics
from meridian.quant.flagship_packet import FlagshipResearchPacket
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.flagship_replay import flagship_engine_hash
from meridian.quant.public_history import PublicHistoryReceipt
from meridian.quant.version import ENGINE_SOURCE_HASH


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    home = root / 'docs/quant-v23'
    manifest = json.loads((home / 'archive-manifest.json').read_text())
    path = home / 'synthetic-registry.zip'
    require(path.stat().st_size <= 20000000, 'V23_ARCHIVE_TOO_LARGE')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest['archive_hash'], 'V23_ARCHIVE_HASH')
    with zipfile.ZipFile(path) as zipped:
        require(len(zipped.namelist()) <= 256 and set(zipped.namelist()) == set(manifest['members']), 'V23_ARCHIVE_MEMBER_SET')
        require(sum(i.file_size for i in zipped.infolist()) <= 30000000, 'V23_ARCHIVE_EXPANSION_LIMIT')
        for name, digest in manifest['members'].items():
            require(hashlib.sha256(zipped.read(name)).hexdigest() == digest, 'V23_MEMBER_HASH:' + name)
        dataset = QuantDataset.model_validate_json(zipped.read('synthetic-dataset.json'))
        plan = FlagshipExperimentPlan.model_validate_json(zipped.read('plan.json'))
        summary = json.loads(zipped.read('summary.json'))
        require(dataset.evidence_status == 'SYNTHETIC_DIAGNOSTIC' and dataset.digest == plan.dataset_hash, 'V23_DATASET_STATUS')
        require(plan.engine_hash == flagship_engine_hash(), 'V23_SOURCE_ENGINE_DRIFT')
        require(summary == json.loads((home / 'synthetic-summary.json').read_text()), 'V23_SUMMARY_DRIFT')
        require(plan.stable_json() == FlagshipExperimentPlan.model_validate_json((home / 'predeclared-plan.json').read_text()).stable_json(), 'V23_PLAN_DRIFT')
        require(summary['evaluation_count'] == len(plan.variants) * len(plan.folds) * 2, 'V23_EVALUATION_COUNT')
        require(not summary['financial_alpha_demonstrated'], 'V23_SYNTHETIC_ALPHA_AUTHORITY')
        for row in summary['results']:
            require(row['status'] == 'REPLAY_COMPLETE', 'V23_BLOCKED_REPLAY:' + row['variant'])
            replay = ReplayResult.model_validate_json(zipped.read('replays/' + row['replay_hash'] + '.json'))
            expected = plan.engine_hash if replay.strategy.startswith('V23_') else ENGINE_SOURCE_HASH
            require(replay.engine_hash == expected and replay.dataset_hash == dataset.digest, 'V23_REPLAY_IDENTITY')
            require(row['metrics'] == flagship_metrics(replay), 'V23_METRICS_DRIFT')
            require(all(d.cash >= 0 and 0 <= d.exposure <= 1 for d in replay.days), 'V23_CASH_EXPOSURE')
            require(all(t.signal_at < t.execution_at for t in replay.trades), 'V23_EXECUTION_DELAY')
    packet = FlagshipResearchPacket.model_validate_json((home / 'golden-research-packet.json').read_text())
    require(packet.engine_hash == plan.engine_hash and packet.evidence_level == 'SYNTHETIC_DIAGNOSTIC' and not packet.authorized_trade, 'V23_PACKET_AUTHORITY')
    require(FlagshipPolicy.model_validate(yaml.safe_load((root / 'policies/quant-v23.yaml').read_text())) == FlagshipPolicy(), 'V23_POLICY_DRIFT')
    for name, model in [('policy', FlagshipPolicy), ('plan', FlagshipExperimentPlan), ('packet', FlagshipResearchPacket), ('public-history', PublicHistoryReceipt)]:
        require(json.loads((root / ('schemas/quant-v23-' + name + '.json')).read_text()) == model.model_json_schema(), 'V23_SCHEMA_DRIFT:' + name)
    public = json.loads((home / 'public-exploratory-summary.json').read_text())
    require(public['evidence_level'] == 'PUBLIC_EXPLORATORY' and not public['financial_alpha_demonstrated'], 'V23_PUBLIC_EVIDENCE')
    require(all(not r['financial_oos_eligible'] and r['historical_available_at'] is None for r in public['results']), 'V23_PUBLIC_CERTIFICATION')
    print(json.dumps({'status': 'PASS', 'evaluations': summary['evaluation_count'], 'engine_hash': plan.engine_hash,
        'canonical_runtime_written': False, 'financial_alpha_demonstrated': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
