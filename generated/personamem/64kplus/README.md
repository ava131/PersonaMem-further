# PersonaMem-v3：超过 64k tokens 的 persona（64kplus）

从 PersonaMem-v3 原始 `backend/` 中提取 `chatbot + ai_studio` 文本长度 **≥ 65,536 tokens** 的全部 persona。

## 结果

- 100 个 persona 中有 **94 个** 超过 64k
- 未入选的 6 个：65 (64,468)、108 (52,878)、90 (49,229)、52 (46,692)、35 (41,933)、93 (32,011)
- 完整正文长度：**66,920 – 290,558** tokens（中位 129,958）

## 文件

| 文件 | 说明 |
|---|---|
| `personas_64k.full.part1.jsonl` / `part2.jsonl` | 94 行完整正文，按 47 / 47 拆成两个 <50 MB 的分片（`persona_id` / `tokens` / `text`） |
| `gsm8k.jsonl` | 94 行，正文按句界截到 **≤ 65,536 tokens**，`{"question": 文本, "answer": ""}` |
| `longbenchv2.jsonl` | 94 行，同样截断，`context`=文本，其余为空占位 |
| `requests.meta.jsonl` | 每行 `pos / persona_id / full_tokens / cut_tokens` |

截断后的长度：**65,432 – 65,536 tokens**，均以完整句子结尾。

## 注意

- 只统计 `chatbot + ai_studio`；若把 Instagram / Facebook / Threads / Calendar 的文本也算上，长度会更大；
- 这是缓存/长上下文性能测试数据，`answer`、`question`、选项为空占位，不用于准确率评分；
- token 数用 Qwen tokenizer 统计，不含 system prompt 与 chat template。

## 分片说明

`personas_64k.full.*.jsonl` 只是原始完整正文，按行数平均拆成两个分片，避免单文件超过 GitHub 建议的 50 MB；使用时把两个文件按行合并即可。
