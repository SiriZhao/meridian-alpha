"""Generate/check additive V2.2 schemas; never replaces V2.1 schemas."""

import argparse
import json
from pathlib import Path

from meridian.quant.contracts import ExpectedReturnEstimate, FundamentalObservation
from meridian.quant.experiments import ChallengerExperimentPlan
from meridian.quant.features import ChallengerFeatureSnapshot
from meridian.quant.packet import QuantResearchPacketV22
from meridian.quant.policy import ChallengerPolicy
from meridian.quant.signals import ChallengerScore

MODELS = {"quant-v22-policy.schema.json": ChallengerPolicy, "quant-v22-features.schema.json": ChallengerFeatureSnapshot,
          "quant-v22-score.schema.json": ChallengerScore, "quant-v22-plan.schema.json": ChallengerExperimentPlan,
          "quant-research-packet.v22.schema.json": QuantResearchPacketV22,
          "quant-expected-return.v1.schema.json": ExpectedReturnEstimate,
          "quant-fundamental-observation.v1.schema.json": FundamentalObservation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    for filename, model in MODELS.items():
        schema = model.model_json_schema()
        schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
                       "$id": "https://meridian-alpha.local/schemas/" + filename})
        target = root / "schemas" / filename
        if args.check:
            if json.loads(target.read_text(encoding="utf-8")) != schema:
                raise ValueError("V22_SCHEMA_DRIFT:" + filename)
        else:
            target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print("V2.2 seven contracts PASS" if args.check else "Generated seven additive V2.2 contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
