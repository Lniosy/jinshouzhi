# rustFrida memfd_create syscall 号 bug 的 LD_PRELOAD 修复

适用:KSU 设备 hook 系统 native 进程(update_engine 等),用 rustFrida 时遇到 `memfd_create 失败: ENOSYS`。

## 现象

rustFrida 注入系统进程,bootstrapper 阶段成功(绕过 KSU ptrace),但加载 agent.so 时失败:
```
[→] pidfd_getfd: pid=... → host_fd=...      ← 成功(绕过 KSU ptrace)
[✗] 注入失败: memfd_create 失败: Function not implemented (os error 38)
```

## 诊断:确认是 syscall 号错误(非内核缺失)

```bash
# 1. 内核其实编译了 memfd_create
adb shell "su -c 'zcat /proc/config.gz | grep CONFIG_MEMFD_CREATE'"   # =y

# 2. strace 看 rustFrida 调的号(应是 279/0x117, 实际调 385/0x181)
adb shell "su -c 'setenforce 0; strace -f -e raw=all /data/local/tmp/rustfrida --pid <PID> 2>&1 | grep -B1 ENOSYS | head; setenforce 1'"
# 输出: syscall_0x181(...) = -1 ENOSYS   ← 0x181=385, 错; 正确 memfd_create=279
```

根因:rustFrida v29/v33 在 arm64 把 memfd_create 号写成了 385(应为 279)。
官方仓库不含 Rust 源码(预编译闭源),无法改源重编译。

## 修复:LD_PRELOAD 把 syscall 号 385 改回 279

rustFrida 经 `libc::syscall(385,...)` 调用(`syscall` 是 UND 动态符号),所以 LD_PRELOAD 一个
同名 `syscall()` 拦截,把 nr 385 改成 279 即可。代码见 `scripts/memfd_shim.c`。

```bash
# 编译(mac NDK,任一版本)
NDK=$(ls -d ~/Library/Android/sdk/ndk/*/toolchains/llvm/prebuilt/* 2>/dev/null | head -1)
"$NDK/bin/aarch64-linux-android24-clang" -shared -fPIC \
    -o memfd_shim.so scripts/memfd_shim.c
adb push memfd_shim.so /data/local/tmp/

# 用 LD_PRELOAD 跑 rustFrida(注意 setenforce 0 + 用完 setenforce 1)
adb shell "su -c 'setenforce 0; LD_PRELOAD=/data/local/tmp/memfd_shim.so \
    /data/local/tmp/rustfrida --pid <PID> -l hook.js; setenforce 1'"
```

修复后注入推进到:`memfd SELinux label → u:object_r:tmpmps:s0`、`agent SO fd 已发送`,
hook 正常安装(实测 hook 到 update_engine 的 SHA256/avb_rsa_verify)。

## hook 脚本注意(rustFrida QuickJS 兼容官方 API,但有坑)

rustFrida 支持 `Interceptor.attach` / `Module.findExportByName` / `Module.enumerateModules`。
**但 `Process.findModuleByName('/system/bin/xxx')` 带完整路径会返回 null** → 用
`Module.enumerateModules()` 遍历按 name/path 匹配拿 base:
```js
var ue = null;
Module.enumerateModules().forEach(function(m){
  if (m.name && m.name.indexOf('update_engine')>=0) ue=m;
});
Interceptor.attach(ue.base.add(0x1121ac), {onEnter:function(){console.log('hit');}});
```
