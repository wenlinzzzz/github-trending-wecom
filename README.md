# GitHub 本周热榜 → 企微群

每周一 09:00（北京时间）抓取 [GitHub 官方 Trending 周榜](https://github.com/trending?since=weekly)，把前 10 个仓库推到企业微信群。

每条包含排名、总星数、本周新增星数、项目介绍和一段使用场景，并附上仓库链接。介绍和场景都是中文。场景会根据仓库说明，写成「它解决什么问题、什么情况下会用」。

## 准备

1. 把这个目录推到 GitHub（公开仓库即可，定时任务不耗付费分钟数）。
2. 在企微群里添加群机器人，复制 Webhook 地址。地址形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...`。
3. 打开仓库 **Settings → Secrets and variables → Actions → Secrets**，新建 `WECOM_WEBHOOK`，值贴上一步的地址。

可选变量（**Variables**，不是 Secrets）：

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `TOP_N` | `10` | 每个榜推几条，1–25 |
| `LANGUAGES` | 空 | 留空只推全语言周榜。多个语言用逗号分隔，例如 `python,typescript,go` |

## 先试一次

**Actions → Weekly GitHub Trending → Run workflow**。成功的话群里会马上收到一条消息。

定时任务只在默认分支上运行。GitHub 的 cron 是 UTC，偶尔会晚几分钟到几十分钟。

本地只看文案、不推送：

```bash
python scripts/push_trending.py --dry-run
python scripts/push_trending.py --dry-run --languages python,go --top 5
```
