---
name: vip-license-re
description: >
  逆向分析本地客户端（Android APK、Windows EXE/桌面端、通用 App）的 VIP 会员验证、
  卡密/激活码/授权码校验逻辑，还原验证流程与算法，并给出可落地的绕过路线
  （Frida hook、smali/PE patch、本地标志篡改、keygen 骨架）。
  触发：VIP、会员、付费墙、isVip、premium、卡密、激活码、授权码、license、
  serial、activation、试用、trial、到期、expire、keygen、patch、绕过验证、
  客户端授权逆向、/vip-license-re。
  APK 反编译先读同仓库 droid-asc（findrefs → getclass），不要一上来全量 jadx；
  全量源码树再读 jadx；改包读 apktool；动态 hook 读 frida-safe-android（PID attach）和 rev-frida。
  发现钥匙型数据时登记到 gap-resource-collision。
  开工先跑仓库 scripts/ensure-tools.sh，缺少的工具会自动安装。
---

# VIP / 卡密验证逆向与绕过

专注**本地 App 客户端**的权益校验：VIP、会员、premium、卡密、激活码、序列号、试用期。
目标不是泛化挖洞，而是：**定位校验点 → 还原流程/算法 → 给出可验证的绕过路径**。

## 边界

- 对象：用户提供的本地样本（APK/EXE/IPA/桌面客户端）或已授权分析目标。
- 默认产出：验证链路图、关键函数、算法结构、绕过 PoC（hook / patch / keygen 骨架）。
- 服务端强校验（在线签发 JWT/权益、服务端拒绝功能 API）要明确标注：**客户端绕过 ≠ 服务端权益**。
- 不替代业务逻辑或接口审计。本 skill 只管客户端授权校验本身。登录/注册请求怎么组，用 `login-register-protocol`。

## 本地功能优先原则（强制）

很多 App 把「登录墙」和「付费 VIP」叠在一起，但**业务功能本身是纯本地代码**（扫描、识别、本地限次、UI 锁）。对此默认按下面做，不要一看到登录/联网就停成「类型 D 无法绕」：

1. **先分清两道门**：`登录门`（账号会话）vs `VIP 门`（isVip / subscription_product_id / permission set）。
2. **登录若免费**（Google/邮箱/游客可建号、不收费）：**允许并优先登录**，拿齐本地上下文后再 hook VIP 门闩。登录不是付费绕过，是测试前置。
3. **功能判定在客户端**：门闩是本地布尔/枚举/配额（混淆短类名、SharedPreferences）→ **Frida 强制 VIP / 改返回值 / 拦 sync 写回 FREE**，把本地能力开满。
4. **只有**关键能力每次请求都被服务端 403/缺字段拒绝时，才标类型 D，并写清「本地已开、云端仍拦」。
5. 交付时分开写：`本地功能（hook 可开）` / `需登录（免费可做）` / `需付费凭证的云端 API（不可用 hook 冒充）`。

口诀：**免费登录先过 → 本地 VIP 门闩 hook 强开 → 再测功能是否真本地。**

## 复合架构拆解（强制·防误判）

发卡网 / 商户 SaaS /「AI 员工」类客户端常见 **A+D 叠层**。禁止用「要登录」「要联网」直接判死。按三层拆：

| 层 | 问什么 | 典型落点 | 绕过含义 |
|---|---|---|---|
| **登录门** | 有没有会话 | `shopToken` / JWT / cookie | 测试前置；可真登或（仅动态探 UI 时）伪造会话 |
| **权益门** | 能不能用（到期/VIP/算力） | `end_time`、`isExpire`、`cms_number`、`isVip` | hook/patch/改响应；先开客户端门闩 |
| **执行引擎** | 功能真正跑在哪 | 本地 Playwright/RPA、页内 ImSdk、云 `/sale/*`、协议客户端 | 决定「真开」价值：本地引擎可开＝高价值 |

补充纪律：

