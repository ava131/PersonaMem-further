# WildChat-250

本数据集来自 WildChat-1M（https://huggingface.co/datasets/allenai/WildChat-1M ，ODC-BY 许可）：这是由 Allen Institute for AI 等机构收集的 100 万段真实用户与 ChatGPT（GPT-3.5 / GPT-4）的对话，来自一个面向公众的免费 ChatGPT 服务，每条记录包含完整的 user/assistant 消息序列和会话开始时间戳，用于研究真实场景下的多轮对话分布与服务性能。我们从中取 train-00013 分片在 2024-04-02 15:18–16:14 UTC 窗口内的前 250 轮请求（来自 134 个真实会话），按 timestamp 排序回放，同一会话的轮次连续排列；每条请求的文本是从会话开头到当前 user 消息的完整拼接，消息以 "user:" / "assistant:" 标注，因此同一会话第 k+1 轮的输入严格以第 k 轮为前缀，可直接用于考察多轮前缀复用、KV cache 命中与 offload 场景。构造过程不做长度筛选、不做内容过滤；gsm8k 与 longbenchv2 中的 answer、question 和选项均为空占位，仅供缓存/性能测试，不用于准确率评分。


250 条真实多轮对话请求流，来自 **WildChat-1M** 的一个时间窗口。

- 数据源：https://huggingface.co/datasets/allenai/WildChat-1M （ODC-BY）
- 分片：`train-00013-of-00014`
- 时间窗口：2024-04-02 15:18 → 16:14 UTC（约 56 分钟）
- 取前 **250 轮**请求，来自 **134 个真实会话**，按 `timestamp` 排序、同一会话的轮次连续排列
- 不做长度筛选、不做内容过滤

## 结构

每个请求的 `question` / `context` 是从会话开头到当前 user 消息的完整文本，格式：

```
user: ...

assistant: ...

user: ...
```

因此同一会话的第 k+1 轮以第 k 轮为严格前缀。

## 统计

| 项 | 值 |
|---|---:|
| 请求数 | 250 |
| 会话数 | 134 |
| 可命中请求（各会话第 2 轮起） | 116 |
| 命中比例 | 46.4% |
| token 最小 | 3 |
| token 中位 | 469 |
| token 平均 | 1,289 |
| token 最大 | 10,239 |

语言：英语 149、俄语 40、他加禄语 23、日语 10、葡萄牙语 7。

## 文件

| 文件 | 说明 |
|---|---|
| `gsm8k.jsonl` | 250 行，`{"question": 文本, "answer": ""}` |
| `longbenchv2.jsonl` | 250 行，`context`=文本，其余为空占位 |
| `requests.meta.jsonl` | 每行：pos / conversation_hash / timestamp / model / language / turn_index / tokens |

## 注意

- 这是**缓存性能测试数据**，`answer`、`question`、选项为空占位，不能用于准确率评分；
- 内容是真实用户输入，未过滤 toxic / redacted，使用前请按需过滤；
- token 数用 Qwen tokenizer 统计，不含 system prompt 与 chat template。
