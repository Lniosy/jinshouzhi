#!/usr/bin/env bash
#
# safe-attach.sh —— 安卓 Frida「防重启」附加器
#
# 设计目标:在 HyperOS/Android 14~16 + PAC 机型上优先走“最小风险”的官方 Frida attach 路径。
# 注意:旧版 Frida 或某些系统组合上,枚举 / spawn / 按名字附加可能把 system_server 打崩。
# 已验证例外:2026-06-25 实测 Redmi K70(vermeer) / HyperOS 3 / Android 16 /
#            official Frida 17.15.3 下,PID attach、-N、frida-ps -Ua 均未重启;
#            但 -f spawn 仍会报 setArgV0 slot 错误。
# 因此本脚本仍默认只走 PID attach,不是因为其它方式永远危险,而是为了跨设备保守。
#
# 用法:
#   ./safe-attach.sh <包名> [hook.js]
#   ./safe-attach.sh <包名> hooks/noop.js
#
# 可选环境变量:
#   SERIAL=<adb序列号>     多设备时指定
#   FRIDA_SERVER=<设备端绝对路径>  跳过自动版本匹配,强制用指定 server
#
set -euo pipefail

PKG="${1:-}"
HOOK="${2:-}"
[ -z "$PKG" ] && { echo "用法: $0 <包名> [hook.js]" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PATH="$REPO_ROOT/.tools/bin:${PATH:-}"
if [[ -x "$REPO_ROOT/scripts/ensure-tools.sh" ]]; then
  "$REPO_ROOT/scripts/ensure-tools.sh" frida
fi

ADB=(adb)
[ -n "${SERIAL:-}" ] && ADB=(adb -s "$SERIAL")

err()  { echo "[错误] $*" >&2; exit 1; }
info() { echo "[信息] $*" >&2; }

# 0) 基础校验 ---------------------------------------------------------------
command -v adb   >/dev/null 2>&1 || err "未找到 adb。在仓库根目录运行 scripts/ensure-tools.sh frida"
command -v frida >/dev/null 2>&1 || err "未找到 frida。在仓库根目录运行 scripts/ensure-tools.sh frida"
"${ADB[@]}" get-state >/dev/null 2>&1 || err "没有已连接的 adb 设备"

LOCAL_VER="$(frida --version | tr -d '[:space:]')"
info "本地 frida 版本: $LOCAL_VER"

# 1) 选一个版本匹配的设备端 frida-server -----------------------------------
SERVER_BIN="${FRIDA_SERVER:-}"
if [ -z "$SERVER_BIN" ]; then
    # 列出 /data/local/tmp 下所有 frida-server*,优先精确版本匹配(兼容 bash 3.2,不用 mapfile)
    CANDS=()
    while IFS= read -r line; do
        [ -n "$line" ] && CANDS+=("$line")
    done < <("${ADB[@]}" shell 'su -c "ls /data/local/tmp 2>/dev/null"' \
              | tr -d '\r' | grep -i 'frida-server' || true)
    [ "${#CANDS[@]}" -ge 1 ] || err "设备 /data/local/tmp 下没有 frida-server,请先 push。"
    # 1.a 文件名里直接带本地版本号的
    for c in "${CANDS[@]}"; do
        [[ "$c" == *"$LOCAL_VER"* ]] && SERVER_BIN="/data/local/tmp/$c" && break
    done
    # 1.b 退而用裸 frida-server(需自行确保版本一致)
    if [ -z "$SERVER_BIN" ]; then
        for c in "${CANDS[@]}"; do
            [[ "$c" == "frida-server" ]] && SERVER_BIN="/data/local/tmp/$c" && break
        done
    fi
    [ -z "$SERVER_BIN" ] && SERVER_BIN="/data/local/tmp/${CANDS[0]}"
fi
info "设备端 frida-server: $SERVER_BIN"

# 2) 启动 frida-server(若未运行) -------------------------------------------
if ! "${ADB[@]}" shell 'su -c "ps -e 2>/dev/null | grep -c frida-server"' | tr -d '\r' | grep -qvx 0; then
    info "启动 frida-server ..."
    # -D 后台守护;输出丢弃,避免 adb 卡住
    "${ADB[@]}" shell "su -c 'nohup $SERVER_BIN -D >/data/local/tmp/frida-server.log 2>&1 &'" >/dev/null 2>&1 || true
    sleep 2
fi
"${ADB[@]}" shell 'su -c "ps -e 2>/dev/null | grep frida-server"' | tr -d '\r' | grep -q frida-server \
    || err "frida-server 未能启动,查看 /data/local/tmp/frida-server.log"
info "frida-server 运行中"

# 3) 拿目标 PID —— 默认用 pidof(走 /proc),保持跨设备最保守 ----------------
get_pid() { "${ADB[@]}" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}'; }
PID="$(get_pid)"
if [ -z "$PID" ]; then
    info "目标未运行,用 monkey 拉起(不走 spawn,保持最保守路径)..."
    "${ADB[@]}" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
    for i in 1 2 3 4 5 6; do sleep 1; PID="$(get_pid)"; [ -n "$PID" ] && break; done
fi
[ -z "$PID" ] && err "拿不到 $PKG 的 PID,请先手动打开该 app。"
info "目标 PID: $PID"

# 4) 只按 PID 附加 ----------------------------------------------------------
if [ -n "$HOOK" ]; then
    [ -f "$HOOK" ] || err "hook 文件不存在: $HOOK"
    info "frida -U -p $PID -l $HOOK"
    exec frida -U -p "$PID" -l "$HOOK"
else
    info "frida -U -p $PID(交互式 REPL)"
    exec frida -U -p "$PID"
fi
