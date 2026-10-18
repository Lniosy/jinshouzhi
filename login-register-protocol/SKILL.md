---
name: login-register-protocol
description: >
  指定一个本地目标后立刻开工，还原它的登录/注册协议。
  目标可以是 Android APK、iOS IPA、Web HAR 或前端目录、桌面客户端、小程序解包目录。
  触发：登录、登陆、注册、signin、signup、拆解、一键开工、指定 app、
  登录协议、注册接口、/login-register-protocol。
  用户一旦给出样本路径，本回合就运行 scripts/start.py，不要先写计划。
  APK 由 start.py 调 droid-asc（findrefs → getclass）。加密前明文再读 frida-safe-android。
---

# 登录 / 注册 API 协议一键分析

还原客户端怎么调登录和注册，不猜口令，不撞验证码。交付是一份对过真实请求的协议报告。

## 开工

用户给出样本路径后，仓库根目录只跑这一条：

```bash
login-register-protocol/scripts/start.py <样本路径>
```

缺工具时脚本自己调用 `scripts/ensure-tools.sh`。产物在 `artifacts/login-register-protocol/<样本名>/`：

| 文件 | 内容 |
|---|---|
| `status.json` | 端类型、命中数、工具错误 |
| `REPORT.md` | 协议报告 |
| `client.py` | 重放骨架。登录和注册先是 `NotImplementedError` |
| `refs/` `classes/` | 仅 APK：ASC 引用和反编译类 |

APK/AAB 走 ASC，词表在 `scripts/start.py` 的 `WORDS`。HAR、IPA、桌面、小程序目录走 `analyze_auth.py`。只有包名、没有文件时，停下来要 APK 路径。只有线上地址时，先要 HAR 或前端包，不要扫活站。

跑完先读 `status.json` 和 `classes/` 里引用最多的类，把能确定的方法、路径、字段、变换写进 `REPORT.md` 第 3 节，并填上 `client.py` 里对应函数。静态对不上的留在「未还原」。不要在函数还抛 `NotImplementedError` 时说协议已经实现。

## 端 → 补全

一键扫描只给出候选。下表决定还要打开哪份 skill。工具用法以那份 skill 为准。

| 端 | 一键输入 | 命中后补全 |
|---|---|---|
| Android | APK | 一开始就用 `droid-asc`：`findrefs` → `getclass`。加密前明文用 `frida-safe-android` 按 PID attach，脚本写法见 `rev-frida` |
| iOS | IPA 或已砸目录 | 对二进制跑本脚本；类方法用 class-dump / Hopper。动态同样走 Frida |
| Web | HAR，或站点前端目录 | HAR 已能抽出请求时直接填协议卡。只有包时在命中文件里追 `fetch` / `axios` / `graphql` |
| 桌面 Electron | 安装包、`app.asar`、或已解目录 | 本脚本扫字符串。运行时用 CDP（`--remote-debugging-port`）看真实 XHR |
| 桌面原生 / .NET | EXE、DLL | 本脚本扫字符串。`.NET` 用 dnSpy / ILSpy 打开命中类。协议字段以一次真实请求为准 |
| 小程序 | 解包后的源码目录 | 本脚本扫目录。请求封装通常在 `wx.request` 附近 |

全量反编译才读 `jadx`。要改包才读 `apktool`。

## 填协议卡

报告模板是 `references/report-template.md`。每个登录、注册、发码、校验、刷新各写一块，空着的项不要编。

1. **方法与 URL**。基址注明来自包内常量还是运行时配置。两者不一致时写运行时那个。
2. **头**。哪些是固定头，哪些每次变（时间戳、nonce、设备 id、签名）。
3. **体字段**。字段名用客户端真实名字。标出账号、口令、验证码、邀请码、设备标识。
4. **变换**。先判断落在哪一类，再写清输入：
   - 明文 JSON / 表单
   - 口令在客户端先做 MD5、SHA 或加盐
   - 整个 body 对称加密。记下算法、模式、key、IV 的来源
   - 签名。记下参与签名的字段顺序、是否排序、密钥放哪
5. **响应**。成功时 token 放哪、叫什么、多久过期。失败时「账号不存在」和「密码错误」是否同一句话。
6. **时序**。发码、校验、注册、登录、带 token 访问、刷新、退出，哪几步这个样本实际存在。

变换没有用一条真实请求对上之前，写在「未还原」，不要写成已经确认。

## 复现

协议对上之后，用占位符写一条请求，方便自己的测试账号重放：

```bash
curl -sS -X POST 'https://TARGET/api/login' \
  -H 'content-type: application/json' \
  -d '{"account":"USERNAME","password":"PASSWORD"}'
```

字段名换成样本里的名字。加密体就写加密前的字段，并注明加密函数的位置。不要把抓包里的口令、token、验证码写进报告。

## Agent 纪律

1. 给出目标就跑 `start.py`。不要自己逐个敲 `findrefs`，也不要一上来全量 jadx。
2. 回复只摘要：端、端点个数、已还原的变换、还缺什么。全文在 `REPORT.md`。
3. 找到硬编码的签名密钥、RSA 私钥、固定盐时，写入报告的变换一节，并按 `gap-resource-collision` 登记。
4. 登录门和会员门不是一回事。会员校验交给 `vip-license-re`。
