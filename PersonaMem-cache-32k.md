# PersonaMem-v3 32k 缓存工作负载（两个版本）

基于 **PersonaMem-v3** 公开数据构造，用于 KV cache / prefix cache 性能测试，**不是准确率数据集**。
正文取自 `backend/<persona>/{chatbot,ai_studio}.json`，按时间排序后做**句子对齐**的 token 前缀切片。

## 构造方法

1. 把每个 persona 的事件文本按时间拼起来；
2. 按句子（`。.!?` 后接空白/换行）切分并逐句 tokenize（Qwen tokenizer）；
3. 找到最接近 **32,768 tokens** 的句界作为第 1 轮正文——**不截断句子**；
4. 之后每轮只追加**连续的完整句子**，累计约 **+100 tokens**；
5. 同一 persona 的第 k 轮文本 = 第 1 轮文本的严格前缀 + 若干整句。

实测（50 个 persona）：

- 首轮句界偏差：中位 4 tokens，最大 17；
- 每段 +100 tokens 的偏差：中位 5，最大 41；
- 22/24 个 persona 两段偏差都 ≤15。

## 两个版本

| 版本 | 条数 | 组成 |
|---|---:|---|
| **A** | 218 | 20 base ×10 次 + 14 独立 + 2 首 + 2 尾 + 5 对离群 |
| **B** | 163 | 20 base ×7/8 次 + 14 独立 + 2 首 + 2 尾 + 4 对离群 |

两个版本都满足：

- **首尾**：位置 0、1 是两条不同的 32k 正文；最后两条（N-2、N-1）分别是它们的**逐字节复制**，间隔整个数据集（约 160 / 216 条），缓存不可能保留；
- **独立条目**：均匀穿插，永不重复；
- **离群值**：每个 gap 各出现一次（按“中间夹的条数”计）。

## 间隔统计

### A（218 条）

- 正常间隔（20 条 base）：n=170，**均值 21.12、中位 22、标准差 3.07**，范围 9–25
- 离群间隔：**0、1、50、100、200** 各 1 条

### B（163 条）

- 正常间隔：n=117，**均值 20.82、中位 22、标准差 3.69**，范围 8–26
- 离群间隔：**0、1、50、100** 各 1 条

## 验证

- 首轮正文句界对齐，正文不以半句结尾；
- 同一 persona 相邻两轮 `next.startswith(prev)` 全部通过；
- `head == tail[-2]`、`head[1] == tail[-1]` 均为 True；
- 独立 persona 各只出现一次。

## 文件

```
generated/PersonaMem-A-218/
├── gsm8k.jsonl          # {"question": 正文, "answer": ""}
├── longbenchv2.jsonl    # context=正文，question/choices/answer 为空占位
└── requests.meta.jsonl  # pos / kind / persona / occ / tokens

generated/PersonaMem-B-163/
├── gsm8k.jsonl
├── longbenchv2.jsonl
└── requests.meta.jsonl
```

## 注意

- 这是**缓存性能数据**，`answer`、`question`、选项都是空占位，不能用于原版 PersonaMem 准确率评分；
- token 长度只针对正文本身，不含 system prompt / chat template / 生成输出；
- tokenizer 使用仓库内 `tokenizer/`（Qwen 系列）；换 tokenizer 会改变长度与选中的 persona。
