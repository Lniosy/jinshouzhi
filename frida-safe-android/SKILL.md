---
name: frida-safe-android
description: Run Frida on Android WITHOUT rebooting the device. Activate when the user wants to hook/attach Frida to an Android app, run frida-server, trace device-fingerprint or network calls at runtime, or when a device (especially Xiaomi HyperOS / Android 14+/16, ARMv8.5 PAC SoC) reboots/crashes when starting frida. Default to PID attach on unknown devices, but trust real crash logs over fixed doctrine. Also covers the KSU-Rust-Frida (kfm / rustFrida) Magisk/KernelSU module — a single-binary frida-server replacement that solves boot-loop / 卡logo natively and supports zymbiote spawn + HTTP RPC.
---

# frida-safe-android — 安卓 Frida 防重启工作流

`scripts/safe-attach.sh` 启动前会跑仓库 `scripts/ensure-tools.sh frida`：本机没有 `frida` / `adb` 就安装，手机已连接且 `/data/local/tmp` 没有同版本 `frida-server` 就下载并 push。只检查：`scripts/ensure-tools.sh --check frida`。装完后 `PATH` 要包含仓库 `.tools/bin`。

在新机型(尤其小米 HyperOS / Android 14~16、骁龙 8Gen+ 等带 PAC 指针认证的 SoC)上,
直接用 frida 常见命令**可能**让整机软重启。本 skill 的目标不是死记硬背某几条禁令,
而是先用**真实 crash 日志**判断当前设备/Frida 版本到底会不会崩,再选最稳的路径。

## 零、先看证据,不要盲信 skill

这份 skill 只能当**默认经验**，不能当真理。优先级永远是:

1. **当前设备的实测结果**
2. **dropbox / tombstone / crash log**
3. **当前 Frida 版本的官方变更**
4. skill 里的保守默认值

如果实测和 skill 冲突,**改 skill**,不要硬套旧规则。

## 一、2026-06-25 实测更新（Redmi K70 / vermeer）

实测环境:

- 设备: Redmi K70 (`vermeer`)
- 系统: HyperOS `OS3.0.302.0.WNKCNXM`
- Android: `16`
- Root: Magisk
- 芯片特征: ARM64 + PAC

### 1) 官方 Frida 16.7.19 —— 会重启

在这台机子上,**官方 `frida-server 16.7.19` 即使用空脚本 + PID attach 也会把 `system_server` 打崩**。
关键证据:

```text
getprop sys.runtime.reboot.reason.last
ne#system_server#...#unhandled

>>> system_server <<< signal 11 (SIGSEGV)
fault addr 0x11
backtrace:
#00 pc 0000000000002784 <anonymous:79a6c02000>
```

这说明旧版官方 Frida 在此环境下,问题**不只**是 `frida -U -f` 或 `frida-ps -Ua`。

### 2) 官方 Frida 17.15.3 —— attach 路径已恢复可用

升级到官方最新 `frida 17.15.3` / `frida-tools 14.10.4` / `frida-server 17.15.3` 后,
下列命令已实测**不会触发重启**:

```bash
frida -U -p <PID> -l noop.js
frida -U -N <包名> -l noop.js
frida-ps -Ua
```

### 3) 官方 Frida 17.15.3 —— spawn 仍不可用

同一环境下,`-f` 不再把系统打崩,但仍然**不能正常工作**:

```bash
frida -U -f <包名> -l noop.js -q -t 12
```

返回:

```text
Failed to spawn: unable to locate android.os.Process.setArgV0() slot; please file a bug
```

**当前结论（只对这个已验证配置成立）**:

- 官方 Frida **可用于 attach**
- 官方 Frida **暂不可用于 spawn**
- 需要“启动前注入”时,改用 **Frida Gadget** 或 **rustFrida**

## 二、为什么会重启(根因)

在**旧版 Frida**或**某些 Android 14+/HyperOS + PAC 机型组合**上,
`frida-ps -Ua`、`frida -U 包名`、`frida -U -f 包名`(spawn-gating)、"取前台应用"等操作,
可能会让 frida **往 `system_server` 注入 agent** 去问 ActivityManager 要应用列表/前台信息。
如果这段注入代码在当前系统上不兼容,就会 **SIGSEGV(空指针)**,
把 system_server 打崩 → Zygote/整个 Java 框架重启 → 表现为"重启"。

典型 tombstone 特征(用于确诊):
```
>>> system_server <<<   signal 11 (SIGSEGV)  fault addr 0x...
backtrace:  #00 pc ....  <anonymous:....>     ← 匿名可执行内存=注入的agent
```
配合 `/data/local/tmp/frida-server.log` 出现
`timed out while waiting for syscall on ActivityManager/android.anim thread` 即可坐实。

