# PersonaMem-v3 32k 缓存工作负载说明

## 1. 数据来源

本工作负载基于 **PersonaMem-v3** 公开数据集构造。

- 数据集主页：https://huggingface.co/datasets/bowen-upenn/PersonaMem-v3
- 代码仓库：https://github.com/bowen-upenn/PersonaMem-v3
- 论文：*PersonaMem-v3: Toward Omni-Platform Personal Intelligence for Holistic User Understanding, Recommendation, and Agentic Tasks*（arXiv:2608.21381）
- 作者机构：Meta Recommendation Systems、University of Pennsylvania、MIT
- 许可：**CC-BY-NC-4.0**

PersonaMem-v3 是 PersonaMem 系列的第三代。与 v1/v2 的全合成用户不同，它的行为信号来自 [Meta GIST-Bench](https://huggingface.co/datasets/facebook/gistbench)——约 400 万条脱敏真实社交媒体行为日志，重采样后不指向任何真实个人。

## 2. 内容是什么

本次发布包含 **100 个 persona**，共 **221,817 条行为事件**：

| 来源 app | 事件数 |
|---|---:|
| Instagram | 68,764 |
| Facebook | 67,875 |
| Threads | 68,337 |
| AI Chatbot | 13,190 |
| AI Studio（陪伴角色） | 3,651 |

每个 persona 对应一个 `backend/<persona_id>/` 目录，六个 app 各有一个 JSON 文件：

```
backend/38/
├── chatbot.json      # 与 AI 助手的对话
├── ai_studio.json    # 与陪伴角色的多轮对话
├── instagram.json    # 浏览/点赞/跳过/评论/发帖
├── facebook.json
├── threads.json
└── calendar.json     # 日程与位置
```

每条事件带时间戳，内容包括帖子正文、评论、私信、对话消息等。约 95% 的信号是隐式的（停留、完播、划过），并非用户显式写下的偏好。

我们取 `chatbot` 与 `ai_studio` 两个 app 的可见文本，按时间排序后作为每个 persona 的连续正文。

## 3. 数据集

统一放在 `generated/personamem/` 下，按条数命名；每份包含：

```
generated/personamem/<条数>/
├── gsm8k.jsonl          # {"question": 正文, "answer": ""}
├── longbenchv2.jsonl    # context=正文，其余字段为空占位
└── requests.meta.jsonl  # pos / kind / persona / occ / tokens
```

| 条数 | 独立无重复 | 命中率 | 平均长度（tokens） | 间隔样本 | 间隔均值 | 间隔中位 | 标准差 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 163 | 14 | 75.46% | 31,554 | 121 | 21.41 | 22 | 8.92 |
| 218 | 14 | 81.19% | 31,664 | 175 | 22.55 | 22 | 15.43 |
| 228 | 7 | 84.21% | 31,694 | 178 | 23.76 | 23 | 16.13 |
| 238 | 13 | 81.51% | 31,720 | 182 | 25.20 | 24 | 16.08 |
| 245 | 0 | 81.63% | 32,754 | 200 | 35.00 | 25 | 24.49 |
| 248 | 20 | 79.03% | 31,746 | 184 | 26.17 | 25 | 12.49 |
| 268 | 33 | 75.75% | 31,788 | 189 | 28.01 | 27 | 12.88 |

命中率 =（总条数 − 独立请求数 − 每个重复 prompt 的首次出现数）/ 总条数。

## 4. 间隔分布

单位：条（同一 prompt 相邻两次出现之间夹的请求数）。统计不含首尾复制的那两条 persona。

| 间隔 | 163 | 218 | 228 | 238 | 245 | 248 | 268 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0–10 | 6 | 4 | 5 | 4 | 0 | 4 | 2 |
| 11–15 | 10 | 11 | 8 | 8 | 0 | 8 | 6 |
| 16–20 | 20 | 23 | 14 | 11 | 80 | 10 | 10 |
| 21–25 | 82 | 134 | 139 | 120 | 75 | 93 | 25 |
| 26–30 | 1 | 0 | 7 | 29 | 0 | 57 | 124 |
| 31–40 | 0 | 0 | 0 | 0 | 0 | 0 | 7 |
| 41+ | 2 | 3 | 5 | 10 | 45 | 12 | 15 |
| **合计** | **121** | **175** | **178** | **182** | **200** | **184** | **189** |

说明：

- `41+` 主要来自刻意加入的离群间隔（0/1/50/100/200）以及 238/248/268 版本新增的“大间隔（≥40）”请求；
- 245 是另一种构造：45 条固定 prompt（20 条 a + 25 条 b），按 a×4 + b×3 + a×2 + b×2 的块顺序重复，重复时直接原样复用、不追加 token，因此间隔只有 20 / 25 / 65 / 95 四种；
- 238/248/268 是在 218 条基础上均匀插入不会命中的请求，因此原有 base 的间隔整体右移（均值 21.1 → 25.2/26.2/28.0）。

## 5. 注意

- 这是**缓存性能测试数据**：`answer`、`question`、选项都是空占位，不能用于 PersonaMem-v3 的准确率评分；
- 原始数据为 CC-BY-NC-4.0，本工作负载作为其衍生数据沿用相同许可；
- token 长度是对正文实际 encode 的结果，不含 system prompt、chat template 和生成输出；换 tokenizer 会改变长度和选中的 persona。
