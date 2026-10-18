/* memfd_shim.c — LD_PRELOAD 拦截 libc::syscall()
 * rustFrida v29/v33 在 arm64 调 memfd_create 用了错误号 385(0x181),
 * 而正确号是 279(0x117), 导致 agent.so 无法加载(ENOSYS)。
 * 本 shim 把 nr==385 改成 279, 其余原样转发, 让 rustFrida 在 KSU 下能注入系统进程。
 *
 * 编译(mac NDK):
 *   NDK=~/Library/Android/sdk/ndk/<ver>/toolchains/llvm/prebuilt/*/bin
 *   $NDK/aarch64-linux-android24-clang -shared -fPIC -o memfd_shim.so memfd_shim.c
 * 使用:
 *   adb push memfd_shim.so /data/local/tmp/
 *   adb shell "su -c 'setenforce 0; LD_PRELOAD=/data/local/tmp/memfd_shim.so \
 *      /data/local/tmp/rustfrida --pid <PID> -l hook.js; setenforce 1'"
 */
#define _GNU_SOURCE
#include <stdarg.h>

/* 真实 syscall: ARM64 内联汇编, 不走 libc(避免递归) */
static long real_syscall(long nr, long a, long b, long c, long d, long e, long f) {
    register long x8 __asm__("x8") = nr;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    register long x5 __asm__("x5") = f;
    __asm__ volatile ("svc 0"
        : "+r"(x0)
        : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
        : "memory", "cc");
    return x0;
}

/* 覆盖 bionic 的 syscall(long number, ...) */
long syscall(long nr, ...) {
    va_list ap;
    long a, b, c, d, e, f;
    va_start(ap, nr);
    a = va_arg(ap, long);
    b = va_arg(ap, long);
    c = va_arg(ap, long);
    d = va_arg(ap, long);
    e = va_arg(ap, long);
    f = va_arg(ap, long);
    va_end(ap);

    /* rustFrida 错调的 memfd_create 号 385 -> 正确 279 */
    if (nr == 385) nr = 279;

    return real_syscall(nr, a, b, c, d, e, f);
}