1. **词义拆开**：「激活码」可能是设备座位码（`activi_code`），不是软件序列号；「会员/算力」才是权益。
2. **配置域名 ≠ 运行域名**：`config.conf` / 内置 baseURL 常被 OEM（`MainBaseUrl` / `GETOEMCONFIG` / `webHost`）覆盖；以实际 XHR/CDP 为准。
3. **布尔命名不可信**：如 `isExpire = now <= end_time` 时 true 表示**未到期可用**。先读赋值再 hook。
4. **安装包先剥壳再猎杀**：NSIS/`app-64.7z`/Squirrel 等 → 找到真正 `app.asar` 或主 EXE，勿只在 Setup 上 strings。
5. **进主界面 ≠ 只过登录**：Electron 路由常依赖服务端菜单（如 `/sale/salememu`）；假 token 还要过 `getInfo` + 动态路由，并防 `-101` 异地踢下线/`resetToken`。
6. **执行引擎定性**（交付必写一句）：`浏览器模拟(Playwright)` / `页内 API 截获` / `私有协议` / `纯云 API` —— 智能获客类多为前两者，不是独立协议栈。

口诀补一句：**先拆三层，再谈能不能免计费。**

## 工具分流（先选对栈）

| 样本 | 静态入口 | 动态入口 | 改包/补丁 |
|---|---|---|---|
| Android APK | 先读 `droid-asc`：`findrefs` → `getclass`；全量树再读 `jadx` | 先读 `frida-safe-android`（PID attach），脚本写法见 `rev-frida` | 读 `apktool`：smali 改 + 重签 |
| Windows PE/EXE | `file`/`strings`/`diec` → IDA/Ghidra/x64dbg | x64dbg / Frida Windows / ScyllaHide | 十六进制 patch 或 loader |
| .NET | dnSpy / ILSpy | dnSpy 调试 | IL 改写 |
| Electron/NW | **先解安装器**再 `asar`；搜 `end_time`/`shopToken`/`isExpire`/`salememu` | **CDP**（`--remote-debugging-port`）优先于盲目 Frida；DevTools | 改 `app.asar` 门闩赋值 |
| iOS（有样本时） | class-dump / Hopper / IDA | Frida | 越狱 hook / 重签 |

APK 纪律：先读 `../droid-asc/SKILL.md`，`findrefs` 后再 `getclass`，**禁止一上来全量 jadx**。全量树才读 `../jadx/SKILL.md`。  
Frida 安卓：先读 `../frida-safe-android/SKILL.md`，未知机默认 PID attach。hook 写法读 `../rev-frida/SKILL.md`。  
改包：读 `../apktool/SKILL.md`。

## 开工清单

0. 环境自检。在仓库根目录执行 `scripts/ensure-tools.sh`。只要本次用到的部分时带上 profile：`asc`、`jadx`、`apktool`、`frida`、`strings`、`python`。缺的工具由脚本安装到 `.tools/`，并把 `.tools/bin` 放进 `PATH`。只检查不安装：`scripts/ensure-tools.sh --check`。
1. 确认样本路径、平台、是否加壳/混淆。
2. 用户目标三选一（可并行）：**只还原流程** / **要绕过** / **要 keygen**。
3. 建输出目录：`artifacts/vip-license-re/<sample>/`。
4. 先判定验证架构类型（下一节），再选绕过路线——不要上来就 patch。

## 验证架构分类（先定性）

| 类型 | 特征 | 绕过主路径 | 价值 |
|---|---|---|---|
| **A 纯本地标志** | SharedPreferences/`isVip`/注册表/`license.dat` 决定 UI | 改存储 / hook getter / patch 分支 | 高（功能常真开） |
| **B 本地算法卡密** | 输入码 → 本地校验（XOR/CRC/自定义/RSA 验签） | 还原算法 → keygen；或 patch 校验返回 | 高 |
| **C 在线激活落本地** | 联网激活一次，落 token/到期时间到本地 | hook 激活响应 / 伪造本地 token / 改时间校验 | 中高 |
| **D 每次在线强校验** | 关键 API 带会员态，服务端拒绝 | 客户端绕过只改 UI；真权益需服务端漏洞 | 低（标清） |
| **E 试用/时间锁** | 安装时间、首次运行、硬件绑定倒计时 | 改时间源 / 清标记 / patch 比较 | 中 |
| **F 硬件绑定** | 机器码/AndroidID/主板序列参与签名 | 抓绑定字段 → 改算法输入或 patch 绑定比较 | 中 |
| **G 第三方 SDK** | 国内卡密平台 / RevenueCat / 自研授权 SDK | 定位 SDK 入口类，按 A–F 再归类 | 视实现 |