## 三、默认铁律（未知环境先这样）

1. **先用最新官方 Frida**，不要先拿旧版结论下判断。
2. **第一次测试优先 PID attach**:`frida -U -p <PID>`。PID 用 `adb shell pidof`(走 /proc,不经 frida)拿。
3. app 自己先用 `am start`/`monkey` 起好,再附加。
4. 如果 PID attach 仍会重启,再把 `frida-ps -Ua`、`-N`、`-f` 视为高风险路径。
5. 每次测试后都回看 `getprop sys.runtime.reboot.reason.last` 和 dropbox,别凭感觉判断。

## 四、标准操作(一条命令)

```bash
# 启动 frida-server(自动匹配本地 frida 版本)+ 拉起目标 app + 按 PID 附加 + 挂 hook
scripts/safe-attach.sh <包名> [hook.js]

# 例:空脚本确认 attach 不会重启，再换自己的 hook
scripts/safe-attach.sh <包名> scripts/hooks/noop.js
```

`safe-attach.sh` 做的事(默认走**跨设备最保守**路径):
1. 校验 adb 设备;
2. 在设备 `/data/local/tmp` 下挑一个**版本与本地 `frida --version` 匹配**的 frida-server 并(若未运行)后台启动;
3. `pidof` 拿 PID;拿不到就 `monkey -p <包名> 1` 把 app 拉起再 `pidof`;
4. `frida -U -p <PID> -l <hook.js>` 附加。

## 五、手动版(脚本不可用时)

```bash
# 0. 版本必须一致!否则常见报错是 "unable to communicate"
frida --version                      # 本地
adb shell 'su -c "ls /data/local/tmp | grep frida"'   # 设备端选同版本

# 1. 启 server
adb shell 'su -c "/data/local/tmp/frida-server-<版本> -D &"'

# 2. 拿 PID —— 默认先用 adb
PID=$(adb shell pidof <包名> | tr -d '\r')
[ -z "$PID" ] && adb shell monkey -p <包名> 1 >/dev/null 2>&1 && sleep 3 && PID=$(adb shell pidof <包名> | tr -d '\r')

# 3. 只按 PID 附加
frida -U -p "$PID" -l hook.js
```

> 未知环境第一次测试时,只想拿 PID 列表仍建议先用 `adb shell ps -A | grep <关键字>`。
> 但在 **Redmi K70 / HyperOS 3 / Android 16 / Frida 17.15.3** 这个已验证配置上,
> `frida-ps -Ua` 已实测可用,不需要再把它当成绝对禁令。

## 六、内置 hook 模板(scripts/hooks/)

- `noop.js` —— 空脚本，只用来确认 PID attach 不会把设备打重启。
- `trace_device_info.js` —— 追踪设备指纹采集:`TelephonyManager.getDeviceId/getSubscriberId/getSimSerialNumber`、
  `Settings.Secure ANDROID_ID`、`WifiManager.getMacAddress`、`Build.SERIAL`,打印调用栈,
  定位哪个 SDK 在取硬件标识。
- 自定义时,**只 hook 目标 app 自己的类**,不要 hook 安卓框架/系统服务里的方法。

## 七、万一又重启了 —— 复盘取证

```bash
adb shell 'su -c "cat /data/local/tmp/frida-server.log"'
adb shell 'su -c "ls -lt /data/system/dropbox/ | head"'        # 找 system_server_native_crash@*
adb shell 'su -c "zcat /data/system/dropbox/system_server_native_crash@*.txt.gz"' | head -40
adb shell 'getprop sys.runtime.reboot.reason.last'             # ne#system_server#...#unhandled = frida打崩了框架
```
若仍崩:

1. **先升级到当前最新官方 Frida 再复测**；
2. 若最新官方版 **PID attach 已正常**,但 `-f` 失败,把它当成 **spawn 路径故障**,不是“Frida 整体不可用”；
3. 若最新官方版 **PID attach 仍会重启**,再改用 **Frida Gadget** 或 **rustFrida**；
4. 若目标只是看采集/上报,直接改用 **logcat / Reqable 抓包**。

## 八、何时干脆别用 frida

如果目标只是"看采集/上报了什么字段",优先 **Reqable/mitm 抓包** + **logcat**,
零注入、零重启风险,信息往往已经够用。frida 仅在需要"改返回值/绕过校验/dump 内存"时才上。

