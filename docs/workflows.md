# 操作说明

命令都在仓库根目录执行。工具细节在各自的 `SKILL.md`，这里只写开工、产物和什么时候停。

分析对象是你自己的样本，或已经获授权的样本。

## 1. 拆注册和登录

准备一个本地文件或目录：

| 手里有的 | 例子 |
|---|---|
| 安卓安装包 | `app.apk`、`app.aab` |
| 抓包 | `capture.har` |
| 网页前端 | 含打包 js 的目录 |
| 桌面程序 | `.exe`、`.dll`、`app.asar`、解出来的目录 |
| iOS | `.ipa`，或已经砸开的目录 |
| 小程序 | 解包后的源码目录 |

然后：

```bash
scripts/ensure-tools.sh asc strings python
export PATH="$PWD/.tools/bin:$PATH"
login-register-protocol/scripts/start.py /path/to/app.apk
```

非 APK 同样是这一条命令。`start.py` 自己判断类型。APK / AAB 会调用 `droid-asc/scripts/asc`，对其余样本调用 `analyze_auth.py`。

产物在 `artifacts/login-register-protocol/<样本文件名>/`：

| 文件 | 内容 |
|---|---|
| `status.json` | 端类型、命中数、工具报错 |
| `REPORT.md` | 协议报告。模板是 `login-register-protocol/references/report-template.md` |
| `client.py` | 重放骨架。`login` / `register` 在字段和加密没对上之前会抛 `NotImplementedError` |
| `refs/`、`classes/` | 只有 APK 有。`refs/` 是引用，`classes/` 是反编译出的类 |

APK 的搜索词在 `login-register-protocol/scripts/start.py` 的 `WORDS`。引用最多的几个业务类会被反编译，`android.*`、`androidx.*`、`kotlin.*` 这类框架类会跳过。

报告里口令、token、验证码的值写成 `<redacted>`，字段名保留。

### 读完静态结果之后

1. 打开 `status.json`。`errors` 不是空的话，先看是超时还是 ASC 没装上。
2. 从 `classes/` 里引用最多的类读起，把方法、URL、字段名、签名或加密写进 `REPORT.md` 第 3 节。
3. 这些已经能对上一条真实请求或一段客户端代码时，再改 `client.py`。用自己的测试账号占位，不要把抓包里的口令贴进去。
4. body 仍是密文、签名对不上时，停在报告的「未还原」。要看加密前明文，用 `frida-safe-android/scripts/safe-attach.sh <包名> <hook.js>`，未知机按 PID attach。hook 的写法见 `rev-frida/SKILL.md`。

只有包名、没有安装包时，`start.py` 不会开工。先把 APK 放到本机再把路径传进去。只有一个网址时，先导出 HAR 或前端包。

## 2. 看会员、卡密、试用期

打开 `vip-license-re/SKILL.md`，按这个顺序：

1. 样本是什么平台，验证更像 A–G 里的哪一类。类型表和绕过顺序在 `vip-license-re/references/bypass-matrix.md`，猎杀词在 `vip-license-re/references/hunt-keywords.md`。
2. 安卓先自检再搜引用：

```bash
scripts/ensure-tools.sh asc
droid-asc/scripts/asc findrefs app.apk string isVip -o artifacts/vip-license-re/app/isVip.txt
```

每个词单独跑一次。类名从引用行里取，再：

```bash
droid-asc/scripts/asc getclass app.apk com.example.VipManager -o artifacts/vip-license-re/app/VipManager.java
```

3. 要整棵源码树时才用 jadx。要改 smali 并重打包时才用 apktool。
4. 动态确认用 Frida。门闩模板是 `vip-license-re/scripts/frida-vip-hooks.js`。未知机不要 spawn：

```bash
scripts/ensure-tools.sh frida
frida-safe-android/scripts/safe-attach.sh <包名> vip-license-re/scripts/frida-vip-hooks.js
```

手机已连接、且 `/data/local/tmp` 没有同版本 `frida-server` 时，`ensure-tools.sh frida` 会下载并 push。

5. 字符串初筛，不代替 ASC：

```bash
vip-license-re/scripts/hunt_license_strings.sh <样本文件或目录>
```

交付写清三件事：本地功能是否已经打开、是否只要免费登录、哪些接口仍被服务端拒绝。

## 3. 安卓工具怎么选

| 目的 | 用 | 不要 |
|---|---|---|
| 找字符串、类、方法的引用，并只反编译那几个类 | `droid-asc` | 一上来 jadx 全量反编译 |
| 要可搜索的整棵 Java 树、Manifest 浏览 | `jadx` | 把它当第一步 |
| 读资源、改 smali、重打包 | `apktool` | 用它代替 ASC 搜代码 |
| 看运行中的参数和返回值 | `frida-safe-android` | 在未知机上 `frida -f` spawn |

`droid-asc/scripts/asc` 发现 `.tools/ASC` 不存在时会自己克隆并安装依赖。

## 4. 缺口和钥匙

分析过程中缺一个对不上的 id，或从样本里看到密钥、盐、固定 token，记一笔：

```bash
scripts/ensure-tools.sh python
python3 gap-resource-collision/scripts/collision.py gap \
  --type identifier \
  --desc "缺什么，用来打哪个接口" \
  --target "样本名"

python3 gap-resource-collision/scripts/collision.py res \
  --type credential \
  --source "哪个文件或响应" \
  --desc "这串钥匙是什么" \
  --target "样本名"
```

账本在 `~/.local/share/gap-resource-collision/`。`COLLISION_LEDGER_DIR` 可以改位置。
