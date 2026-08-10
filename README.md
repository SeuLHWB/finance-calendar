# 财经日历提醒系统 fincal

每天 08:00 自动推送未来 30 天的重要财经事件预告。零第三方依赖（纯标准库），Windows / Linux / macOS 通用。

---

## 一、微信推送的可行性与前置条件

微信官方**没有**开放"给任意个人微信发消息"的通用接口。所有能落到微信里的方案，本质都是绕道『企业微信』或『某个已认证的服务号』。下面是全部可行路径的实测对比：

| 方案 | 推荐度 | 消息落在哪 | 前置条件 | 关键限制 |
|---|---|---|---|---|
| **企业微信群机器人 Webhook** | ⭐⭐⭐⭐⭐ **首选** | 企业微信 App 的群里 | ① 注册企业微信（个人/小团队也可免费注册，无需营业执照即可创建非认证企业）<br>② 建一个群 → 群设置 → 群机器人 → 添加 → 复制 Webhook URL | • 20 条/分钟限流<br>• markdown 单条 ≤ 4096 字节（本系统已自动分片）<br>• **需要装企业微信 App**，不在微信里<br>• 想让群消息同步到个人微信，需企业通过微信认证并开启"微信插件" |
| **企业微信自建应用消息** | ⭐⭐⭐⭐ | 企业微信 App 的应用会话 | corpid + corpsecret + agentid；**必须配置企业可信 IP 白名单** | • 家用宽带动态 IP 会频繁失效，建议部署在有固定 IP 的云服务器<br>• markdown ≤ 2048 字节 |
| **Server酱³ / Turbo** | ⭐⭐⭐⭐ **上手最快** | **微信 App 内**（"方糖"服务号模板消息） | 微信扫码登录 sct.ftqq.com，复制 SendKey，1 分钟搞定 | • 免费版 **每天 5 条**（本系统每天只发 1 条，够用）<br>• 依赖第三方中转，服务方可见推送内容<br>• 模板消息样式受限，长文折叠为详情页 |
| **WxPusher** | ⭐⭐⭐⭐ | **微信 App 内**（第三方公众号） | 建应用拿 appToken，用户扫码关注拿 UID | 免费额度有限；支持 HTML 正文，排版比 Server酱好 |
| **PushPlus** | ⭐⭐⭐ | **微信 App 内** | 关注公众号获取 token | 免费版限频，高峰期偶有延迟 |
| **自建微信服务号模板消息** | ⭐⭐ | **微信 App 内**，完全自主 | ① **企业主体**的已认证服务号（认证费 300 元/年，个人主体不可申请）<br>② 用户关注并授权拿 openid<br>③ 申请并等待模板审核 | 成本与流程最重；内容需符合模板结构；财经内容易触发合规审核 |
| itchat / wechaty 等个人号协议 | ❌ **不要用** | 微信 | — | 违反《微信个人帐号使用规范》，**封号风险极高** |
| 订阅号群发推文 | ⭐ | 微信 | 有订阅号 | 每天仅 1 次群发、有审核延迟，不适合定时提醒 |

### 推荐组合（按你的场景）

- **只想在微信里收到、且想 5 分钟内跑起来** → `Server酱` 主 + `email` 备。
- **想长期稳定、不限量、内容不过第三方** → `企业微信群机器人` 主 + `Server酱` 备（可同时开启，本系统支持多渠道并发推送）。
- **有云服务器/固定 IP、要推给团队多人** → `企业微信自建应用` 主 + `email` 备。

> 系统已内置的替代渠道：**邮件（SMTP）**、**Telegram**、**钉钉机器人**、**飞书机器人**、**本地文件**。
> 邮件是最稳的兜底——不限量、不依赖任何第三方平台、HTML 排版最完整。

---

## 二、快速开始

```bash
cd finance-calendar

# 1. 预览（不推送，生成 out/preview.html）
python run.py preview --days 30

# 2. 配置推送渠道
copy config\channels.example.json config\channels.json   # Windows
#  cp config/channels.example.json config/channels.json  # Linux/macOS
#  编辑 channels.json，把想用的渠道 enabled 改为 true 并填密钥

# 3. 测试渠道连通性
python run.py channels --test wecom_bot,email

# 4. 立即推送一次
python run.py push

# 5. 注册每日 08:00 定时任务（输出命令，按提示执行）
python run.py install-task --time 08:00
```

