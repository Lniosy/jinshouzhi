#!/usr/bin/env bash
# Check the host tools this repo's skills call, and install anything missing.
# Usage (from the repo root):
#   scripts/ensure-tools.sh                 # all profiles
#   scripts/ensure-tools.sh asc frida       # only these
#   ENSURE_CHECK_ONLY=1 scripts/ensure-tools.sh
#   scripts/ensure-tools.sh --check
# Profiles: python git strings asc jadx apktool frida all
# Installed files land in <repo>/.tools. Put <repo>/.tools/bin on PATH.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS="${TOOLS_DIR:-$REPO_ROOT/.tools}"
BIN="$TOOLS/bin"
ASC_ROOT="${ASC_ROOT:-$TOOLS/ASC}"
mkdir -p "$BIN"
export PATH="$BIN:${PATH:-}"
export HOMEBREW_NO_AUTO_UPDATE=1
export NONINTERACTIVE=1

CHECK_ONLY=0
if [[ "${ENSURE_CHECK_ONLY:-0}" == "1" ]]; then
  CHECK_ONLY=1
fi

PROFILES=()
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
    *) PROFILES+=("$arg") ;;
  esac
done
if [[ "${#PROFILES[@]}" -eq 0 ]]; then
  PROFILES=(all)
fi

FAIL=0
ok() { printf '[ok] %s\n' "$*"; }
installing() { printf '[install] %s\n' "$*"; }
skip() { printf '[skip] %s\n' "$*"; }
miss() { printf '[missing] %s\n' "$*" >&2; FAIL=1; }
die() { printf '[fail] %s\n' "$*" >&2; FAIL=1; }

have() { command -v "$1" >/dev/null 2>&1; }

# ASC and frida-tools need 3.11+. macOS /usr/bin/python3 is often 3.9.
pick_py311() {
  local c
  for c in python3.13 python3.12 python3.11 python3; do
    if have "$c" && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

ensure_py311() {
  local bin prefix
  if bin="$(pick_py311)"; then
    PY311="$bin"
    ok "python $($bin -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "python >= 3.11"
    return 0
  fi
  if ! have brew; then
    die "python >= 3.11 missing; install Python 3.11+ and re-run"
    return 0
  fi
  installing "python@3.13 via brew"
  brew install python@3.13 || { die "brew install python@3.13 failed"; return 0; }
  prefix="$(brew --prefix python@3.13 2>/dev/null || true)"
  if [[ -n "$prefix" && -x "$prefix/bin/python3.13" ]]; then
    PY311="$prefix/bin/python3.13"
  elif bin="$(pick_py311)"; then
    PY311="$bin"
  else
    die "python >= 3.11 still missing"
    return 0
  fi
  ok "python $($PY311 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
}

java_ok() {
  have java || return 1
  java -version >/dev/null 2>&1
}

prepend_brew_java() {
  have brew || return 0
  local prefix
  prefix="$(brew --prefix openjdk 2>/dev/null || true)"
  if [[ -n "$prefix" && -x "$prefix/bin/java" ]]; then
    export PATH="$prefix/bin:$PATH"
  fi
}

os_name() {
  case "$(uname -s)" in
    Darwin) echo darwin ;;
    Linux) echo linux ;;
    *) echo other ;;
  esac
}

arch_name() {
  case "$(uname -m)" in
    arm64|aarch64) echo aarch64 ;;
    x86_64|amd64) echo x86_64 ;;
    *) uname -m ;;
  esac
}

fetch() {
  curl -fL --retry 3 --retry-delay 2 -o "$2" "$1"
}

github_asset() {
  # github_asset owner repo suffix-or-substring
  local owner="$1" repo="$2" needle="$3"
  python3 - "$owner" "$repo" "$needle" <<'PY'
import json, sys, urllib.request
owner, repo, needle = sys.argv[1:]
url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ensure-tools"})
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
for asset in data.get("assets", []):
    name = asset.get("name") or ""
    if needle in name:
        print(asset["browser_download_url"])
        raise SystemExit(0)
raise SystemExit(1)
PY
}

ensure_python() {
  if have python3; then
    ok "python3 $(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "python3"
    return 0
  fi
  installing "python3"
  if have brew; then
    brew install python || { die "brew install python failed"; return 0; }
  else
    die "python3 missing; install Python 3.11+ and re-run"
    return 0
  fi
  have python3 && ok "python3" || die "python3 still missing"
}