详细判定信号见 `references/hunt-keywords.md`。绕过优先级见 `references/bypass-matrix.md`。

## 标准流程

```
样本定性(平台/壳/架构类型)
        │
        ▼
关键字猎杀(VIP/license/卡密/expire/activate…)
        │
        ▼
定位校验函数与调用链(UI → 校验 → 落库/请求)
        │
        ▼
画验证流程图 + 标信任边界(本地 vs 服务端)
        │
        ▼
选绕过: hook 返回值 / patch 分支 / 改存储 / keygen
        │
        ▼
验证: 功能是否真开、关键 API 是否仍 403
        │
        ▼
交付: 链路图 + 关键点 + PoC + 局限说明
```

### 1) 猎杀关键字

APK（每个词单独跑一次 `droid-asc/scripts/asc findrefs <apk> string <词>`，输出到 `artifacts/vip-license-re/`）：

```text
vip  VIP  isVip  is_vip  premium  member  会员  开通
license  serial  activate  activation  卡密  激活码  授权码
expire  expiry  trial  试用  到期  validUntil
checkLicense  verify  unlock  paywall
```

PE/通用：

```bash
strings -a -n 6 TARGET | rg -i 'vip|license|serial|activ|expire|trial|卡密|激活|会员|授权'
```

命中后立刻追：谁读、谁写、失败字符串的 xref、成功跳转。

### 2) 还原调用链（必画）

最少标出：

```text
[入口] 设置页/启动闪屏/功能点击
   → [采集] 卡密输入 / 设备 ID / 本地旧 token
   → [变换] 哈希/加密/签名/拼请求体
   → [判定] 本地 if / 服务端 HTTP
   → [落库] SP/文件/注册表/Keychain
   → [门闩] UI 显隐、功能方法开头的 isVip()、拦截器
```

每个节点记：类/函数名、文件偏移或 smali 方法、真假分支条件。

### 3) 算法还原要点

- **对称**：硬编码 key/IV？模式 ECB/CBC？密钥是否派生自设备 ID？
- **非对称**：本地是否只有公钥（验签）？私钥是否误打包？
- **卡密格式**：长度、字符集、校验位、分段规则、时间窗、设备绑定字段。
- **成功条件**：只看布尔？还看到期时间、渠道、SKU、签名字段？

Keygen 骨架放 `artifacts/vip-license-re/keygen.py`，变量用真实字段名；未知处置 `SERIAL`/`LICENSE_BLOB`/`ENCRYPT_KEY` 占位并注释缺什么。

### 4) 绕过执行顺序（实战默认）

1. **免费登录**（若有登录墙且注册/第三方登录不收费）：先登录，再测 VIP。不要卡在登录弹窗上结束分析。
2. **最快验证**：Frida hook 门闩强制 VIP / `true`（见 `scripts/frida-vip-hooks.js`）。同时 hook「无购买则写 FREE」的 sync 回写，避免 Play/服务器把本地状态冲掉。
3. **持久化**：改本地标志文件 / SP / 注册表；或 smali/PE patch 比较指令。
4. **完整还原**：算法可逆或可伪造时写 keygen。
5. **纯云端强校验**：抓包确认 API 仍拒 → 标类型 D；**本地已开的功能仍算 hook 成功**，不要整单否定。

Android hook：

```bash
# 仓库根目录。未知机不要 spawn，交给 safe-attach 按 PID 附加
frida-safe-android/scripts/safe-attach.sh <包名> vip-license-re/scripts/frida-vip-hooks.js
```

Hook 时注意：Frida 里 `this.method()` 会递归；用 overload 引用 `.call(this, ...)` 调原实现。

APK 持久 patch 粗流程：

```bash
apktool d app.apk -o app-smali
# 改 isVip/checkLicense 等方法的返回常量
apktool b app-smali -o app-patched.apk
# 对齐 + 签名后再装
```

