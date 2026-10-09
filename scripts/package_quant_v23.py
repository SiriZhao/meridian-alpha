"""Seal explicitly synthetic registry and sanitized public derived summaries."""
import argparse
import hashlib
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import yaml

from meridian.quant.backtest import QuantDataset
from meridian.quant.flagship_experiments import FlagshipExperimentPlan
from meridian.quant.flagship_packet import FlagshipResearchPacket, build_flagship_packet
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.integration import immutable_record
from meridian.quant.policy import CostPolicy
from meridian.quant.public_history import PublicHistoryReceipt
from meridian.trading_calendar import session_close


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--public-summary', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / 'docs/quant-v23'
    dataset = QuantDataset.model_validate_json((args.registry / 'synthetic-dataset.json').read_text())
    if dataset.evidence_status != 'SYNTHETIC_DIAGNOSTIC':
        raise ValueError('V23_PACKAGING_PRIVATE_OR_FINANCIAL_DATA_FORBIDDEN')
    plan = FlagshipExperimentPlan.model_validate_json((args.registry / 'plan.json').read_text())
    payloads = {p.relative_to(args.registry).as_posix(): p.read_bytes() for p in sorted(args.registry.rglob('*.json'))}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, payload in payloads.items():
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(entry, payload)
    blob = archive.getvalue()
    archive_path = destination / 'synthetic-registry.zip'
    if archive_path.exists() and archive_path.read_bytes() != blob:
        raise ValueError('V23_IMMUTABLE_ARCHIVE_EXISTS')
    archive_path.write_bytes(blob)
    for source, name in [('plan.json', 'predeclared-plan.json'), ('summary.json', 'synthetic-summary.json')]:
        immutable_record(destination / name, (args.registry / source).read_text())
    public = json.loads(args.public_summary.read_text())
    if public['evidence_level'] != 'PUBLIC_EXPLORATORY' or public['financial_alpha_demonstrated']:
        raise ValueError('V23_PUBLIC_SUMMARY_EVIDENCE_INVALID')
    immutable_record(destination / 'public-exploratory-summary.json', json.dumps(public, indent=2, sort_keys=True) + '\n')
    cutoff = session_close(plan.folds[0].validation_end)
    packet = build_flagship_packet({s.canonical_symbol: s for s in dataset.series}, cutoff,
        symbols=tuple(m.symbol for m in dataset.memberships), current={}, nav=Decimal('100000'),
        risk=plan.risk, policy=FlagshipPolicy(), costs=CostPolicy(), diagnostic=True,
        sector_map={m.symbol: m.sector for m in dataset.security_metadata},
        asset_types={m.symbol: m.asset_type for m in dataset.security_metadata})
    immutable_record(destination / 'golden-research-packet.json', packet.stable_json() + '\n')
    manifest = {'version': 'quant-v23-registry-manifest', 'archive_hash': hashlib.sha256(blob).hexdigest(),
        'engine_hash': plan.engine_hash, 'dataset_hash': dataset.digest,
        'members': {n: hashlib.sha256(b).hexdigest() for n, b in payloads.items()},
        'evidence_level': 'SYNTHETIC_DIAGNOSTIC', 'automatic_promotion': False}
    immutable_record(destination / 'archive-manifest.json', json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    immutable_record(root / 'policies/quant-v23.yaml', yaml.safe_dump(FlagshipPolicy().model_dump(mode='json'), sort_keys=True))
    for name, model in [('policy', FlagshipPolicy), ('plan', FlagshipExperimentPlan), ('packet', FlagshipResearchPacket), ('public-history', PublicHistoryReceipt)]:
        immutable_record(root / ('schemas/quant-v23-' + name + '.json'), json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + '\n')
    print(json.dumps({'archive_bytes': len(blob), 'members': len(payloads), 'engine_hash': plan.engine_hash}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
