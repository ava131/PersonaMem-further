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

我们取 `chatbot` 与 `ai_studio` 两个 app 的可见文本，按时间排序后作为每个 persona 的连续正文。这类文本是自然的多轮对话与随笔，适合做长上下文切片。

## 3. 两版数据集

| | A | B |
|---|---:|---:|
| 条数 | **218** | **163** |
| 命中率 | **81.19%**（177/218） | **75.46%**（123/163） |
| token 最小 | 32,749 | 32,749 |
| token 中位 | 33,152 | 32,974 |
| token 平均 | 33,142 | 33,018 |
| token 最大 | 33,675 | 33,386 |

命中率 =（总条数 − 独立请求数 − 每个重复 prompt 的首次出现数）/ 总条数。
独立 prompt 永不重复；每个重复 prompt 的第一次出现时缓存里还没有它的前缀，也不可能命中，因此一并剔除。

## 4. 注意

- 这是**缓存性能测试数据**：`answer`、`question`、选项都是空占位，不能用于 PersonaMem-v3 的准确率评分；
- 原始数据为 CC-BY-NC-4.0，本工作负载作为其衍生数据沿用相同许可；
- token 长度只统计正文本身，不含 system prompt、chat template 和生成输出；换 tokenizer 会改变长度和选中的 persona。

## 5. 在 218 条基础上扩展的三个版本

以 A（218 条）为基准，向其中均匀插入不会命中的请求：

- 其中约 2/3 为**独立无重复** prompt（新 persona，32k 正文）；
- 约 1/3 为**间隔 ≥40** 的重复（复用已有 base，插入位置与上一次出现相距 ≥40）；
- 插入位置均匀分散在整条流中，尾部两条复制保持在最后。

| 版本 | 总条数 | 独立 | 大间隔(≥40) | token 范围 | 命中率 |
|---|---:|---:|---:|---|---:|
| A-238 | 238 | 13 | 7 | 30,880 – 32,768 | 81.51% |
| A-248 | 248 | 20 | 10 | 30,880 – 32,768 | 79.03% |
| A-268 | 268 | 33 | 17 | 30,880 – 32,768 | 75.75% |

由于新增请求均匀穿插，原有 base 的间隔被整体拉长：

| 版本 | 间隔均值 | 间隔中位 |
|---|---:|---:|
| A（基准） | 21.12 | 22 |
| A-238 | 25.20 | 24 |
| A-248 | 26.48 | 25 |
| A-268 | 28.66 | 27 |

命中率口径与第 3 节一致：（总条数 − 独立请求数 − 每个重复 prompt 的首次出现数）/ 总条数。
