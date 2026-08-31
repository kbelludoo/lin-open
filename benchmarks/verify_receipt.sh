#!/usr/bin/env bash
# ============================================================================
# Independent LIN compute-receipt verifier — Bash + OpenSSL (no LIN binary).
#
# Zero-trust: recomputes the receipt Merkle root using only standard tools
# (openssl dgst -sha256, or sha256sum as fallback) and compares it to the
# claimed root. Works on any Linux/macOS machine with bash + openssl.
#
# Open receipt format (LIN_COMPUTE_RECEIPT_1.0):
#   leaf[0:32]  = SHA-256(source code)              ("artifact")
#   leaf[32:40] = output   (i64, little-endian)
#   leaf[40:48] = steps    (u64, little-endian)
#   leaf[48:56] = sp_at_ret (u64, little-endian)
#   leaf[56:64] = input    (i64, little-endian)
#   merkle_root = SHA-256(leaf)
#
# Usage:
#   ./verify_receipt.sh receipt.json
#   ./verify_receipt.sh receipt.rulel
#   ./verify_receipt.sh receipt.json "return x * x;"   # optional source check
# Exit code: 0 = PASS, 1 = FAIL.
# ============================================================================
set -u

RECEIPT="${1:?usage: verify_receipt.sh <receipt.json|receipt.rulel> [source-code]}"
SRC="${2:-}"

if [ ! -f "$RECEIPT" ]; then
  echo "[FAIL] cannot open receipt: $RECEIPT" >&2
  exit 1
fi

# --- extract a field from JSON ("key": "value" or "key": value) ----------
json_val() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p" "$RECEIPT" | head -n1
}
# --- extract a field from RULEL (.k="value" or .k=value) ------------------
rulel_val() {
  sed -n "s/^\.$1=\(.*\)$/\1/p" "$RECEIPT" | head -n1 | tr -d '"'
}

if head -c1 "$RECEIPT" | grep -q '{'; then
  ART=$(json_val artifact)
  INP=$(json_val input)
  OUT=$(json_val output)
  STEPS=$(json_val steps)
  SP=$(json_val sp_at_ret)
  MERKLE=$(json_val merkle_root)
else
  ART=$(rulel_val a)
  INP=$(rulel_val i)
  OUT=$(rulel_val o)
  STEPS=$(rulel_val s)
  SP=$(rulel_val p)
  MERKLE=$(rulel_val m)
fi

for f in "$ART" "$INP" "$OUT" "$STEPS" "$SP" "$MERKLE"; do
  [ -n "$f" ] || { echo "[FAIL] receipt is missing required fields" >&2; exit 1; }
done

ART_HEX=${ART#sha256:}
MERKLE_HEX=${MERKLE#sha256:}
[ "${#ART_HEX}" -eq 64 ] || { echo "[FAIL] artifact is not a 64-char SHA-256 hex digest" >&2; exit 1; }
[ "${#MERKLE_HEX}" -eq 64 ] || { echo "[FAIL] merkle_root is not a 64-char SHA-256 hex digest" >&2; exit 1; }

# --- little helpers --------------------------------------------------------
hex_to_bytes() { # hex string -> raw bytes on stdout
  local h="$1" i
  for (( i = 0; i < ${#h}; i += 2 )); do
    printf "\\x${h:i:2}"
  done
}
put_le64() { # signed 64-bit int -> 8 raw bytes little-endian on stdout
  local v="$1" i byte
  for (( i = 0; i < 8; i++ )); do
    byte=$(( (v >> (8 * i)) & 255 ))
    printf "\\$(printf '%03o' "$byte")"
  done
}
sha256_hex() { # file -> hex digest (openssl preferred, sha256sum fallback)
  if command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" 2>/dev/null | awk '{print $NF}'
  else
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
  fi
}

TMPDIR_V=$(mktemp -d) || exit 1
trap 'rm -rf "$TMPDIR_V"' EXIT
LEAF="$TMPDIR_V/leaf.bin"

{
  hex_to_bytes "$ART_HEX"
  put_le64 "$OUT"
  put_le64 "$STEPS"
  put_le64 "$SP"
  put_le64 "$INP"
} > "$LEAF"

COMPUTED=$(sha256_hex "$LEAF")

echo "========================================================================="
echo "   INDEPENDENT LIN RECEIPT VERIFIER (BASH + OPENSSL)"
echo "========================================================================="
echo "  Artifact     : sha256:$ART_HEX"
echo "  Input        : $INP"
echo "  Output       : $OUT"
echo "  Steps        : $STEPS"
echo "  SP at ret    : $SP"
echo "  Merkle (file): sha256:$MERKLE_HEX"
echo "  Merkle (calc): sha256:$COMPUTED"

OK=0
if [ -n "$SRC" ]; then
  if command -v openssl >/dev/null 2>&1; then
    SRC_HASH=$(printf '%s' "$SRC" | openssl dgst -sha256 2>/dev/null | awk '{print $NF}')
  else
    SRC_HASH=$(printf '%s' "$SRC" | sha256sum | awk '{print $1}')
  fi
  if [ "$SRC_HASH" = "$ART_HEX" ]; then
    echo "  Source check : PASS (artifact matches source)"
  else
    echo "  Source check : FAIL (artifact != SHA-256(source))"
    OK=1
  fi
fi

if [ "$COMPUTED" = "$MERKLE_HEX" ] && [ "$OK" = 0 ]; then
  echo "  [PASS] Receipt validated by an independent open-source verifier"
  echo "========================================================================="
  exit 0
else
  echo "  [FAIL] Receipt forged or tampered! calculated=$COMPUTED claimed=$MERKLE_HEX"
  echo "========================================================================="
  exit 1
fi