## 三、命令一览

| 命令 | 说明 |
|---|---|
| `preview` | 预览事件并生成 `out/preview.html` / `preview.md` / `events.json` |
| `push` | 渲染并推送到所有已启用渠道 |
| `check` | 列出置信度非 high、需要人工核对官方日程的事件 |
| `add` | 手动补录事件 |
| `channels [--test x,y]` | 查看 / 测试推送渠道 |
| `install-task --time 08:00` | 输出 Windows 计划任务 / crontab 安装命令 |

通用过滤参数（可叠加，覆盖配置文件）：

```bash
python run.py preview --days 14 --min-star 4                      # 只看 4 星以上
python run.py push --sectors "AI算力,光模块,锂电池"                 # 只关注指定板块
python run.py push --categories monetary,policy --regions CN,US   # 按类别/地区过滤
python run.py push --channels serverchan                          # 只推指定渠道
```

## 四、目录结构

```
finance-calendar/
├── run.py                      入口
├── config/
│   ├── settings.json           全局配置：时区、窗口、默认过滤、节假日
│   ├── channels.json           推送渠道密钥（自行创建，不入库）
│   ├── channels.example.json   渠道模板 + 每个渠道的申请说明
│   ├── rules.json              ★ 宏观/货币/政策/市场事件的调度规则库
│   └── leaders.json            ★ 分行业龙头名单 + 财报发布规律
├── data/
│   ├── events_manual.json      手动补录事件
│   └── state.json              运行状态与历史
├── fincal/
│   ├── models.py               Event 数据模型
│   ├── tzsupport.py            时区（zoneinfo 优先，内置美/欧夏令时规则兜底）
│   ├── ruleengine.py           日期规则引擎
│   ├── sources.py              规则源 / 手动源 / 财报源 / HTTP 源
│   ├── aggregate.py            去重、过滤、排序
│   ├── render.py               text / markdown / html 渲染
│   ├── channels.py             10 个推送渠道
│   └── cli.py                  命令行
└── out/                        生成的预览与推送快照
```

## 五、事件数据源

### 1）规则库 `config/rules.json`（自动生成，无需联网）

支持 10 种调度规则：

| type | 含义 | 典型事件 |
|---|---|---|
| `fixed_dates` | 官方公布的固定日期表 | FOMC、ECB、BOJ 议息会议 |
| `offset_days` | 相对另一规则偏移 | FOMC 纪要 = 会议 + 21 天 |
| `day_of_month` | 每月固定某日 | 中国 LPR（20 日）、CPI（9 日） |
| `nth_weekday` | 每月第 n 个星期几 | 非农（第一个周五）、四巫日（3/6/9/12 月第三个周五） |
| `nth_business_day` | 每月第 n 个工作日 | ISM 制造业 PMI |
| `last_day_of_month` | 每月最后一日 | 中国官方 PMI |
| `day_window` | 每月某个日期区间 | 社融（9-15 日）、美国 CPI（10-14 日） |
| `annual_window` | 每年某月区间 | 中央经济工作会议（12 月 8-14 日） |
| `month_day` | 每年固定日 | 两会（3/5）、A 股中报截止（8/31） |
| `weekly` | 每周某天 | 美国初请失业金 |

每条规则带 `confidence` 标记：`high` 可直接信任，`medium` / `low` 会在推送里标注"日期待核对"，并可用 `python run.py check` 集中列出。

### 2）龙头财报 `config/leaders.json`

按行业维护"能带动整个板块"的绝对龙头，当前覆盖 9 大行业 30+ 家公司：

`AI算力与半导体`（英伟达/台积电/博通/AMD/阿斯麦/美光/中芯国际/北方华创/中际旭创）、`消费电子`（苹果/立讯/小米）、`软件与云计算`（微软/谷歌/亚马逊/Meta）、`新能源与汽车`（特斯拉/宁德时代/比亚迪/隆基）、`白酒与消费`（茅台/五粮液/沃尔玛）、`互联网（港股）`（腾讯/阿里/美团）、`金融`（摩根大通/中国平安/招商银行/中信证券）、`医药`（礼来/恒瑞/药明康德）、`能源与资源`（埃克森美孚/紫金矿业/长江电力）、`智能制造`（海康/汇川）