PE patch：在校验 `JZ/JNZ` 或 `test eax,eax` 后改跳转；macOS 样本若涉及签名提醒 `codesign --force --deep --sign - TARGET`。

### 5) 验证绕过是否「真开」

| 检查 | 通过标准 |
|---|---|
| UI | 会员标识/锁消失 |
| 本地功能 | 离线也能用原 VIP 能力 |
| 网络功能 | 对应 API 返回 200 且业务数据可用 |
| 持久 | 杀进程/重装策略后仍有效（按目标声明） |

只过 UI、API 仍失败 → 类型 D，写入局限，不要当完整破解。

## 交付格式（每次必给）

```markdown
# <样本名> VIP/卡密验证分析

## 1. 样本与架构类型
- 文件 / 包名 / 版本：
- 架构类型：A–G
- 壳/混淆：

## 2. 验证流程图
（入口 → 采集 → 变换 → 判定 → 落库 → 门闩）

## 3. 关键点
| 位置 | 作用 | 备注 |
|---|---|---|
| ... | 门闩/算法/落库/联网 | 偏移或方法名 |

## 4. 算法 / 协议
- 卡密或 token 结构：
- 关键材料：
- 服务端角色：

## 5. 绕过 PoC
- 路线：hook / patch / 改存储 / keygen
- 步骤与命令：
- 验证结果：UI / 本地功能 / API

## 6. 局限
- 服务端仍校验的接口：
- 重装/换机/到期后的行为：
```


## Magisk / LSPosed / ZygiskFrida（持久化优先）

有 Magisk+LSPosed 时，**优先做持久 hook，不要先改包重签**：

1. **LSPosed 模块**（推荐）：Java `IXposedHookLoadPackage` 钩目标包自己的本地门闩。安装 APK → Manager 勾选模块并限定作用域到目标包 → 重启。
2. **ZygiskFrida**：在 gadget 配置里指定 `app_name`，脚本模式指向本仓库的 `scripts/frida-vip-hooks.js`，启动 App 自动跑 hook，无需 PC attach。
3. **smali 改包**：无 Magisk 时再用 apktool；签名变化需卸载重装，且可能触发完整性校验。

## Agent 纪律

1. 先定性架构类型，再动手绕过；**复合样本先写三层表**（登录门 / 权益门 / 执行引擎）。
2. APK 先读 `droid-asc`，不要默认 `jadx` 全量。
3. 安卓 Frida 先读 `frida-safe-android`；未知机先 PID attach。脚本结构跟 `rev-frida`。
4. Electron：CDP/DevTools 验证门闩与路由；Win 样本优先真机/WSL-Win 动态，勿只停在 macOS 解包。
5. 产出落到 `artifacts/vip-license-re/`，回复只摘要。
6. 类型 D 必须写明「客户端可绕、服务端仍拦」；**本地 RPA/浏览器引擎可 hook 强开时不得用「必须联网/必须付费」当停手理由**。
7. 登录墙若免费：主动登录（或请用户点一下），再继续 VIP hook；口令未知时可伪造会话探 UI，但交付须标「非真会话」。
8. 发现硬编码密钥、卡密盐、RSA 私钥、激活 token、**运行时 OEM 基址** → 记入交付，并按 `gap-resource-collision` 登记。
9. 用户只要「原理」时仍给出绕过面评估；用户只要「绕过」时仍先给 5 行流程摘要再上 PoC。

## 参考

- `references/hunt-keywords.md` — 猎杀词表与架构信号
- `references/bypass-matrix.md` — 类型 → 绕过优先级
- `scripts/frida-vip-hooks.js` — 通用 VIP 门闩 hook 模板
- `scripts/hunt_license_strings.sh` — 本地样本字符串初筛
- `../droid-asc/SKILL.md` — APK 交叉引用与按需反编译
- `../jadx/SKILL.md` — 全量 Java 树，排在 ASC 之后
- `../apktool/SKILL.md` — 解包、smali、重打包
- `../frida-safe-android/SKILL.md` — 安卓 Frida PID attach
- `../rev-frida/SKILL.md` — hook 脚本写法
- `../gap-resource-collision/SKILL.md` — 钥匙与缺口登记
- `../scripts/ensure-tools.sh` — 环境自检，缺工具自动安装