## 九、根治方案:换引擎 KSU-Rust-Frida(kfm / rustFrida)

上面 1~8 节是「优先修正官方 Frida 版本,仍不行再退到保守 attach 或替代引擎」。若可刷模块,
还有一条**从机制上根治**的路线:[`references/ksu-rust-frida.md`](references/ksu-rust-frida.md)。

[KSU-Rust-Frida](https://github.com/dreamland-blog/KSU-Rust-Frida) 是一个 KSU/Magisk 模块,
用 Rust 重写的单文件 `rustfrida` 引擎(命令 `kfm`)替代官方 frida-server:

- **不随开机启动**(`service.sh` 只清残留,手动 `kfm start`)→ 不抢 zygote 资源、不卡 logo;
- 单文件 ~3.9MB、内置 QuickJS → 无 V8 版本依赖,告别 `unable to communicate`;
- 原生 **zymbiote spawn**(可 hook `Application.onCreate`)、**watch-so**(eBPF 追 dlopen)、HTTP RPC(端口 28042);
- 三级隐写 NORMAL/WXSHADOW/RECOMP 反检测。

兼容性:仅 ARM64,KernelSU 0.7+/Magisk 24+,Android 9~17。常用命令:
`kfm start` 起引擎 → `kfm inject <包名> hook.js`(attach,最稳)/ `kfm spawn <包名> hook.js`(从启动注入)。

> 迁移老 frida 脚本到 rustFrida 时注意:原方法调用用 `this.$orig()` 而非原函数名(否则无限递归),
> Java hook 用 `.impl`、且全部并入同一个 `Java.perform()` 块。详见参考文档。
> 总原则不变:能抓包/logcat 解决就别注入;真要注入时 attach 优先于 spawn。

## 十、KSU 下 hook 系统 native 进程(update_engine/vold/system_server 等)—— rustFrida 是唯一解

1~8 节针对 **app**。要 hook **系统 native 守护进程**(如挖 OTA/bootloader 漏洞时 attach `update_engine`),
**KSU 设备上官方 frida-server 会直接失败**(这不是第二节的 system_server 枚举问题,已按 PID 仍失败):

```
frida -U -p <PID>  →  Failed to attach: unable to connect to remote frida-server: closed
```

根因是 **KSU 内核 ptrace 防护**拦了 frida-server 对系统进程的 ptrace,`setenforce 0` 也无效。
**唯一解是 rustFrida**(第八节单文件引擎)——它用 `pidfd_getfd` 绕过 KSU ptrace,bootstrapper 能成功附加系统进程。

### 坑:rustFrida v29/v33 有 memfd_create syscall 号 bug

rustFrida 加载 agent.so 时调 `memfd_create`,但在 arm64 用了**错误号 385(0x181)**(正确是 279(0x117))→ `ENOSYS`,
注入卡在 bootstrapper 之后:
```
strace -f -e raw=all rustfrida --pid <PID> 2>&1 | grep ENOSYS
syscall_0x181(...) = -1 ENOSYS    ← 号错; 内核其实有 memfd_create(CONFIG_MEMFD_CREATE=y)
注入失败: memfd_create 失败: Function not implemented (os error 38)
```

### LD_PRELOAD shim 修复(不改源码,rustfrida 闭源也能修)

rustfrida 经 `libc::syscall(385,...)` 调用(`syscall` 是 UND 动态符号),可用 LD_PRELOAD 拦截把号改成 279。
完整代码与一键编译见 [`references/memfd-shim-fix.md`](references/memfd-shim-fix.md) + `scripts/memfd_shim.c`:
```bash
NDK_CC=aarch64-linux-android24-clang  # ~/Library/Android/sdk/ndk/*/toolchains/llvm/prebuilt/*/bin/
$NDK_CC -shared -fPIC -o memfd_shim.so scripts/memfd_shim.c
adb push memfd_shim.so /data/local/tmp/
adb shell "su -c 'setenforce 0; LD_PRELOAD=/data/local/tmp/memfd_shim.so /data/local/tmp/rustfrida --pid <PID> -l hook.js; setenforce 1'"
```
修好后实测可 hook 到 update_engine 的 SHA256/AVB 验证函数。

> **结论**:
> - **未知环境**:官方 Frida 先从 PID attach 开始试
> - **本机已验证环境（Redmi K70 / HyperOS 3 / Android 16 / Frida 17.15.3）**:官方 Frida 可用于 PID attach / `-N` / `frida-ps -Ua`,但 **`-f` spawn 仍不可用**
> - **hook 系统 native 进程**:必须 rustFrida + memfd shim