ensure_git() {
  if have git; then
    ok "git"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "git"
    return 0
  fi
  installing "git"
  if have brew; then
    brew install git || { die "brew install git failed"; return 0; }
  else
    die "git missing"
    return 0
  fi
  have git && ok "git" || die "git still missing"
}

ensure_java() {
  prepend_brew_java
  if java_ok; then
    ok "java"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "java"
    return 0
  fi
  if ! have brew; then
    die "java missing; install a JDK and re-run"
    return 0
  fi
  installing "openjdk via brew"
  brew install openjdk || { die "brew install openjdk failed"; return 0; }
  prepend_brew_java
  if java_ok; then
    ok "java"
  else
    die "java still missing after openjdk install; add \$(brew --prefix openjdk)/bin to PATH"
  fi
}

ensure_strings() {
  if have strings && have file; then
    ok "strings file"
  else
    miss "strings/file (expected from the system)"
  fi
  if have rg; then
    ok "rg"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "rg"
    return 0
  fi
  if have brew; then
    installing "ripgrep via brew"
    brew install ripgrep || { die "brew install ripgrep failed"; return 0; }
    hash -r || true
    have rg && ok "rg" || die "rg still missing"
    return 0
  fi
  installing "ripgrep from GitHub"
  local os arch url tmp
  os="$(os_name)"
  arch="$(arch_name)"
  if [[ "$os" == "other" ]]; then
    die "rg missing and no Homebrew; install ripgrep manually"
    return 0
  fi
  url="$(github_asset BurntSushi ripgrep "${arch}-apple-${os}" 2>/dev/null || true)"
  if [[ "$os" == "linux" ]]; then
    url="$(github_asset BurntSushi ripgrep "${arch}-unknown-linux-musl" 2>/dev/null || true)"
  fi
  if [[ -z "$url" ]]; then
    die "could not resolve a ripgrep release asset"
    return 0
  fi
  tmp="$(mktemp -d)"
  fetch "$url" "$tmp/rg.tgz" || { die "download ripgrep failed"; rm -rf "$tmp"; return 0; }
  tar -xzf "$tmp/rg.tgz" -C "$tmp" || { die "unpack ripgrep failed"; rm -rf "$tmp"; return 0; }
  local bin
  bin="$(find "$tmp" -type f -name rg -print -quit)"
  if [[ -z "$bin" ]]; then
    die "rg binary not in the release archive"
    rm -rf "$tmp"
    return 0
  fi
  install -m 755 "$bin" "$BIN/rg"
  rm -rf "$tmp"
  ok "rg"
}

ensure_asc() {
  ensure_py311
  ensure_git
  if [[ -z "${PY311:-}" ]]; then
    return 0
  fi
  local py="$ASC_ROOT/.venv/bin/python"
  local main="$ASC_ROOT/main.py"
  if [[ -x "$py" && -f "$main" ]] && "$py" -c 'import androguard' >/dev/null 2>&1; then
    ok "asc $ASC_ROOT"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "asc ($ASC_ROOT)"
    return 0
  fi
  if [[ ! -f "$main" ]]; then
    installing "ASC clone into $ASC_ROOT"
    rm -rf "$ASC_ROOT"
    git clone --depth 1 https://github.com/MG1937/ASC.git "$ASC_ROOT" || { die "git clone ASC failed"; return 0; }
  fi
  if [[ ! -x "$py" ]]; then
    installing "ASC venv"
    "$PY311" -m venv "$ASC_ROOT/.venv" || { die "python venv for ASC failed"; return 0; }
  fi
  installing "ASC requirements"
  "$ASC_ROOT/.venv/bin/pip" install -r "$ASC_ROOT/requirements.txt" || { die "pip install ASC requirements failed"; return 0; }
  if "$py" -c 'import androguard' >/dev/null 2>&1; then
    ok "asc $ASC_ROOT"
  else
    die "ASC installed but androguard cannot be imported"
  fi
}

install_jadx_zip() {
  local url tmp
  url="$(python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    "https://api.github.com/repos/skylot/jadx/releases/latest",
    headers={"Accept": "application/vnd.github+json", "User-Agent": "ensure-tools"},
)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
names = []
for asset in data.get("assets", []):
    name = asset.get("name") or ""
    if name.startswith("jadx-") and name.endswith(".zip") and "gui" not in name:
        print(asset["browser_download_url"])
        raise SystemExit
