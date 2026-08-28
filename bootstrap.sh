#!/bin/sh
# LIN cold-start seed (Node-free entrypoint).
#
# The repo tracks only .lin + .rulel files (see spec/LIN_CORE_ARCH.rulel,
# AGENTS_md.rulel). Executable host glue (.mjs, package.json, ...) is
# materialized at bootstrap time from TRANSPOSED_SOURCE .rulel mirrors.
#
# Problem this solves: something has to perform that very first
# extraction, and it cannot itself be one of the files it extracts. This
# script is the sole tracked host-exception that does that — written in
# POSIX sh + awk (no Node, no Python) so the *first* step of getting the
# project running requires zero JS runtime. Node is only invoked starting
# from bootstrap_cold_start.mjs, which today still hosts the LIN
# compiler/verifier/test-runner (see R_BOOT=js_compiler_is_bootstrap in
# spec/LIN_CORE_ARCH.rulel — this is a phase marker, not the end state).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Extracts the .source{content="..."} JSON-escaped payload of a
# TRANSPOSED_SOURCE .rulel file to stdout, unescaped.
extract_rulel() {
  awk '
    BEGIN { insrc = 0; out = "" }
    {
      line = $0
      if (!insrc) {
        idx = index(line, ".source{content=\"")
        if (idx == 0) next
        line = substr(line, idx + length(".source{content=\""))
        insrc = 1
      }
      i = 1
      n = length(line)
      while (i <= n) {
        c = substr(line, i, 1)
        if (c == "\\") {
          nx = substr(line, i + 1, 1)
          if (nx == "n") { out = out "\n" }
          else if (nx == "t") { out = out "\t" }
          else if (nx == "r") { out = out "\r" }
          else if (nx == "\"") { out = out "\"" }
          else if (nx == "\\") { out = out "\\" }
          else { out = out nx }
          i += 2
        } else if (c == "\"") {
          printf "%s", out
          exit
        } else {
          out = out c
          i += 1
        }
      }
    }
  ' "$1"
}

seed() {
  rulel="$1"
  outpath="$2"
  [ -f "$outpath" ] && return 0
  mkdir -p "$(dirname "$outpath")"
  extract_rulel "$rulel" > "$outpath"
}

seed package_json.rulel package.json
seed bootstrap_cold_start.rulel bootstrap_cold_start.mjs

exec node bootstrap_cold_start.mjs "$@"
