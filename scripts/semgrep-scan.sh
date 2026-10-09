#!/usr/bin/env bash
# Scan a Juice Shop source tree with the pinned Semgrep rule.
# Usage: scripts/semgrep-scan.sh <source-dir> <output.json>
# Fails if the installed Semgrep version or the fetched rule differs from config/semgrep/rules.lock.json.
set -euo pipefail

SRC=${1:?source dir}
OUT=${2:?output json}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOCK="$ROOT/config/semgrep/rules.lock.json"
TARGET="$ROOT/config/targets/juice-shop.json"
SEMGREP=${SEMGREP:-semgrep}

want_version=$(jq -r '.semgrepVersion' "$LOCK")
have_version=$("$SEMGREP" --version)
if [[ "$have_version" != "$want_version" ]]; then
  echo "semgrep version mismatch: have $have_version, lock wants $want_version" >&2
  exit 2
fi

rules_dir=$(mktemp -d)
trap 'rm -rf "$rules_dir"' EXIT
rule_url=$(jq -r '.rules[0].url' "$LOCK")
rule_sha=$(jq -r '.rules[0].sha256' "$LOCK")
curl -sSfL "$rule_url" -o "$rules_dir/rule.yaml"
got_sha=$(shasum -a 256 "$rules_dir/rule.yaml" | cut -d' ' -f1)
if [[ "$got_sha" != "$rule_sha" ]]; then
  echo "rule content changed upstream: got $got_sha, lock wants $rule_sha" >&2
  exit 3
fi

path=$(jq -r '.allowed_paths[0]' "$TARGET")
# Exit code 0 = scan completed (with or without findings). Scanner errors are kept in the JSON.
(cd "$SRC" && SEMGREP_SEND_METRICS=off "$SEMGREP" scan --metrics=off --config "$rules_dir/rule.yaml" --json --quiet "$path") > "$OUT"
jq -c --arg rule "$(jq -r '.rules[0].id' "$LOCK")" '{
  rule: $rule,
  findings: [.results[] | select(.check_id | endswith($rule)) | {path, line: .start.line}],
  errors: (.errors | length),
  scanned: .paths.scanned
}' "$OUT"
