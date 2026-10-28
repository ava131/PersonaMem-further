# PersonaMem-B-163

163 条，32k 正文，句子对齐。

- 组成：137 重复 + 14 独立 + 4 首尾 + 8 离群（4 对）
- 正常间隔：均值 20.82、中位 22、标准差 3.69（n=117）
- 离群间隔：0、1、50、100 各 1 条
- 首尾：位置 0/1 与 161/162，尾部为逐字节复制
- 正文 token：32,749 – 33,386

文件：

| 文件 | 说明 |
|---|---|
| `gsm8k.jsonl` | 163 行，`question`=正文，`answer`="" |
| `longbenchv2.jsonl` | 163 行，`context`=正文，其余占位 |
| `requests.meta.jsonl` | 每行 `pos/kind/persona/occ/tokens` |

完整统计见仓库根目录 `PersonaMem-cache-32k.md`。
