# WildChat-250（高并发交错回放）

本数据集来自 WildChat-1M（https://huggingface.co/datasets/allenai/WildChat-1M ，ODC-BY 许可）：这是由 Allen Institute for AI 等机构收集的 100 万段真实用户与 ChatGPT（GPT-3.5 / GPT-4）的对话，来自一个面向公众的免费 ChatGPT 服务，每条记录包含完整的 user/assistant 消息序列和会话开始时间戳。我们从中取 train-00013 分片 2024-04-02 时间窗内的真实会话，把每个会话拆成逐轮请求，并为每一轮模拟发送时间（用户思考时间 + 上一条回复的生成时间），再把所有会话的轮次按全局时间合并，形成 250 条**多个会话交错到达**的请求流；每条请求的文本是从会话开头到当前 user 消息的完整拼接，以 “user:” / “assistant:” 标注，同一会话第 k+1 轮的输入严格以第 k 轮为前缀，因此可以直接观察真实内容下的多轮前缀复用、KV cache 命中与 offload 行为。构造过程不做长度筛选、不做内容过滤；gsm8k 与 longbenchv2 中的 answer、question 和选项均为空占位，仅供缓存/性能测试，不用于准确率评分。

## 结构

- 会话之间**交错排列**，相邻请求通常来自不同 session；
- 同一会话内轮次顺序保持不变，turn k+1 以 turn k 为严格前缀；
- 并发度：平均 **12.5** 个会话同时活跃，峰值 **25**（按模拟的发送/结束时间计算）。

## 统计

| 项 | 值 |
|---|---:|
| 请求数 | 250 |
| 会话数 | 143 |
| 可命中请求（各会话第 2 轮起） | 107 |
| 命中比例 | 42.8% |
| token 最小 | 3 |
| token 中位 | 454 |
| token 最大 | 7,596 |

## 文件

| 文件 | 说明 |
|---|---|
| `gsm8k.jsonl` | 250 行，`{"question": 文本, "answer": ""}` |
| `longbenchv2.jsonl` | 250 行，`context`=文本，其余为空占位 |
| `requests.meta.jsonl` | pos / session / turn / time_s / real_start / model / language / tokens |

## 注意

- 这是**缓存性能测试数据**，`answer`、`question`、选项为空占位，不能用于准确率评分；
- 内容是真实用户输入，未过滤 toxic / redacted，使用前请按需过滤；
- `time_s` 是为形成并发而模拟的相对时间（秒），`real_start` 保留原始会话开始时间；
- token 数用 Qwen tokenizer 统计，不含 system prompt 与 chat template。
