#!/usr/bin/env bash
# Quick string pre-screen for VIP / license / card-key logic in a local sample.
# Usage: hunt_license_strings.sh <file-or-dir> [out.txt]

set -euo pipefail

TARGET="${1:-}"
OUT="${2:-}"

if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 <file-or-dir> [out.txt]" >&2
  exit 1
fi

if [[ ! -e "$TARGET" ]]; then
  echo "Not found: $TARGET" >&2
  exit 1
fi

PATTERN='vip|VIP|isVip|is_vip|premium|Premium|member|Member|license|License|serial|Serial|activat|Activ|expire|Expire|trial|Trial|卡密|激活|会员|授权|开通|试用|到期|paywall|unlock|Unlock'

run_strings() {
  local f="$1"
  if command -v strings >/dev/null 2>&1; then
    strings -a -n 4 "$f" 2>/dev/null || true
  else
    # fallback: printable runs
    LC_ALL=C grep -aobE '[[:print:]]{4,}' "$f" 2>/dev/null | head -c 5000000 || true
  fi
}

scan_one() {
  local f="$1"
  echo "===== $f ====="
  file "$f" 2>/dev/null || true
  run_strings "$f" | rg -i --color=never "$PATTERN" | sort -u | head -n 400
  echo
}

{
  echo "# vip-license-re string hunt"
  echo "# target: $TARGET"
  echo "# date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  if [[ -f "$TARGET" ]]; then
    scan_one "$TARGET"
  else
    # common nested binaries
    while IFS= read -r -d '' f; do
      scan_one "$f"
    done < <(find "$TARGET" -type f \( \
      -name '*.so' -o -name '*.dll' -o -name '*.exe' -o -name '*.dex' \
      -o -name '*.bin' -o -name 'lib*.so' -o -name '*.asar' \
      \) -print0 2>/dev/null | head -z -n 80)
  fi
} | if [[ -n "$OUT" ]]; then
  tee "$OUT"
  echo "[+] wrote $OUT" >&2
else
  cat
fi
