#!/usr/bin/env python3
"""Start login/register protocol work for one local target.

Usage:
  start.py <target> [out-dir]

Android APK/AAB: ASC findrefs on the auth words, then getclass for the
hottest classes. Other local samples: analyze_auth.py.
Writes REPORT.md, status.json, and client.py. Secrets are redacted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

WORDS = (
    "login",
    "register",
    "signin",
    "signup",
    "oauth",
    "token",
    "sms",
    "captcha",
    "password",
    "登录",
    "注册",
    "验证码",
)
SKIP_PREFIX = (
    "android.",
    "androidx.",
    "java.",
    "javax.",
    "kotlin.",
    "kotlinx.",
    "com.google.android.",
)
REF_RE = re.compile(
    r"^(?P<dex>\S+) \| L(?P<cls>[^;]+);->(?P<method>\S+) \| matched=\((?P<hit>.*)\)\s*$"
)
URL_RE = re.compile(r"https?://[^\s\"'<>\\]{8,200}")
CRYPTO_RE = re.compile(
    r"Cipher|MessageDigest|Mac\.getInstance|SecretKeySpec|IvParameterSpec|"
    r"\bAES\b|\bRSA\b|HmacSHA|MD5|SHA-?256|signature|sign\(",
    re.I,
)
LINE_SECRET = re.compile(
    r"(?i)(?<![A-Za-z])(password|passwd|pwd|token|authorization|secret|otp|code)(?![A-Za-z])"
    r"(\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,}&]+)"
)
MAX_CLASSES = 8
FINDREFS_TIMEOUT = 180

REPO = Path(__file__).resolve().parents[2]
ASC = REPO / "droid-asc" / "scripts" / "asc"
ANALYZE = Path(__file__).resolve().parent / "analyze_auth.py"
ENSURE = REPO / "scripts" / "ensure-tools.sh"
TEMPLATE = Path(__file__).resolve().parents[1] / "references" / "report-template.md"


def redact_line(text: str) -> str:
    return LINE_SECRET.sub(r"\1\2<redacted>", text)


def parse_ref_line(line: str):
    match = REF_RE.match(line.strip())
    if not match:
        return None
    cls = match.group("cls").replace("/", ".")
    return {
        "dex": match.group("dex"),
        "class": cls,
        "method": match.group("method"),
        "hit": match.group("hit"),
    }


def keep_class(name: str) -> bool:
    return not name.startswith(SKIP_PREFIX)


def ranked_classes(rows: list[dict]) -> list[tuple[str, int]]:
    counts = Counter(row["class"] for row in rows if keep_class(row["class"]))
    return counts.most_common(MAX_CLASSES)


def run(cmd: list[str], timeout: int, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def ensure(profile: str) -> None:
    if ENSURE.is_file():
        run([str(ENSURE), profile], timeout=1800, cwd=REPO)


def apk_job(target: Path, out: Path) -> dict:
    ensure("asc")
    refs_dir = out / "refs"
    class_dir = out / "classes"
    refs_dir.mkdir(parents=True, exist_ok=True)
    class_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    errors = []
    for word in WORDS:
        dest = refs_dir / ("%s.txt" % word)
        try:
            proc = run(
                [str(ASC), "findrefs", str(target), "string", word, "-o", str(dest)],
                FINDREFS_TIMEOUT,
                REPO,
            )
        except subprocess.TimeoutExpired:
            errors.append("%s: timeout" % word)
            continue
        text = dest.read_text(encoding="utf-8", errors="replace") if dest.exists() else proc.stdout
        if not dest.exists() and proc.stdout:
            dest.write_text(proc.stdout, encoding="utf-8")
            text = proc.stdout
        if proc.returncode != 0 and not text.strip():
            errors.append("%s: %s" % (word, (proc.stderr or "").strip()[:300]))
            continue
        for line in text.splitlines():
            row = parse_ref_line(line)
            if row:
                row["word"] = word
                rows.append(row)
    classes = ranked_classes(rows)
    written = []
    for name, _count in classes:
        dest = class_dir / (name + ".java")
        proc = run(
            [str(ASC), "getclass", str(target), name, "-o", str(dest)],
            FINDREFS_TIMEOUT,
            REPO,
        )
        if proc.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
            if proc.stdout.strip():
                dest.write_text(proc.stdout, encoding="utf-8")
            else:
                errors.append("getclass %s: %s" % (name, (proc.stderr or "").strip()[:300]))
                continue
        written.append(str(dest))
    return {"rows": rows, "classes": classes, "java": written, "errors": errors}


def scan_java(paths: list[str]) -> dict:
    urls = []
    crypto = []
    for item in paths:
        text = Path(item).read_text(encoding="utf-8", errors="replace")
        for found in URL_RE.findall(text):
            urls.append(found.rstrip(".,);"))
        for line in text.splitlines():
            if CRYPTO_RE.search(line):
                crypto.append(redact_line(line.strip())[:240])
    return {"urls": unique(urls)[:40], "crypto": unique(crypto)[:40]}


def unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def write_client(path: Path, sample: str, urls: list[str], classes: list[str]) -> None:
    url_lines = "\n".join('URLS.append("%s")' % item.replace("\\", "\\\\").replace('"', '\\"') for item in urls) or "pass"
    class_lines = "\n".join("# %s" % item for item in classes) or "# no class decompiled"
    path.write_text(
        "\n".join([
            "# Replay skeleton for %s" % sample,
            "# Fill USERNAME and PASSWORD with your own test account.",
            "# Captured secrets do not belong in this file.",
            "",
            "USERNAME = \"USERNAME\"",
            "PASSWORD = \"PASSWORD\"",
            "URLS = []",
            url_lines,
            "",
            class_lines,
            "",
            "def login(account=USERNAME, password=PASSWORD):",
            "    \"\"\"Body field names and any crypto come from classes/*.java.\"\"\"",
            "    import requests",
            "    raise NotImplementedError(\"confirm method, path, and transform from the decompiled classes\")",
            "",
            "def register(account, password, code=\"CODE\"):",
            "    raise NotImplementedError(\"confirm the register call from the decompiled classes\")",
            "",
            "if __name__ == \"__main__\":",
            "    print(\"\\n\".join(URLS) or \"no auth url yet\")",
            "",
        ]),
        encoding="utf-8",
    )


def write_apk_report(out: Path, target: Path, job: dict, clues: dict) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    template = template.replace("<样本名>", target.name)
    hits = []
    for url in clues["urls"]:
        hits.append("- `%s`" % url)
    if not hits:
        hits.append("- （ASC 引用里还没有抽出 http URL，看 classes/ 里的路径拼接）")
    text = template.replace("<!-- HITS -->", "\n".join(hits))
    class_lines = "\n".join("- `%s` (%d)" % pair for pair in job["classes"]) or "- （没有业务类命中）"
    crypto = "\n".join("- %s" % line for line in clues["crypto"]) or "- （反编译片段里没有 Cipher / Digest / Mac）"
    errors = "\n".join("- %s" % item for item in job["errors"]) or "- 无"
    text += "\n".join([
        "",
        "## 6. 调用类",
        "",
        class_lines,
        "",
        "## 7. 变换线索",
        "",
        crypto,
        "",
        "## 8. 客户端骨架",
        "",
        "`client.py` 只放了挖到的 URL。登录和注册函数要等上面的类把字段和变换对上再填。",
        "",
        "## 9. 工具错误",
        "",
        errors,
        "",
    ])
    (out / "REPORT.md").write_text(text, encoding="utf-8")


def other_job(target: Path, out: Path) -> dict:
    ensure("strings")
    proc = run([sys.executable, str(ANALYZE), str(target), str(out)], 300, REPO)
    endpoints = []
    endpoint_file = out / "endpoints.txt"
    if endpoint_file.exists():
        endpoints = [line for line in endpoint_file.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    urls = [line for line in endpoints if line.startswith("http")]
    if proc.returncode != 0:
        (out / "scan-error.txt").write_text(proc.stderr or proc.stdout, encoding="utf-8")
    return {"urls": urls, "endpoints": endpoints, "returncode": proc.returncode}


def kind_of(target: Path) -> str:
    suffix = target.suffix.lower()
    if suffix in {".apk", ".aab"}:
        return "apk"
    if suffix == ".har":
        return "har"
    if suffix == ".ipa":
        return "ios"
    if suffix in {".exe", ".dll"}:
        return "desktop"
    if suffix == ".asar":
        return "electron"
    if target.is_dir():
        return "dir"
    return "file"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print("Usage: start.py <apk|har|dir|desktop-sample> [out-dir]", file=sys.stderr)
        return 2
    if "://" in argv[1]:
        print("Pass a local sample, not a live URL.", file=sys.stderr)
        return 1
    target = Path(argv[1]).expanduser().resolve()
    if not target.exists():
        print("Not found: %s" % target, file=sys.stderr)
        return 1
    kind = kind_of(target)
    out = Path(argv[2]).expanduser().resolve() if len(argv) > 2 else (
        Path.cwd() / "artifacts" / "login-register-protocol" / target.name
    )
    out.mkdir(parents=True, exist_ok=True)
    status = {"target": str(target), "kind": kind, "out": str(out)}
    if kind == "apk":
        job = apk_job(target, out)
        clues = scan_java(job["java"])
        write_apk_report(out, target, job, clues)
        write_client(out / "client.py", target.name, clues["urls"], [name for name, _n in job["classes"]])
        status.update({
            "refs": len(job["rows"]),
            "classes": len(job["classes"]),
            "urls": len(clues["urls"]),
            "errors": job["errors"],
        })
        code = 0 if job["rows"] or job["java"] else 1
    else:
        job = other_job(target, out)
        urls = [item for item in job["urls"] if item.startswith("http")]
        write_client(out / "client.py", target.name, urls, [])
        status.update({"endpoints": len(job["endpoints"]), "urls": len(urls), "returncode": job["returncode"]})
        code = 0 if job["endpoints"] else job["returncode"]
    (out / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[+] kind %s" % kind)
    print("[+] out %s" % out)
    print("[+] status %s" % (out / "status.json"))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
