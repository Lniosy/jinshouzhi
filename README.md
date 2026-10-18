# 金手指

分析自己的客户端，或已经获授权的样本：登录和注册接口是怎么组的，会员和卡密是在本地判的还是每次问服务器。

仓库地址：<https://github.com/Lniosy/jinshouzhi>

两条主线：

| 你要做的事 | 入口 |
|---|---|
| 指定一个 App / 网页包 / 桌面程序，拆它的注册和登录 | `login-register-protocol/scripts/start.py <样本>` |
| 看 VIP、卡密、试用期、激活是怎么拦功能的 | 阅读 `vip-license-re/SKILL.md`，按里面的流程做 |

安卓上要看代码、找接口、找调用，第一步是 [ASC](https://github.com/MG1937/ASC)：`findrefs` 定位，再 `getclass` 只反编译命中的类。整棵 Java 树用 jadx，改 smali 和重打包用 apktool，看运行时明文用 Frida。

对象是本地样本。只有包名或一个线上地址时，先拿到 APK、HAR 或前端包。不扫活站，不猜口令，不撞验证码。客户端改掉一个布尔值，不等于服务器也认这笔权益。

更细的命令、产物和停手条件在 [docs/workflows.md](docs/workflows.md)。

## 拿下来就能跑

```bash
git clone https://github.com/Lniosy/jinshouzhi.git
cd jinshouzhi
scripts/ensure-tools.sh
export PATH="$PWD/.tools/bin:$PATH"
```

`ensure-tools.sh` 缺什么装什么，装进 `.tools/`，不写进仓库。只检查、不安装：

```bash
scripts/ensure-tools.sh --check
```

只要其中几样时写出名字：`asc`、`jadx`、`apktool`、`frida`、`strings`、`python`。macOS 上优先用 Homebrew；没有 Homebrew 时，jadx、apktool、adb、ripgrep 会从对应的发布页下载到 `.tools/bin`。ASC 克隆到 `.tools/ASC`，要用别的目录就设置 `ASC_ROOT`。

Python 用 3.11 及以上。登录协议和 Frida 会自己挑 `python3.13`、`python3.12`、`python3.11`。

## 目录

每个子目录是一份可以单独拷走的 skill。给 agent 用时，目录名不要改，这样 `SKILL.md` 里的 `name` 才对得上。

```text
login-register-protocol/   指定样本后一键开工，产出协议报告和重放骨架
vip-license-re/            权益校验：架构类型、绕过顺序、hook 模板
droid-asc/                 APK 交叉引用。包装脚本调用上游 ASC
jadx/                      全量 Java 树，排在 ASC 后面
apktool/                   解包、smali、重打包
frida-safe-android/        安卓 Frida。未知机按 PID attach
rev-frida/                 hook 脚本怎么写
gap-resource-collision/    缺口账和资源账
scripts/ensure-tools.sh    环境自检和安装
docs/workflows.md          两条主线的操作说明
```

调用关系：

```text
login-register-protocol/scripts/start.py <样本>
  ├─ APK / AAB ───────── droid-asc（findrefs → getclass）
  ├─ HAR / Web / 桌面 / IPA / 解包目录 ─ analyze_auth.py
  └─ 还要看加密前明文 ── frida-safe-android + rev-frida

vip-license-re
  ├─ APK 静态 ── droid-asc ── 全量时才 jadx
  ├─ 改包 ────── apktool
  ├─ 动态 hook ─ frida-safe-android + rev-frida
  └─ 钥匙登记 ── gap-resource-collision
```

登录门和会员门分开。接口怎么组看 `login-register-protocol`，功能开关和卡密看 `vip-license-re`。

## 装进 agent

把要用的目录拷进 agent 的 skills 目录，名字保持不变。本仓库放在一起，是为了 skill 之间用相对路径互相引用。

| 对 agent 说 | 它应打开 |
|---|---|
| 拆这个 APK 的注册登录 | `login-register-protocol` |
| 这个客户端的 VIP / 卡密怎么校验 | `vip-license-re` |
| 在这个 APK 里找某个字符串的引用 | `droid-asc` |

## 不进仓库的东西

`.gitignore` 排除了样本、安装包和分析产物：

```text
.tools/          本机工具和 ASC 克隆
artifacts/       start.py、字符串扫描的输出
*.apk *.aab *.ipa *.exe *.dll
```

账本默认在 `~/.local/share/gap-resource-collision/`。换目录用环境变量 `COLLISION_LEDGER_DIR`。

## 许可

[MIT](LICENSE)。Copyright (c) 2026 Lniosy。
