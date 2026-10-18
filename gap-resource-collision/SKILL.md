---
name: gap-resource-collision
description: >
  漏洞挖掘「缺口-资源碰撞」机制：维护跨目标共享的缺口账(gaps)与资源账(resources)。
  碰壁挂账、发现钥匙登记、登记即碰撞、会话启动全量配对、验证闭环。
  触发：/collision、挂账、登记缺口、登记资源、无法利用、缺UUID、缺密钥、碰撞、开工简报、跨目标钥匙。
  漏洞挖掘/红队/SRC/小程序审计/hunt 过程中必须持续使用。
---

# 缺口-资源碰撞机制

> 跨目标共享 · 持久化 · 登记即碰撞  
> **主账本**：`~/.local/share/gap-resource-collision/{gaps,resources}.json`  
> **CLI**：`python3 gap-resource-collision/scripts/collision.py`  
> 环境变量 `COLLISION_LEDGER_DIR` 可改账本目录。  
> 没有 `python3` 时，在仓库根目录跑 `scripts/ensure-tools.sh python`，缺了会自己装。

## 职责

漏洞挖掘时，除攻击目标本身，必须维护两本**跨目标共享**账：

| 账 | 登记时机 | 记什么 |
|----|----------|--------|
| **缺口账 gaps** | 攻击面因缺不可猜/不可得的值而卡住 | 缺什么钥匙 |
| **资源账 resources** | 响应/JS/报错/配置出现钥匙型数据 | 这里发什么钥匙 |

同目标内组合靠上下文；**跨目标组合**才是这两本账存在的意义。

## 两条纪律（铁律）

1. **「无法利用」不是结论。** 攻击面卡住只有两种状态：已闭环，或挂账等钥匙。
2. **碰撞只负责提醒，不保证开锁。** 签名密钥撞上加密密钥需求是常态；能不能用必须实际验证。

## 规则

### 规则1 · 碰壁禁止说「无法利用」，必须登记缺口

```bash
python3 gap-resource-collision/scripts/collision.py gap \
  --type identifier \
  --desc "缺他人 conversation UUID，用于 chat 接口 IDOR" \
  --target "TARGET_APP" \
  --surface "/api/chat/detail"
```

| 字段 | 要求 |
|------|------|
| type | `identifier` / `credential` / `internal_info` / `access` |
| description | 缺什么 + 用于哪个攻击面。**越具体碰撞越准** |
| status | `open`（挂账等钥匙） |

### 规则2 · 发现钥匙型数据，必须登记资源

```bash
python3 gap-resource-collision/scripts/collision.py res \
  --type identifier \
  --source "GET /api/items" \
  --desc "响应里的资源 id，可作 IDOR 测试输入" \
  --target "OTHER_APP"
```

### 规则3 · 登记即碰撞（双向）

CLI 在 `gap`/`res` 后自动输出同 type Top5，**跨目标优先**。  
行动提示：**调钥匙接口取值 → 回填缺口攻击面验证**

### 规则4 · 每次会话启动，全量配对

```bash
python3 gap-resource-collision/scripts/collision.py brief \
  --target "当前目标标识"
```

### 规则5 · 验证后闭环

```bash
.../collision.py close --gap gap-0001 --by res-0003 --note "验证通过"
.../collision.py note  --gap gap-0001 --note "这把钥匙不对锁"
```

## 类型

| type | 含义 |
|------|------|
| `identifier` | 各类 ID（orderId / conversation UUID / agent id…） |
| `credential` | 密钥凭证（AES key / AppSecret / session / token…） |
| `internal_info` | 内网 IP、表名、隐藏 path、配置 |
| `access` | 账号、入口、角色、调试页 |

## Agent 行为清单

1. 会话开头：跑 `brief`，写入开工简报  
2. 想说「无法利用」→ 先 `gap`  
3. 拿到钥匙型数据 → 立刻 `res`  
4. 撞上 → 取钥匙 → 回填验证  
5. 结果 → `close` 或 `note 不对锁`

## 存储

```
~/.local/share/gap-resource-collision/
  gaps.json
  resources.json
  brief.md
```

环境变量 `COLLISION_LEDGER_DIR` 可覆盖账本目录。
