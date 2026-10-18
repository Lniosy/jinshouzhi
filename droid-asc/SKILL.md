---
name: droid-asc
description: >
  SRC漏洞挖掘、渗透测试、红队、bug bounty 碰到 Android APK 时的第一选择，优先于 jadx。
  用 Droid ASC 按需反编译并做全 DEX 交叉引用（string/type/method/field）。
  先 findrefs 搜硬编码密钥/URL/JWT/token/apiKey/接口，再 getclass 只反编译命中类。
  触发：APK、安卓App、安卓逆向、挖洞、SRC、渗透、红队、硬编码、密钥、接口、
  xref、findrefs、getclass、Droid ASC、mobile app。
  不要用它解包资源/改包（apktool）。全量源码树才用 jadx，且必须先跑完 ASC。
  ASC 不在时包装脚本会调用仓库 scripts/ensure-tools.sh asc 自动克隆并安装依赖。
---

# Droid ASC

**SRC / 渗透 / 红队碰到 APK：先读本 skill，先跑 ASC。禁止一上来 jadx 全量反编译。**

按需查 APK：先 `findrefs` 定位引用，再 `getclass` 只反编译命中的类。零预处理，适合大包。

仓库：https://github.com/MG1937/ASC  
克隆位置由 `ASC_ROOT` 决定，默认是本仓库的 `.tools/ASC`。虚拟环境建在克隆目录里，不要在 skill 目录再造一份。

## 启动命令

在仓库根目录用包装脚本：

```bash
droid-asc/scripts/asc <args...>
```

未设置 `ASC_ROOT` 时，脚本走 `<仓库根>/.tools/ASC`。等价于：

```bash
"$ASC_ROOT/.venv/bin/python" "$ASC_ROOT/main.py" <args...>
```

工作目录任意。**Agent 只用 CLI，不要开 `--gui`。**

## 和 jadx / apktool 怎么选

| 目标 | 用 |
|---|---|
| 搜字符串 / 类型 / 方法 / 字段引用 | **ASC `findrefs`** |
| 只要某几个类的 Java | **ASC `getclass`** |
| 全量 Java 源码树、资源、Manifest 浏览 | jadx |
| 解包资源、改 smali、重打包 | apktool |

**SRC / 渗透 / 红队默认：先 ASC。** 全量导出、用户点名整棵树、或只要 Manifest/资源浏览 → 再 jadx / apktool。

## 标准流程

```
确认 APK 路径
    │
    ├─ 已知类名 ──────────────► getclass 反编译
    │
    └─ 只知道关键字/API ─────► findrefs 搜引用
                                   │
                                   ▼
                            从命中行取出类名
                                   │
                                   ▼
                              getclass 看实现
```

1. 确认 `.apk` 存在，记下绝对路径。
2. 先搜后反编译。不要一上来全量 jadx。
3. 结果写到工作区，例如 `artifacts/asc/`，不要只打在终端里就结束。
4. 引用结果可能很多：先看前几十行，必要时收窄关键词，再决定反编译哪些类。

SRC / 渗透第一轮至少搜这些（每个词单独一次 `findrefs string`，输出到 `artifacts/asc/`）：

`http` `https` `apiKey` `api_key` `secret` `token` `Authorization` `eyJ` `AKIA` `AIza` `firebase` `password`

再加目标域名关键字。命中后对高频调用类 `getclass`。

## 类名规则

`getclass` 的第二个参数是 Dalvik 类名。包装脚本和 `main.py` 都接受这两种：

| 输入 | 实际查询 |
|---|---|
| `com.poc.Main` | `Lcom/poc/Main;` |
| `Lcom/poc/Main;` | 原样 |

内部类用 `$`：`com.poc.Main$Inner`。  
`findrefs --class` 默认也按完整类名；只记得短名时加 `--fuzzy-class`。

## 命令

把 `<apk>` 换成绝对路径。线程默认 8，大包可 `--threads 16`。

### 反编译一个类

```bash
droid-asc/scripts/asc getclass <apk> com.poc.Main -o artifacts/asc/Main.java
```

stdout 和 `-o` 都会写出 Java。类不存在时退出码非 0，stderr 类似 `Class L...; not found in APK.`

### 搜引用

```bash
# 字符串（模糊）
droid-asc/scripts/asc findrefs <apk> string token -o artifacts/asc/string_refs.txt

# 类型
droid-asc/scripts/asc findrefs <apk> type com.poc.Main -o artifacts/asc/type_refs.txt

# 方法：至少给 --class 或方法名之一
droid-asc/scripts/asc findrefs <apk> method onCreate --class com.poc.Main -o artifacts/asc/method_refs.txt
droid-asc/scripts/asc findrefs <apk> method notify --class MainActivity --fuzzy-class -o artifacts/asc/method_refs.txt

# 字段
droid-asc/scripts/asc findrefs <apk> field apiKey -o artifacts/asc/field_refs.txt
```

### 调试耗时

任意子命令加 `--debug`。

## 引用输出格式

每行：

```
classes.dex | Lcom/poc/Main;->onCreate | matched=(token)
```

| 段 | 含义 |
|---|---|
| `classes.dex` | 命中的 DEX（可能是 `classes2.dex` 等） |
| `L...;->name` | **引用发生的方法**（调用方） |
| `matched=(...)` | 实际匹配到的字符串 / 类型 / 方法 / 字段 |

同一方法里多个匹配会合成一行，`matched=` 里用 `; ` 分隔。

从引用行取类名做 `getclass`：取 `L...;` 里 `;->` 前面那段。

## Agent 纪律

1. 先读本 skill，再跑命令。不要手写 Python 调 ASC 内部 API。
2. 不要 `--gui`。用户明确要看界面时，只告诉他这条，自己仍用 CLI：
   ```bash
   droid-asc/scripts/asc <apk> --gui
   ```
3. 不要把整份 `findrefs` 原文贴进回复。摘要：命中数量、高频类、再反编译的 3～10 个类。
4. 输出文件用 utf-8。Java 里的乱码按 `errors=replace` 处理过，以文件为准。
5. 当前仓库如果是 Windows exe / 非 APK，先说明 ASC 只吃 APK，再问 APK 路径。

## 环境自检

直接跑包装脚本即可。ASC 或 venv 缺失时，它会调用 `scripts/ensure-tools.sh asc` 克隆上游并安装依赖。只检查、不安装：

```bash
ENSURE_CHECK_ONLY=1 scripts/ensure-tools.sh asc
```

装好的位置默认是仓库 `.tools/ASC`，可用 `ASC_ROOT` 覆盖。GUI 缺 Tk 时才需要 `python-tk`，CLI 不需要。不要改去用别的反编译器，除非用户同意。