raise SystemExit(1)
PY
)" || { die "could not resolve a jadx release"; return 0; }
  tmp="$(mktemp -d)"
  fetch "$url" "$tmp/jadx.zip" || { die "download jadx failed"; rm -rf "$tmp"; return 0; }
  rm -rf "$TOOLS/jadx"
  mkdir -p "$TOOLS/jadx"
  unzip -q "$tmp/jadx.zip" -d "$TOOLS/jadx" || { die "unzip jadx failed"; rm -rf "$tmp"; return 0; }
  rm -rf "$tmp"
  ln -sfn "$TOOLS/jadx/bin/jadx" "$BIN/jadx"
  if [[ -x "$TOOLS/jadx/bin/jadx-gui" ]]; then
    ln -sfn "$TOOLS/jadx/bin/jadx-gui" "$BIN/jadx-gui"
  fi
  ok "jadx"
}

ensure_jadx() {
  if have jadx; then
    ok "jadx"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "jadx"
    return 0
  fi
  ensure_java
  if have brew; then
    installing "jadx via brew"
    if brew install jadx; then
      hash -r || true
      have jadx && { ok "jadx"; return 0; }
    fi
  fi
  installing "jadx from GitHub"
  install_jadx_zip
}

install_apktool_jar() {
  local url tmp
  url="$(python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    "https://api.github.com/repos/iBotPeaches/Apktool/releases/latest",
    headers={"Accept": "application/vnd.github+json", "User-Agent": "ensure-tools"},
)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
for asset in data.get("assets", []):
    name = asset.get("name") or ""
    if name.startswith("apktool_") and name.endswith(".jar"):
        print(asset["browser_download_url"])
        raise SystemExit
raise SystemExit(1)
PY
)" || { die "could not resolve an apktool jar"; return 0; }
  tmp="$(mktemp -d)"
  fetch "$url" "$tmp/apktool.jar" || { die "download apktool failed"; rm -rf "$tmp"; return 0; }
  mkdir -p "$TOOLS/apktool"
  mv "$tmp/apktool.jar" "$TOOLS/apktool/apktool.jar"
  rm -rf "$tmp"
  cat > "$BIN/apktool" <<EOF
#!/bin/sh
exec java -jar "$TOOLS/apktool/apktool.jar" "\$@"
EOF
  chmod +x "$BIN/apktool"
  ok "apktool"
}

ensure_apktool() {
  if have apktool; then
    ok "apktool"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "apktool"
    return 0
  fi
  ensure_java
  if have brew; then
    installing "apktool via brew"
    if brew install apktool; then
      hash -r || true
      have apktool && { ok "apktool"; return 0; }
    fi
  fi
  installing "apktool from GitHub"
  install_apktool_jar
}

ensure_adb() {
  if have adb; then
    ok "adb"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "adb"
    return 0
  fi
  if have brew; then
    installing "android-platform-tools via brew"
    if brew install android-platform-tools; then
      hash -r || true
      have adb && { ok "adb"; return 0; }
    fi
  fi
  local os url tmp
  os="$(os_name)"
  case "$os" in
    darwin) url="https://dl.google.com/android/repository/platform-tools-latest-darwin.zip" ;;
    linux) url="https://dl.google.com/android/repository/platform-tools-latest-linux.zip" ;;
    *) die "adb missing; install Android platform-tools"; return 0 ;;
  esac
  installing "platform-tools"
  tmp="$(mktemp -d)"
  fetch "$url" "$tmp/pt.zip" || { die "download platform-tools failed"; rm -rf "$tmp"; return 0; }
  rm -rf "$TOOLS/platform-tools"
  unzip -q "$tmp/pt.zip" -d "$TOOLS" || { die "unzip platform-tools failed"; rm -rf "$tmp"; return 0; }
  rm -rf "$tmp"
  ln -sfn "$TOOLS/platform-tools/adb" "$BIN/adb"
  have adb && ok "adb" || die "adb still missing"
}

frida_host_ok() {
  have frida && frida --version >/dev/null 2>&1
}