字段说明：

```jsonc
{ "code": "NVDA", "name": "英伟达", "market": "US", "importance": 5,
  "session": "amc",                                  // bmo 盘前 / amc 盘后 / mid 盘中
  "anchors": ["02-26","05-28","08-27","11-19"],      // 历年典型发布日（近似）
  "window_days": 5,                                  // 浮动天数 → 生成"预计 x/x - x/x"
  "confirmed": ["2026-08-27"],                       // 已确认的精确日期，优先级最高
  "monthly_day": 10,                                 // 月度营收类（台积电）
  "sectors": ["AI算力","光模块","PCB","液冷温控"],
  "note": "财报后A股算力链常有共振" }
```

新增一家龙头 = 在对应行业数组里加一个对象，无需改代码。`--sectors` 过滤同时匹配行业名与 sectors 标签。

### 3）手动补录 `data/events_manual.json`

```bash
python run.py add --name "中央金融工作会议" --when "2026-10-28" \
  --category policy --region CN --importance 5 \
  --sectors "银行,券商,保险" --confidence low --note "日期待官方公告"
```

### 4）自动抓取 HTTP 源

在 `settings.json → sources.http` 中按 `_http_source_example` 的结构配置任意返回 JSON 的接口，用 `root` + `mapping` 做字段映射即可接入（如东财/新浪/Investing 的日历接口、或你自己的数据服务），无需改代码。

## 六、推送内容示例

每条提醒包含：**日期 + 时间（北京时间 / 源时区双标注）+ 事件名 + 重要性星级 + 预期值/前值 + 影响板块 + 置信度提示**，并在开头给出"本期最需关注" TOP5。

```
【8月28日 周五 · T+18】
  04:20  ★★★★★ 英伟达（NVDA）财报 · 盘后
        影响：AI算力/光模块/PCB/液冷温控/服务器 | 预计 8/22 - 9/1，以公司公告为准
  09:15  ★★★★★ 中国 LPR 贷款市场报价利率
        影响：银行/地产/建材/家电/基建/消费
  20:30  ★★★★★ 美国 PCE 物价指数
        影响：贵金属/美股/美债/美元指数 | 预计 8月26-31日 公布
```

## 七、定时调度

三种方式任选：

**A. Windows 计划任务**（管理员命令提示符）

```cmd
schtasks /Create /SC DAILY /TN "FinCalDailyPush" /ST 08:00 /TR "\"<python路径>\" \"<项目路径>\run.py\" push" /F /RL HIGHEST
```

`python run.py install-task` 会直接打印填好路径的完整命令。

**B. Linux / macOS crontab**

```cron
0 8 * * *  cd /path/to/finance-calendar && /usr/bin/python3 run.py push >> logs/push.log 2>&1
```

**C. WorkBuddy 自动化任务** —— 已注册「财经日历每日推送」，每天 08:00 自动执行。

## 八、维护建议

1. **每年 12 月**核对次年 FOMC / ECB / BOJ / BOE 官方日程，更新 `rules.json` 的 `fixed_dates`（规则里已附官网链接）。
2. **每季度**用 `python run.py check` 扫一遍待核对项，把确认的财报日填进 `leaders.json` 的 `confirmed`。
3. 龙头名单随产业格局变化调整，建议每半年 review 一次。
4. 节假日表在 `settings.json → holidays`，每年更新一次即可让"顺延到下一工作日"的规则保持准确。

## 九、已知边界

- 规则引擎生成的是**日程预告**，不含实时行情与实际值；`prev` / `forecast` 字段留给 HTTP 源或手动填写。
- Windows 缺少 IANA 时区库时自动回退到内置夏令时规则（美国：3 月第二个周日 – 11 月第一个周日；欧盟：3 月最后一个周日 – 10 月最后一个周日），已覆盖本系统全部时区；若需完全精确可 `pip install tzdata`。
- 解禁 / IPO / 龙虎榜等需要实时数据库支撑的事件，建议接 HTTP 源或手动补录。
