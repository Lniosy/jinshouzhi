/*
 * trace_device_info.js —— 追踪「设备指纹/硬件标识」采集行为
 *
 * 在目标 app 进程内 hook 一批读取硬件唯一标识的系统 API,打印返回值 + Java 调用栈,
 * 用于定位「是哪个 SDK / 哪一步在采集设备信息」(IMEI、IMSI、android_id、MAC、序列号等)。
 *
 * 配合 safe-attach.sh(只按 PID 附加,不碰 system_server):
 *   safe-attach.sh <包名> hooks/trace_device_info.js
 *
 * 说明:Android 10+ 普通应用大多已拿不到 IMEI/IMSI/真实MAC/序列号(系统返回空/抛异常),
 *      这正好能在日志里看出「SDK 尝试采集但被系统拦截」的真实情况。
 */
Java.perform(function () {
    function stack() {
        return Java.use("android.util.Log")
            .getStackTraceString(Java.use("java.lang.Exception").$new());
    }
    function trace(clsName, method, label) {
        try {
            var cls = Java.use(clsName);
            cls[method].overloads.forEach(function (ov) {
                ov.implementation = function () {
                    var ret = ov.apply(this, arguments);
                    console.log("\n[采集] " + label + "  ->  " + ret);
                    console.log(stack());
                    return ret;
                };
            });
            console.log("[+] hooked " + label);
        } catch (e) {
            console.log("[-] 跳过 " + label + " (" + e + ")");
        }
    }

    // —— 电话/SIM 类标识 ——（需 READ_PHONE_STATE;Android10+ 多被限制）
    trace("android.telephony.TelephonyManager", "getDeviceId",        "TelephonyManager.getDeviceId(IMEI)");
    trace("android.telephony.TelephonyManager", "getImei",            "TelephonyManager.getImei");
    trace("android.telephony.TelephonyManager", "getSubscriberId",    "TelephonyManager.getSubscriberId(IMSI)");
    trace("android.telephony.TelephonyManager", "getSimSerialNumber", "TelephonyManager.getSimSerialNumber(ICCID)");
    trace("android.telephony.TelephonyManager", "getLine1Number",     "TelephonyManager.getLine1Number(本机号码)");

    // —— ANDROID_ID ——（Settings.Secure.getString(cr, "android_id")）
    try {
        var Secure = Java.use("android.provider.Settings$Secure");
        Secure.getString.overload("android.content.ContentResolver", "java.lang.String")
            .implementation = function (cr, key) {
                var ret = this.getString(cr, key);
                if (key && key.toLowerCase().indexOf("android_id") >= 0) {
                    console.log("\n[采集] Settings.Secure ANDROID_ID  ->  " + ret);
                    console.log(stack());
                }
                return ret;
            };
        console.log("[+] hooked Settings.Secure.getString(ANDROID_ID)");
    } catch (e) { console.log("[-] 跳过 ANDROID_ID (" + e + ")"); }

    // —— WiFi MAC / 序列号 ——
    trace("android.net.wifi.WifiInfo", "getMacAddress", "WifiInfo.getMacAddress(MAC)");
    try {
        var Build = Java.use("android.os.Build");
        // Build.getSerial() 需特权;Build.SERIAL 是字段,这里 hook 方法形式
        if (Build.getSerial) {
            Build.getSerial.implementation = function () {
                var ret = this.getSerial();
                console.log("\n[采集] Build.getSerial()  ->  " + ret);
                console.log(stack());
                return ret;
            };
            console.log("[+] hooked Build.getSerial()");
        }
    } catch (e) { console.log("[-] 跳过 Build.getSerial (" + e + ")"); }

    console.log("\n=== 设备信息采集追踪已就绪,去 app 里走登录/支付等流程,观察 [采集] 日志 ===\n");
});
