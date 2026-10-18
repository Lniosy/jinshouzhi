#!/usr/bin/env python3
"""One-pass login/register surface scan.

Usage:
  analyze_auth.py <sample-or-har-or-dir> [out-dir]

Writes endpoints.txt, hits.txt, and REPORT.md.
Password, token, and code values are redacted. Field names stay.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AUTH_RE = re.compile(
    r"(login|logon|log_in|signin|sign-in|sign_in|signup|sign-up|sign_up|"
    r"register|regist|oauth|token|refresh|logout|signout|"
    r"sms|sendcode|send_code|verifycode|verify_code|captcha|"
    r"password|passwd|/auth/|account/login|"
    r"登录|注册|验证码|密码)",
    re.I,
)
URL_RE = re.compile(rb"https?://[^\s\"'<>\\\x00-\x1f]{8,240}", re.I)
PATH_RE = re.compile(
    rb"(?:/[A-Za-z0-9._~+-]+){1,8}"
    rb"(?:login|logon|signin|sign-in|signup|sign-up|register|oauth|token|"
    rb"refresh|logout|sms|captcha|password|auth)[A-Za-z0-9._~+-]*",
    re.I,
)
KEEP_RE = re.compile(
    r"https?://|"
    r"/[\w./-]*(?:login|logon|signin|sign-in|signup|sign-up|register|oauth|token|sms|captcha|password)|"
    r"登录|注册|验证码|密码",
    re.I,
)
LINE_SECRET = re.compile(
    r"(?i)(?<![A-Za-z])(password|passwd|pwd|token|authorization|secret|otp|code)(?![A-Za-z])"
    r"(\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,}&]+)"
)

SECRET_KEY = re.compile(
    r"(password|passwd|pwd|token|authorization|secret|otp|smscode|sms_code|"
    r"verifycode|verify_code|code|credential)",
    re.I,
)
TEXT_SUFFIX = {
    ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".html", ".htm",
    ".json", ".har", ".xml", ".txt", ".md", ".smali", ".java", ".kt",
    ".cs", ".py", ".php", ".go", ".swift", ".m", ".mm", ".dart",
}
BIN_SUFFIX = {
    ".apk", ".aab", ".ipa", ".exe", ".dll", ".so", ".dylib", ".dex",
    ".bin", ".asar", ".node", ".pyc",
}
SKIP_DIR = {".git", ".tools", "node_modules", ".venv", "venv", "__pycache__"}
MAX_FILE = 8 * 1024 * 1024
MAX_BODY = 2000


def redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if isinstance(key, str) and SECRET_KEY.search(key) and not isinstance(item, (dict, list)):
                out[key] = "<redacted>"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > MAX_BODY:
        return value[:MAX_BODY] + "...<trimmed>"
    return value


def interesting(text: str) -> bool:
    return bool(AUTH_RE.search(text))


def redact_line(text: str) -> str:
    return LINE_SECRET.sub(r"\1\2<redacted>", text)


def from_bytes(blob: bytes) -> list[str]:
    found = []
    for match in URL_RE.findall(blob):
        text = match.decode("utf-8", "replace").rstrip(".,);]")
        if interesting(text):
            found.append(text)
    urls = [item for item in found if item.startswith("http")]
    for match in PATH_RE.findall(blob):
        text = match.decode("utf-8", "replace")
        if interesting(text) and not any(text in url for url in urls):
            found.append(text)
    if any(word.encode() in blob for word in ("登录", "注册", "验证码", "密码")):
        text = blob.decode("utf-8", "replace")
        for line in re.split(r"[\x00-\x1f]+", text):
            line = line.strip()
            if line and len(line) <= 300 and KEEP_RE.search(line):
                found.append(redact_line(line))
    return found


def scan_file(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".har" or path.name.lower().endswith(".har"):
            return har_endpoints(path)
        if suffix in TEXT_SUFFIX or suffix == "":
            data = path.read_bytes()[:MAX_FILE]
            if b"\x00" in data[:512] and suffix not in BIN_SUFFIX:
                return from_bytes(data)
            text = data.decode("utf-8", "replace")
            hits = []
            for line in text.splitlines():
                line = line.strip()
                if line and KEEP_RE.search(line):
                    hits.append(redact_line(line[:500]))
            hits.extend(from_bytes(data))
            return hits
        data = path.read_bytes()[:MAX_FILE]
        return from_bytes(data)
    except OSError as exc:
        return ["<unreadable %s: %s>" % (path, exc)]


def walk(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    files = []
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR for part in path.parts):
            continue
        if path.stat().st_size > 80 * 1024 * 1024:
            continue
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIX or suffix in BIN_SUFFIX or suffix in {".apk", ".hap", ".wpk"}:
            files.append(path)
    return files


def header_map(headers) -> dict:
    out = {}
    for item in headers or []:
        name = str(item.get("name", ""))
        value = str(item.get("value", ""))
        if SECRET_KEY.search(name):
            value = "<redacted>"
        out[name] = value
    return out


def body_text(post):
    if not post:
        return ""
    text = post.get("text") or ""
    mime = (post.get("mimeType") or "").lower()
    if "json" in mime:
        try:
            return json.dumps(redact(json.loads(text)), ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    if SECRET_KEY.search(text):
        return "<redacted body containing secret-like fields>"
    if len(text) > MAX_BODY:
        return text[:MAX_BODY] + "...<trimmed>"
    return text


def har_endpoints(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return from_bytes(path.read_bytes()[:MAX_FILE])
    entries = (((data.get("log") or {}).get("entries")) or [])
    lines = []
    for entry in entries:
        req = entry.get("request") or {}
        url = str(req.get("url") or "")
        if not interesting(url) and not interesting(json.dumps(req.get("postData") or {}, ensure_ascii=False)):
            continue
        res = entry.get("response") or {}
        block = {
            "method": req.get("method"),
            "url": url,
            "status": res.get("status"),
            "headers": header_map(req.get("headers")),
            "body": body_text(req.get("postData")),
        }
        lines.append(json.dumps(redact(block), ensure_ascii=False))
    return lines


def unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def write_report(out_dir: Path, target: Path, endpoints: list[str]) -> None:
    template = Path(__file__).resolve().parents[1] / "references" / "report-template.md"
    text = template.read_text(encoding="utf-8")
    text = text.replace("<样本名>", target.name)
    hits = "\n".join("- `%s`" % item.replace("`", "'") for item in endpoints) or "- （没有命中登录/注册相关字符串）"
    text = text.replace("<!-- HITS -->", hits)
    (out_dir / "REPORT.md").write_text(text, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print("Usage: analyze_auth.py <sample-or-har-or-dir> [out-dir]", file=sys.stderr)
        return 2
    if "://" in argv[1]:
        print("Pass a local sample or HAR, not a live URL.", file=sys.stderr)
        return 1
    target = Path(argv[1]).expanduser().resolve()
    if not target.exists():
        print("Not found: %s" % target, file=sys.stderr)
        return 1
    out_dir = Path(argv[2]).expanduser().resolve() if len(argv) > 2 else (
        Path.cwd() / "artifacts" / "login-register-protocol" / target.name
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    files = walk(target)
    hits = []
    for path in files:
        for item in scan_file(path):
            hits.append("%s\t%s" % (path, item))
    endpoints = unique(hits)
    (out_dir / "hits.txt").write_text("\n".join(endpoints) + ("\n" if endpoints else ""), encoding="utf-8")
    urls = unique([line.split("\t", 1)[-1] for line in endpoints if AUTH_RE.search(line)])
    (out_dir / "endpoints.txt").write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    write_report(out_dir, target, urls[:200])
    print("[+] files %d" % len(files))
    print("[+] hits %d" % len(endpoints))
    print("[+] report %s" % (out_dir / "REPORT.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
