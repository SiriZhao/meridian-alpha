"""Read-only launcher preflight; no probes, providers, model calls or ledger writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from meridian.config import load_policies
from meridian.live_readiness import environment_identity
from meridian.runtime import RuntimePaths, policy_directory


def launch_identity(expected_root: Path) -> dict:
    root = expected_root.resolve()
    identity = environment_identity()
    reasons = []
    if sys.version_info[:2] != (3, 12):
        reasons.append('PROJECT_PYTHON_3_12_REQUIRED')
    if Path(sys.prefix).resolve() != root / '.venv':
        reasons.append('WRONG_PROJECT_VIRTUAL_ENVIRONMENT')
    if not Path(str(identity['package_origin'])).resolve().is_relative_to(root / 'src'):
        reasons.append('WRONG_PACKAGE_ORIGIN')
    if policy_directory().resolve() != root / 'policies':
        reasons.append('WRONG_POLICY_DIRECTORY')
    policies = load_policies(policy_directory())
    model = policies.models.research
    paths = RuntimePaths.from_environment()
    return {'schema_version': 'meridian-launch-identity.v1',
            'status': 'BLOCKED' if reasons else 'PASS', 'blockers': reasons,
            'environment': identity, 'runtime': paths.as_dict(),
            'challenger_mode': 'V2.3_SHADOW', 'canonical_mode': 'QUANT_V1_BASELINE',
            'model': {'provider': model.provider, 'name': model.model,
                      'reasoning_effort': model.reasoning_effort} if model else None,
            'model_inference_actually_run': False, 'broker_submission': 'DISABLED',
            'runtime_written': False,
            'message_zh': '仅核对代码、解释器和配置；未探测写权限、运行模型或创建 Paper 日。'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-root', type=Path, required=True)
    args = parser.parse_args()
    result = launch_identity(args.expected_root)
    print(json.dumps(result, ensure_ascii=False))
    return 3 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
