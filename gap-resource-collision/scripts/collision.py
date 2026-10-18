#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缺口-资源碰撞账本 CLI（跨目标共享）

主存储: ~/.local/share/gap-resource-collision/{gaps,resources}.json
覆盖:   环境变量 COLLISION_LEDGER_DIR
用法:
  collision.py gap    --type T --desc D --target X [--surface S]
  collision.py res    --type T --source S --desc D --target X [--value V]
  collision.py close  --gap ID [--note N] [--by RES]
  collision.py note   --gap ID --note N
  collision.py list   [--status open|closed|all] [--type T]
  collision.py match  --type T --desc D [--target X] [--side gap|res]
  collision.py brief  [--target X] [--out PATH]
  collision.py help
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

def _ledger_dir() -> Path:
    env = os.environ.get("COLLISION_LEDGER_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".local" / "share" / "gap-resource-collision"

LEDGER_DIR = _ledger_dir()
GAPS_PATH = LEDGER_DIR / "gaps.json"
RES_PATH = LEDGER_DIR / "resources.json"
BRIEF_PATH = LEDGER_DIR / "brief.md"

VALID_TYPES = ("identifier", "credential", "internal_info", "access")
TYPE_ALIASES = {
    "id": "identifier",
    "ids": "identifier",
    "uuid": "identifier",
    "token": "credential",
    "key": "credential",
    "secret": "credential",
    "cred": "credential",
    "creds": "credential",
    "internal": "internal_info",
    "info": "internal_info",
    "ip": "internal_info",
    "path": "internal_info",
    "account": "access",
    "role": "access",
    "entry": "access",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_ledger() -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not GAPS_PATH.exists():
        _write_json(GAPS_PATH, {"version": 1, "updated_at": None, "gaps": []})
    if not RES_PATH.exists():
        _write_json(RES_PATH, {"version": 1, "updated_at": None, "resources": []})


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    ensure_ledger()
    return json.loads(path.read_text(encoding="utf-8"))


def load_gaps() -> dict:
    return _read_json(GAPS_PATH)


def load_resources() -> dict:
    return _read_json(RES_PATH)


def save_gaps(data: dict) -> None:
    data["updated_at"] = now_iso()
    _write_json(GAPS_PATH, data)


def save_resources(data: dict) -> None:
    data["updated_at"] = now_iso()
    _write_json(RES_PATH, data)


def normalize_type(t: str) -> str:
    t = (t or "").strip().lower()
    t = TYPE_ALIASES.get(t, t)
    if t not in VALID_TYPES:
        raise SystemExit(
            f"非法 type={t!r}，允许: {', '.join(VALID_TYPES)} "
            f"(别名: {', '.join(TYPE_ALIASES)})"
        )
    return t


def next_id(items: list, prefix: str) -> str:
    max_n = 0
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for it in items:
        m = pat.match(it.get("id", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}-{max_n + 1:04d}"


_CN_SPLIT = re.compile(r"[\u4e00-\u9fff]{1,}|[A-Za-z0-9_./:-]{2,}")
_STOP = {
    "的", "了", "和", "与", "或", "在", "是", "有", "为", "用", "于", "对", "从",
    "到", "一个", "这个", "那个", "可以", "进行", "相关", "接口", "用于", "缺少",
    "缺", "返回", "发现", "测试", "the", "a", "an", "of", "to", "for", "in", "on",
    "and", "or", "is", "are", "with", "via", "from",
}


def tokenize(text: str) -> set:
    if not text:
        return set()
    toks = set()
    for m in _CN_SPLIT.finditer(text.lower()):
        t = m.group(0)
        if t in _STOP or len(t) < 2:
            continue
        toks.add(t)
        if re.fullmatch(r"[\u4e00-\u9fff]+", t) and len(t) >= 2:
            for i in range(len(t) - 1):
                toks.add(t[i : i + 2])
    return toks


def similarity(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    jaccard = len(inter) / len(union)
    cover = len(inter) / len(ta)
    return 0.55 * jaccard + 0.45 * cover


def rank_matches(query_type, query_desc, candidates, query_target, top_k=5):
    same_type = [c for c in candidates if c.get("type") == query_type]
    scored = []
    for c in same_type:
        sim = similarity(query_desc, c.get("description", ""))
        extra = " ".join(filter(None, [c.get("source", ""), c.get("attack_surface", ""), c.get("value_hint", "")]))
        if extra:
            sim = max(sim, similarity(query_desc, extra) * 0.85)
        c_target = (c.get("target") or "").strip()
        q_target = (query_target or "").strip()
        if q_target and c_target and q_target != c_target:
            cross = 0
            is_cross = True
        elif q_target and c_target and q_target == c_target:
            cross = 1
            is_cross = False
        else:
            cross = 0.5
            is_cross = False
        scored.append((cross, -sim, {**c, "_score": round(sim, 4), "_cross": is_cross}))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in scored[:top_k]]


def format_match_lines(matches, kind):
    if not matches:
        return f"  （无同类型{kind}可碰撞）"
    lines = []
    for i, m in enumerate(matches, 1):
        cross = "跨目标" if m.get("_cross") else "同/未标目标"
        score = m.get("_score", 0)
        if kind == "资源":
            lines.append(
                f"  {i}. [{m.get('id')}] ({cross}, sim={score}) target={m.get('target')!r}\n"
                f"     source={m.get('source')}\n"
                f"     desc={m.get('description')}\n"
                f"     → 行动: 调钥匙来源取值 → 回填缺口攻击面验证"
            )
        else:
            lines.append(
                f"  {i}. [{m.get('id')}] ({cross}, sim={score}) target={m.get('target')!r} status={m.get('status')}\n"
                f"     surface={m.get('attack_surface') or '-'}\n"
                f"     desc={m.get('description')}\n"
                f"     → 行动: 用本资源回填该缺口攻击面验证"
            )
    return "\n".join(lines)


def cmd_gap(args):
    gtype = normalize_type(args.type)
    desc = (args.desc or "").strip()
    if not desc:
        raise SystemExit("--desc 必填，且要具体：缺什么 + 用于哪个攻击面")
    if len(desc) < 8:
        print("⚠ 描述过短，碰撞精度会差。好例：缺他人conversation的UUID，用于chat接口IDOR", file=sys.stderr)

    data = load_gaps()
    gap = {
        "id": next_id(data["gaps"], "gap"),
        "type": gtype,
        "description": desc,
        "status": "open",
        "target": (args.target or "").strip() or None,
        "attack_surface": (args.surface or "").strip() or None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "notes": [],
        "closed_by": None,
    }
    data["gaps"].append(gap)
    save_gaps(data)

    print(f"✓ 已挂账缺口 {gap['id']}  →  {GAPS_PATH}")
    print(f"  type={gap['type']} target={gap['target']!r}")
    print(f"  desc={gap['description']}")
    print(f"  surface={gap['attack_surface']}")
    print()
    print("—— 登记即碰撞：同类型资源 Top5（跨目标优先）——")
    res = load_resources()["resources"]
    matches = rank_matches(gtype, desc, res, gap["target"])
    print(format_match_lines(matches, "资源"))
    print()
    print("纪律: 未闭环前禁止写「无法利用」。状态=open（挂账等钥匙）。")


def cmd_res(args):
    rtype = normalize_type(args.type)
    desc = (args.desc or "").strip()
    source = (args.source or "").strip()
    if not desc or not source:
        raise SystemExit("--desc 与 --source 必填")

    data = load_resources()
    res = {
        "id": next_id(data["resources"], "res"),
        "type": rtype,
        "source": source,
        "description": desc,
        "target": (args.target or "").strip() or None,
        "value_hint": (args.value or "").strip() or None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "notes": [],
    }
    data["resources"].append(res)
    save_resources(data)

    print(f"✓ 已登记资源 {res['id']}  →  {RES_PATH}")
    print(f"  type={res['type']} target={res['target']!r}")
    print(f"  source={res['source']}")
    print(f"  desc={res['description']}")
    if res["value_hint"]:
        print(f"  value_hint={res['value_hint']}")
    print()
    print("—— 登记即碰撞：同类型 open 缺口 Top5（跨目标优先）——")
    gaps = [g for g in load_gaps()["gaps"] if g.get("status") == "open"]
    matches = rank_matches(rtype, desc, gaps, res["target"])
    print(format_match_lines(matches, "缺口"))
    print()
    print("提醒: 碰撞只负责提醒，钥匙能不能开锁必须实际验证。")


def cmd_close(args):
    gid = args.gap.strip()
    data = load_gaps()
    found = None
    for g in data["gaps"]:
        if g["id"] == gid:
            found = g
            break
    if not found:
        raise SystemExit(f"未找到缺口 {gid}")
    found["status"] = "closed"
    found["updated_at"] = now_iso()
    found["closed_by"] = (args.by or "").strip() or None
    note = (args.note or "").strip()
    if note:
        found.setdefault("notes", []).append({"at": now_iso(), "text": note})
    save_gaps(data)
    print(f"✓ 缺口 {gid} 已闭环 (closed)，退出碰撞池。")


def cmd_note(args):
    gid = args.gap.strip()
    note = (args.note or "").strip()
    if not note:
        raise SystemExit("--note 必填")
    data = load_gaps()
    found = None
    for g in data["gaps"]:
        if g["id"] == gid:
            found = g
            break
    if not found:
        raise SystemExit(f"未找到缺口 {gid}")
    found.setdefault("notes", []).append({"at": now_iso(), "text": note})
    found["updated_at"] = now_iso()
    save_gaps(data)
    print(f"✓ 已备注缺口 {gid}: {note}")
    if "不对锁" in note or "不对" in note:
        print("  缺口保持 open，继续等钥匙。")


def cmd_list(args):
    status = (args.status or "open").lower()
    tfilter = normalize_type(args.type) if args.type else None
    gaps = load_gaps()["gaps"]
    res = load_resources()["resources"]

    print(f"账本目录: {LEDGER_DIR}")
    print("=== 缺口账 gaps ===")
    shown = 0
    for g in gaps:
        if status != "all" and g.get("status") != status:
            continue
        if tfilter and g.get("type") != tfilter:
            continue
        shown += 1
        print(
            f"  {g['id']} [{g['status']}] type={g['type']} target={g.get('target')!r}\n"
            f"    {g.get('description')}"
        )
    if shown == 0:
        print("  （空）")

    print()
    print("=== 资源账 resources ===")
    shown = 0
    for r in res:
        if tfilter and r.get("type") != tfilter:
            continue
        shown += 1
        print(
            f"  {r['id']} type={r['type']} target={r.get('target')!r}\n"
            f"    source={r.get('source')}\n"
            f"    {r.get('description')}"
        )
    if shown == 0:
        print("  （空）")


def cmd_match(args):
    mtype = normalize_type(args.type)
    desc = (args.desc or "").strip()
    if not desc:
        raise SystemExit("--desc 必填")
    side = (args.side or "both").lower()
    target = (args.target or "").strip() or None

    if side in ("gap", "both"):
        print("—— 对缺口（以本描述当资源去撞 open 缺口）——")
        gaps = [g for g in load_gaps()["gaps"] if g.get("status") == "open"]
        print(format_match_lines(rank_matches(mtype, desc, gaps, target), "缺口"))
        print()
    if side in ("res", "resource", "both"):
        print("—— 对资源（以本描述当缺口去撞资源）——")
        res = load_resources()["resources"]
        print(format_match_lines(rank_matches(mtype, desc, res, target), "资源"))


def cmd_brief(args):
    filter_target = (args.target or "").strip() or None
    gaps = [g for g in load_gaps()["gaps"] if g.get("status") == "open"]
    resources = load_resources()["resources"]
    if filter_target:
        gaps = [g for g in gaps if (g.get("target") or "") == filter_target or True]

    lines = [
        "# 缺口-资源碰撞 · 开工简报",
        "",
        f"生成时间: {now_iso()}",
        f"账本: {LEDGER_DIR}",
        f"open 缺口: {len([g for g in load_gaps()['gaps'] if g.get('status')=='open'])} · 资源总数: {len(resources)}",
        f"当前聚焦 target: {filter_target or '（全部）'}",
        "",
        "## 纪律提醒",
        "- 「无法利用」不是结论：已闭环，或挂账等钥匙。",
        "- 碰撞只提醒，不保证开锁；验证永远是你的活。",
        "",
        "## 全量配对（每条 open 缺口 × 同类型资源 Top5，跨目标优先）",
        "",
    ]

    open_gaps = [g for g in load_gaps()["gaps"] if g.get("status") == "open"]
    if not open_gaps:
        lines.append("（当前无 open 缺口）")
    else:
        for g in open_gaps:
            lines.append(f"### {g['id']} · {g['type']} · target={g.get('target')!r}")
            lines.append(f"- 缺口: {g.get('description')}")
            if g.get("attack_surface"):
                lines.append(f"- 攻击面: {g['attack_surface']}")
            matches = rank_matches(g["type"], g.get("description", ""), resources, g.get("target"))
            if not matches:
                lines.append("- 碰撞: 暂无同类型资源")
            else:
                lines.append("- 候选钥匙:")
                for i, m in enumerate(matches, 1):
                    tag = "跨目标" if m.get("_cross") else "同/未标"
                    lines.append(
                        f"  {i}. [{m['id']}] ({tag}, sim={m.get('_score')}) "
                        f"target={m.get('target')!r} | {m.get('source')} | {m.get('description')}"
                    )
                lines.append("- 行动: 调钥匙接口取值 → 回填缺口攻击面验证")
            lines.append("")

    lines.append("## 资源账一览")
    lines.append("")
    if not resources:
        lines.append("（资源账为空）")
    else:
        for r in resources:
            lines.append(
                f"- {r['id']} [{r['type']}] target={r.get('target')!r} "
                f"| {r.get('source')} | {r.get('description')}"
            )

    text = "\n".join(lines) + "\n"
    out = Path(args.out).expanduser() if args.out else BRIEF_PATH
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n（已写入 {out}）", file=sys.stderr)


def build_parser():
    p = argparse.ArgumentParser(description="缺口-资源碰撞账本")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gap", help="登记缺口（碰壁挂账）")
    g.add_argument("--type", "-t", required=True)
    g.add_argument("--desc", "-d", required=True)
    g.add_argument("--target", "-T", default="")
    g.add_argument("--surface", "-s", default="")
    g.set_defaults(func=cmd_gap)

    r = sub.add_parser("res", help="登记资源（发现钥匙）")
    r.add_argument("--type", "-t", required=True)
    r.add_argument("--source", "-S", required=True)
    r.add_argument("--desc", "-d", required=True)
    r.add_argument("--target", "-T", default="")
    r.add_argument("--value", "-v", default="")
    r.set_defaults(func=cmd_res)

    c = sub.add_parser("close", help="闭环缺口")
    c.add_argument("--gap", required=True)
    c.add_argument("--note", default="")
    c.add_argument("--by", default="")
    c.set_defaults(func=cmd_close)

    n = sub.add_parser("note", help="给缺口加备注")
    n.add_argument("--gap", required=True)
    n.add_argument("--note", required=True)
    n.set_defaults(func=cmd_note)

    l = sub.add_parser("list", help="列出账本")
    l.add_argument("--status", default="open", choices=["open", "closed", "all"])
    l.add_argument("--type", "-t", default="")
    l.set_defaults(func=cmd_list)

    m = sub.add_parser("match", help="手工碰撞查询")
    m.add_argument("--type", "-t", required=True)
    m.add_argument("--desc", "-d", required=True)
    m.add_argument("--target", "-T", default="")
    m.add_argument("--side", default="both", choices=["both", "gap", "res", "resource"])
    m.set_defaults(func=cmd_match)

    b = sub.add_parser("brief", help="会话启动全量配对简报")
    b.add_argument("--target", "-T", default="")
    b.add_argument("--out", default="")
    b.set_defaults(func=cmd_brief)

    h = sub.add_parser("help", help="帮助")
    h.set_defaults(func=lambda a: print(__doc__))

    return p


def main(argv=None):
    # 重新解析 LEDGER（允许环境变量）
    global LEDGER_DIR, GAPS_PATH, RES_PATH, BRIEF_PATH
    LEDGER_DIR = _ledger_dir()
    GAPS_PATH = LEDGER_DIR / "gaps.json"
    RES_PATH = LEDGER_DIR / "resources.json"
    BRIEF_PATH = LEDGER_DIR / "brief.md"
    ensure_ledger()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