install_frida_venv() {
  ensure_py311
  if [[ -z "${PY311:-}" ]]; then
    return 0
  fi
  local py="$TOOLS/py/bin/python"
  if [[ ! -x "$py" ]]; then
    "$PY311" -m venv "$TOOLS/py" || { die "venv for frida-tools failed"; return 0; }
  fi
  installing "frida-tools into $TOOLS/py"
  "$TOOLS/py/bin/pip" install -U frida-tools || { die "pip install frida-tools failed"; return 0; }
  ln -sfn "$TOOLS/py/bin/frida" "$BIN/frida"
  ln -sfn "$TOOLS/py/bin/frida-ps" "$BIN/frida-ps"
  ln -sfn "$TOOLS/py/bin/frida-ls-devices" "$BIN/frida-ls-devices" 2>/dev/null || true
  hash -r || true
}

android_frida_arch() {
  case "$1" in
    arm64-v8a) echo android-arm64 ;;
    armeabi-v7a) echo android-arm ;;
    x86_64) echo android-x86_64 ;;
    x86) echo android-x86 ;;
    *) echo "" ;;
  esac
}

ensure_frida_server() {
  local adb=(adb)
  [[ -n "${SERIAL:-}" ]] && adb=(adb -s "$SERIAL")
  if ! "${adb[@]}" get-state >/dev/null 2>&1; then
    skip "frida-server (no adb device)"
    return 0
  fi
  local state
  state="$("${adb[@]}" get-state 2>/dev/null | tr -d '\r' || true)"
  if [[ "$state" != "device" ]]; then
    skip "frida-server (adb state: ${state:-unknown})"
    return 0
  fi
  local ver abi arch name
  ver="$(frida --version | tr -d '[:space:]')"
  abi="$("${adb[@]}" shell getprop ro.product.cpu.abi | tr -d '\r')"
  arch="$(android_frida_arch "$abi")"
  if [[ -z "$arch" ]]; then
    die "unknown device abi: $abi"
    return 0
  fi
  name="frida-server-${ver}-${arch}"
  if "${adb[@]}" shell "ls /data/local/tmp/${name} /data/local/tmp/frida-server-${ver} /data/local/tmp/frida-server" 2>/dev/null | tr -d '\r' | grep -q .; then
    ok "frida-server on device"
    return 0
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then
    miss "frida-server ${ver} for ${abi}"
    return 0
  fi
  installing "frida-server ${ver} (${arch})"
  local url="$TOOLS/frida-server/${name}"
  mkdir -p "$TOOLS/frida-server"
  local xz="$TOOLS/frida-server/${name}.xz"
  if [[ ! -x "$url" ]]; then
    fetch "https://github.com/frida/frida/releases/download/${ver}/${name}.xz" "$xz" || { die "download frida-server failed"; return 0; }
    python3 - "$xz" "$url" <<'PY' || { die "decompress frida-server failed"; return 0; }
import lzma, sys
src, dst = sys.argv[1:]
with lzma.open(src) as inf, open(dst, "wb") as out:
    out.write(inf.read())
PY
    chmod +x "$url"
    rm -f "$xz"
  fi
  "${adb[@]}" push "$url" "/data/local/tmp/${name}" || { die "adb push frida-server failed"; return 0; }
  "${adb[@]}" shell "chmod 755 /data/local/tmp/${name}" >/dev/null 2>&1 || \
    "${adb[@]}" shell "su -c 'chmod 755 /data/local/tmp/${name}'" >/dev/null 2>&1 || true
  ok "frida-server pushed /data/local/tmp/${name}"
}

ensure_frida() {
  ensure_adb
  if frida_host_ok; then
    ok "frida $(frida --version | tr -d '[:space:]')"
  elif [[ "$CHECK_ONLY" == "1" ]]; then
    miss "frida"
  else
    install_frida_venv
    if frida_host_ok; then
      ok "frida $(frida --version | tr -d '[:space:]')"
    else
      die "frida still missing"
    fi
  fi
  if frida_host_ok; then
    ensure_frida_server
  fi
}

run_profile() {
  case "$1" in
    python) ensure_python ;;
    git) ensure_git ;;
    strings) ensure_strings ;;
    asc) ensure_asc ;;
    jadx) ensure_jadx ;;
    apktool) ensure_apktool ;;
    frida) ensure_frida ;;
    all)
      ensure_python
      ensure_git
      ensure_strings
      ensure_asc
      ensure_jadx
      ensure_apktool
      ensure_frida
      ;;
    *)
      die "unknown profile: $1"
      ;;
  esac
}

for profile in "${PROFILES[@]}"; do
  run_profile "$profile"
done

printf '[path] %s\n' "$BIN"
if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
