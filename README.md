# 金手指

本地客户端权益校验的逆向笔记：VIP、会员、卡密、激活码、序列号、试用期。

定位校验点，还原流程和算法，再给出可验证的绕过路径（Frida hook、smali/PE patch、本地标志、keygen 骨架）。对象是自己的样本，或已经获授权的分析目标。客户端绕过不等于服务端权益。

## 目录

每个子目录是一份可单独安装的 skill。`vip-license-re` 用相对路径点到旁边那几份，不依赖本机绝对路径。

```text
vip-license-re/          权益校验：流程、架构类型、绕过顺序
droid-asc/               APK 先 findrefs，再 getclass。包装脚本调用上游 ASC
jadx/                    全量 Java 树。排在 droid-asc 之后
apktool/                 解包、smali、重打包
frida-safe-android/      安卓 Frida，未知机按 PID attach
rev-frida/               hook 脚本写法
gap-resource-collision/  缺口账和资源账
login-register-protocol/ 登录/注册 API 协议。App、Web、桌面、小程序
scripts/ensure-tools.sh  环境自检。缺的工具装到 .tools/
```

调用关系：

```text
vip-license-re
  ├─ APK 静态 ── droid-asc ── 全量时才 jadx
  ├─ 改包 ────── apktool
  ├─ 动态 hook ─ frida-safe-android + rev-frida
  └─ 钥匙登记 ── gap-resource-collision

login-register-protocol
  └─ scripts/start.py <样本>
       ├─ APK ─ droid-asc（findrefs → getclass）
       ├─ HAR / Web / 桌面 / 解包目录 ─ analyze_auth.py
       └─ 加密前明文 ─ frida-safe-android + rev-frida
```

## 安装

把需要的 skill 目录拷进 agent 的 skills 目录，目录名保持不变。工具不进仓库。在仓库根目录自检，缺什么装什么：

```bash
scripts/ensure-tools.sh
export PATH="$PWD/.tools/bin:$PATH"
```

profile 可以只写这次要用的：`asc`、`jadx`、`apktool`、`frida`、`strings`、`python`。`--check` 只报告、不安装。ASC 默认克隆到 `.tools/ASC`，用 `ASC_ROOT` 换位置。账本目录可用 `COLLISION_LEDGER_DIR` 覆盖，默认是 `~/.local/share/gap-resource-collision/`。

`droid-asc/scripts/asc` 和 `frida-safe-android/scripts/safe-attach.sh` 发现工具缺失时会自己调用上面的脚本。

字符串初筛：

```bash
vip-license-re/scripts/hunt_license_strings.sh <样本文件或目录>
login-register-protocol/scripts/start.py <样本路径>
```

## 许可

[MIT](LICENSE)。Copyright (c) 2026 Lniosy。
