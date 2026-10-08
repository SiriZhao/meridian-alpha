"""Read-only public-ref audit. Never print a matching value or full blob."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "HIGH_RISK_TOKEN": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|sk-[A-Za-z0-9_-]{30,})"),
    "PRIVATE_KEY_HEADER": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "PERSONAL_ABSOLUTE_PATH": re.compile(rb"[A-Za-z]:[\\/]Users[\\/][^\\/\r\n\"']+", re.IGNORECASE),
    "RAW_ACCOUNT_FIELD": re.compile(rb'"(?:account_number|accountNumber|account_hash)"\s*:\s*"[^"\r\n]{6,}"'),
}


def audit(root: Path) -> dict[str, object]:
    listed = subprocess.run(["git", "rev-list", "--objects", "--remotes=origin"], cwd=root, check=True, capture_output=True).stdout.splitlines()
    objects = [line.partition(b" ")[0] for line in listed]
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("HISTORY_AUDIT_PIPE_UNAVAILABLE")
    findings = []
    blobs = 0
    try:
        for oid in objects:
            process.stdin.write(oid + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3:
                raise ValueError("HISTORY_AUDIT_OBJECT_UNAVAILABLE")
            size = int(header[2])
            content = process.stdout.read(size)
            if len(content) != size or process.stdout.read(1) != b"\n":
                raise ValueError("HISTORY_AUDIT_OBJECT_TRUNCATED")
            if header[1] != b"blob":
                continue
            blobs += 1
            for category, pattern in PATTERNS.items():
                matches = pattern.findall(content)
                if matches:
                    findings.append({"object_id": oid.decode("ascii"), "category": category,
                                     "count": len(matches), "fingerprint": hashlib.sha256(matches[0]).hexdigest()[:16]})
    finally:
        process.stdin.close()
        process.stdout.close()
        process.wait(timeout=30)
    return {"schema_version": "meridian-public-history-audit.v1", "scope": "ALL_FETCHED_ORIGIN_REFS",
            "objects_scanned": len(objects), "blobs_scanned": blobs, "findings": findings,
            "status": "REVIEW_REQUIRED" if findings else "NO_PATTERN_FINDINGS",
            "limitations": "Pattern scan cannot prove absence of all secrets; no credential-store access or history mutation."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "findings"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
