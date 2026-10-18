# 猎杀词表与架构信号

配合主 skill 第「猎杀关键字 / 验证架构分类」使用。命中后按信号归类 A–G。

## 通用关键字

```text
vip VIP isVip is_vip isPremium premium member membership 会员 开通会员
license Licence serial SerialKey activation activate 卡密 激活码 授权码 注册码
expire expiry expired validUntil valid_thru trial 试用 到期 过期
checkLicense verifyLicense unlock paywall purchase restore
```

## Android 额外

```text
SharedPreferences  getBoolean("isVip"  putBoolean("vip
BillingClient  queryPurchases  acknowledgePurchase
getPackageInfo  signatures  PackageManager
AndroidID  Settings$Secure  TelephonyManager
```

## Windows / 桌面额外

```text
HKEY_CURRENT_USER  Software\\  RegSetValue  RegQueryValue
GetVolumeInformation  GetComputerName  CryptVerifySignature
license.dat  .lic  activation.json
```

## Electron / 商户 SaaS

```text
app.asar  app-64.7z  Nullsoft  electron-builder
ipcMain  ipcRenderer  electron-store  shopToken  shop_token
end_time  isExpire  cms_number  salememu  uuinfo  webHost
MainBaseUrl  GETOEMCONFIG  cardshop  activi_code
playwright  storageState  page.evaluate  msedge
```

## 架构信号速查

| 看到… | 倾向类型 |
|---|---|
| 无网络权限 / 无激活域名，本地 `if (isVip)` | A 纯本地 |
| 输入框 → 长函数里循环/查表/CRC，无 HTTP | B 本地算法 |
| 激活成功后写 `token`/`expireAt` 到文件，以后离线读 | C 在线激活落本地 |
| 每次进功能都请求 `/user/vip` 或带会员 header | D 每次在线 |
| 比较 `firstLaunch` + `now` / `InstallTime` | E 试用时间锁 |
| 卡密校验吃 `deviceId`/`machineCode` | F 硬件绑定 |
| 包名含 `revenuecat` / 国内发卡 SDK / `LicenseSDK` | G 第三方 SDK |
| `end_time`/`cms_number` + 本地 Playwright/RPA IPC | **A+D 复合**（权益云、引擎本地） |
| `activi_code` + 设备列表，另有账号到期 | 座位码 ≠ 软件 VIP，分开画 |

## 追 xref 优先级

1. 用户可见错误串：「卡密错误」「已过期」「账号已到期」「请开通会员」「密码错误」「异地登录」
2. 布尔门闩：`isVip()` / `isPremium()` / `checkLicense()` / `isExpire`（先读赋值语义）
3. 写入点：`putBoolean` / `fwrite` / `RegSetValue` / `localStorage.shopToken`
4. 网络：`activate` / `verify` / `redeem` / `uuinfo` / `salememu`；并核对 **OEM 实际 host**
5. 执行引擎：`playwright` / `storageState` / `page.locator` vs 私有协议 / 纯云 API
