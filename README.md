# PersonaMem-further

将已发布的 **PersonaMem-v3 正文**转换为多会话、固定轮转顺序、精确 token 长度的缓存性能工作负载。无需模型推理，也无需重新生成 PersonaMem。

默认：20 个独立 persona/session，3 轮，首轮 32,768 tokens，每轮新增 100 tokens。共 60 条请求：

| 行号 | session | 轮数 | 正文 tokens |
|---|---|---|---|
| 1–20 | 0–19 | 1 | 32,768 |
| 21–40 | 0–19 | 2 | 32,868 |
| 41–60 | 0–19 | 3 | 32,968 |

第 21 条 = 第 1 条 + 100 tokens，第 41 条 = 第 21 条 + 100 tokens。相邻两次同 session 请求之间有 19 条其他请求。`--requests-per-round 23` 对应 23 个 session，A 的位置是 1、24、47；若中间需要恰好 23 条其他请求，设置 24。

## 环境与快速运行

Python 3.9+；仅加载 tokenizer，不下载模型权重。不需要 GPU、PyTorch 或模型 API key。

```bash
cd /path/to/PersonaMem-further
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 下载 24 个 persona 的现成聊天/陪伴文本，给筛选留余量。
HF_HOME=.cache/huggingface .venv/bin/python convert.py download --personas 24

HF_HOME=.cache/huggingface .venv/bin/python convert.py build \
  --tokenizer Qwen/Qwen3-32B \
  --rounds 3 \
  --requests-per-round 20 \
  --initial-tokens 32768 \
  --increment-tokens 100 \
  --format both \
  --output-dir generated/r3_n20_l32768_d100

HF_HOME=.cache/huggingface .venv/bin/python convert.py verify \
  --output-dir generated/r3_n20_l32768_d100
```

本次用户提供的名称为 `qwen3.8-32b`，未确认到该确切模型 ID，因此当前默认使用已确认的 **`Qwen/Qwen3-32B`**。这不是声称两者 tokenizer 相同。请与实际服务模型对齐；可以通过 `--tokenizer /本地/tokenizer/目录` 或任何兼容的 Hugging Face tokenizer ID 替换，替换后重新生成。项目 `tokenizer/` 若已存在，可使用 `--tokenizer ./tokenizer` 离线加载。

默认会保留 tokenizer 与原数据的版本/指纹；下载只发生在 `download` 和远程 tokenizer 首次加载时。HF token 如需使用，从环境读取，不写进报告。

## 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `--rounds` | 3 | 每个 session 的请求轮数 |
| `--requests-per-round` | 20 | 独立 session 数；每轮各发一次 |
| `--initial-tokens` | 32768 | 首轮正文精确 token 数 |
| `--increment-tokens` | 100 | 每次追加的精确 token 数 |
| `--format` | both | `longbenchv2`、`gsm8k` 或 `both` |
| `--data-dir` | 项目下 data | 下载根目录或本地 backend 目录 |
| `--apps` | chatbot ai_studio | 文本来源 app，可加 instagram facebook threads |
| `--persona-ids` | 自动筛选 | 固定 persona ID，逗号分隔 |
| `--seed` | 42 | 可重复的 persona 选择和截取偏移 |
| `--tokenizer-revision` | 默认分支 | 模型仓库 commit/tag；用于固定版本 |
| `--block-size` | 16 | 验证首轮共享完整前缀块使用的块大小 |
| `--max-first-prefix-tokens` | 8 | 任意两条首轮正文允许的最大共同前缀，必须小于 block-size |
| `--offset-attempts` | 1024 | 为寻找可精确切分的原文起点最多尝试的偏移数量 |
| `--emit-token-ids` | 关闭 | 在 metadata sidecar 中额外保存规范 input_ids |

