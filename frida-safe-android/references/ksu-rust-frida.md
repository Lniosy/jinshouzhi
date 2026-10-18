# KSU-Rust-Frida（kfm / rustFrida）—— 从根上不卡 logo 的 Frida 替代引擎

来源：https://github.com/dreamland-blog/KSU-Rust-Frida

`frida-safe-android` 主 SKILL 走的是「保留官方 frida-server,但靠纪律(只按 PID 附加、绝不枚举、绝不 spawn)规避往 system_server 注入而打崩框架」的路线。
**KSU-Rust-Frida** 是另一条路线:用一个 KSU/Magisk 模块把官方 frida-server 换成 Rust 重写的单文件 `rustfrida` 引擎(KSU-Frida Manager,命令行 `kfm`),从机制上解决「开机卡 logo / 与 zygote 竞争资源导致重启」的问题。

适用场景:本机长期做安卓逆向、可刷模块、希望**原生支持 spawn(从 Application.onCreate 起 hook)**、或需要 HTTP RPC 远程调用时。

---

## 一、与官方 frida-server / 本 skill 主路线的区别

| 维度 | 官方 frida-server | rustFrida (kfm) |
|------|------------------|-----------------|
| 二进制 | frida-server + frida-inject 两个 | 单文件 `rustfrida`,约 3.9MB 自包含 |
| JS 引擎 | V8(版本强依赖) | 内置 QuickJS,无版本依赖 |
| 通信 | 命令行 + su | HTTP RPC(默认端口 28042) |
| 开机 | 随开机起,易卡 logo / 抢 zygote 资源 | **不随开机起**,`service.sh` 只清残留,手动 `kfm start` |
| spawn | 易触发 system_server 崩溃(本 skill 禁止) | 原生 zymbiote spawn,劫持 zygote 在 fork 时注入 |
| 反检测 | 无 | 三级隐写 NORMAL / WXSHADOW / RECOMP |

> 注意:即便用 kfm,**主 SKILL 的判断逻辑仍然成立**——"看采集/上报了什么字段"优先抓包+logcat,
> frida 只在需要改返回值/绕校验/dump 内存时才上。kfm 解决的是"引擎层不再把设备搞重启",
> 不改变"能不用注入就不用注入"的总原则。

## 二、系统兼容性

- Root:KernelSU 0.7+ / KSU-Next / Magisk 24+
- 架构:**仅 ARM64**
- Android:9(API 28)~ 17
- 作者验证机型:Pixel 6 Pro(Android 14/16)
- 本机(小米 HyperOS / Android 16 / KernelSU)符合前置条件,可用;ARMv8.5 PAC SoC 上仍建议优先 attach,spawn 谨慎验证。

## 三、安装

```bash
# 1. 推模块包到设备
adb push ksu-frida-manager-v2.0.0.zip /sdcard/Download/
# 2. 用 KSU/Magisk Manager → "从存储安装" 选该 zip
# 3. 重启
adb reboot
# 4. 验证
adb shell "su -c 'kfm version'"
```

### KSU 环境找不到 kfm(overlay 未生效)的修复

```bash
su -c 'cat > /data/adb/ksu/bin/kfm << "EOF"
#!/system/bin/sh
exec sh /data/adb/modules/ksu-frida-manager/system/bin/kfm "$@"
EOF
chmod 755 /data/adb/ksu/bin/kfm'
```

## 四、核心命令

| 操作 | 命令 |
|------|------|
| 启动引擎(按需,重启后需手动执行) | `kfm start` / `kfm start --rpc-port 9191` |
| 注入运行中的应用(attach,**最稳**) | `kfm inject com.example.app script.js` |
| 从启动注入(spawn,可 hook onCreate) | `kfm spawn com.example.app hook.js` |
| 监听 SO 加载时注入(eBPF 追 dlopen) | `kfm watch libnative.so script.js` |
| 设置隐写模式 | `kfm stealth wxshadow` |
| RPC 调用导出函数 | `kfm rpc call myFunc [args]` |
| 看日志 | `kfm log server -f` |
| 停止 | `kfm stop` |

### 注入模式
- **attach**:ptrace 附加到已运行进程,注 ARM64 shellcode 后加载引擎。应用已启动时用,最稳,对应本 skill 主路线的"只按 PID/已起进程附加"。
- **spawn**:注 zymbiote 到 zygote,目标 app fork 时暂停注入,可从第一行代码(含 `Application.onCreate`)hook。
- **watch-so**:eBPF 内核层追 `dlopen`,目标 SO 加载时自动触发,适合 native 库延迟加载。

## 五、JavaScript API 差异(从官方 frida 脚本迁移时注意)

rustFrida 提供 Frida 兼容 API,但有几处**关键差异**,迁移老脚本必看:

```javascript
// Native hook —— 原方法调用必须用 this.$orig(),不能用原函数名,否则无限递归
hook(Module.findExportByName("libc.so", "open"), function (path) {
    console.log("open:", Memory.readCString(ptr(path)));
    return this.$orig();
});

// Java hook —— 用 .impl(等价 .implementation),原方法用 this.$orig()
Java.perform(function () {
    var Activity = Java.use("android.app.Activity");
    Activity.onResume.impl = function () {
        console.log("onResume");
        return this.$orig();
    };
});

// RPC 导出
rpc.exports = { ping: function () { return "pong"; } };
```

迁移要点:
1. 原方法调用一律 `this.$orig(args)`,**不要** `this.methodName(args)`。
2. 所有 Java hook 合并进**同一个** `Java.perform()` 块。
3. `.impl` 与 `.implementation` 等价,任选其一。

## 六、HTTP RPC(PC 端远程调用)

引擎启动后监听 28042(可改):

```bash
# 设备本地
curl http://127.0.0.1:28042/health
curl http://127.0.0.1:28042/sessions
curl -X POST http://127.0.0.1:28042/rpc/0/add -d '[3,4]'   # → {"ok":true,"result":7}

# PC 远程:先 forward
adb forward tcp:28042 tcp:28042
```

## 七、analyze 模式(避免与 zygisk 模块冲突)

```bash
kfm analyze enter      # 禁用冲突模块 → 自动重启
kfm inject com.app hook.js
kfm stop
kfm analyze exit       # 恢复模块 → 自动重启
```

## 八、常见问题

- **重启后引擎没了**:设计如此(防卡 logo),每次重启手动 `kfm start`。
- **rustfrida 启动即退出**:旧版 stdin EOF 导致(REPL 监听 stdin),v2.0.0 已用 FIFO 修复。
- **`unable to communicate` / 版本不匹配**:rustFrida 内置 QuickJS 无 V8 版本依赖,通常不再有官方 server 的版本对不上问题。

## 九、自行构建

```
NDK 25+ / Rust + aarch64-linux-android / Python 3 / 可选 bpf-linker(watch-so)
./build.sh   # 产出 build/ksu-frida-manager-v2.0.0.zip
```