不同长度/轮数输出到不同目录。已有输出拒绝覆盖，避免误删结果。数据不足会明确报错，不会重复 persona、重复文本或用 padding 凑长度。大量轮数可能找不到所有切口都可逆的原文起点，此时增加原数据/offset-attempts 或调整长度；不会静默改变目标长度。

## 输出文件与格式

- `longbenchv2.jsonl`：完整字段名结构，正文在 `context`。
- `gsm8k.jsonl`：`{"question": "正文", "answer": ""}`。
- `requests.meta.jsonl`：逐行对应，含 session、轮次、精确长度、上一条行号、内容哈希等。
- `manifest.json`：参数、源文件哈希、tokenizer 指纹、筛选和重叠统计。
- `verification.json`：`verify` 重新读取最终文件并 tokenize 后生成的验证结果。

两种格式中的正文逐行完全一致。metadata 不混进模型输入，避免变化的 request ID 破坏缓存命中。

**这是格式兼容的缓存性能数据，不是原版 LongBench-v2/GSM8K 准确率题库。**`answer`、LongBench 题目和选项为空占位，未伪造 ground truth；`difficulty=easy` / `length=long` 是格式标签，不是官方难度/长度评估。不可用官方准确率评分器解释其结果。若现有 loader 要求非空答案或从答案推导输出长度，需要将 loader 改为性能模式，并显式指定固定生成 token 数。

## 精确长度与缓存条件

1. 长度定义为对 `context`（LongBench-v2）或 `question`（GSM8K）执行目标 tokenizer 的 `encode(..., add_special_tokens=False)`。不含 system prompt、chat template、MCQ 包装和生成输出。
2. 从每个独立 persona 的正文按时间排序，抽取自然的连续 token 切片；不加入画像、偏好标签或标准答案。选择起点后，每轮只扩展同一段原文。
3. 每个切片都执行 decode→encode 检查，必须恢复原 token IDs，且文本和 token 都严格包含上一轮完整正文。避免 UTF-8 字符和 BPE 边界带来的“看似 +100、实际不是 +100”。
4. 首轮所有 session 两两验证最长共同前缀。默认最多 8 tokens，因此正文层面在 16-token block 下不共享完整前缀块。这不禁止普通词语重复，也不承诺系统提示词零命中。
5. 这不是将上一轮实际生成回答加入历史的对话评测；新增内容来自原始数据的后续正文。

**回放时必须保持 JSONL 行顺序，关闭 shuffle、输入截断和随机采样。**若要严格保持执行轮转关系，先使用顺序回放/并发 1；高并发会影响实际完成顺序与驱逐。为生成输出预留 max_model_len 空间。

如果需要“整个模型输入”精确 32k，请让回放器直接使用正文 token IDs（可开启 `--emit-token-ids`），或把实际模板加入计数后重做校验。标准 chat template 会在正文末尾附加 assistant 标记；后续请求会在该位置换成新增正文，因此只能承诺**旧正文前缀**复用，不能承诺包括旧模板尾部的整个输入也复用。LongBench 的标准题目/选项包装也同理。

对于 hybrid 模型，token 前缀一致不代表对应 recurrent state 一定存在：保存边界、准入/驱逐策略与恢复逻辑必须在推理引擎中另外验证。脚本不声称某个策略必然胜出。

## 验证与来源

```bash
PYTHONPYCACHEPREFIX=.cache/pycache .venv/bin/python -m unittest -v test_convert.py
```

源码：https://github.com/bowen-upenn/PersonaMem-v3

数据：https://huggingface.co/datasets/bowen-upenn/PersonaMem-v3 （数据卡标注 CC-BY-NC-4.0；本项目的派生文本沿用源数据使用条件。）

LongBench-v2 字段：https://github.com/THUDM/LongBench#data-format

GSM8K 字段：https://huggingface.co/datasets/openai/gsm8k

论文中建议称为“基于 PersonaMem-v3 文本的受控多会话缓存工作负载”，并明确长度、追加方式、轮转顺序是自定义实验参数。
