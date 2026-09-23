# obsidian-classify

用本地 laya 模型给 Obsidian 笔记自动分类，并顺带判断这篇笔记有没有长期价值。

写完一篇丢进 `00 收件箱`，后台监听到就自动归位；拿不准的留在原地等你手动处理，绝不乱挪。

## 安装

依赖 Python 3.11 + laya 0.3.6 + torch 2.2.2（x86_64 macOS 上 torch 不能升 2.5+）。模型需已下载到本地缓存：

```bash
/Users/adrain/Desktop/project/.venv-laya/bin/python classify.py --help
```

`config.yaml` 里的 `model` 指向已有的 laya 快照目录，`vault` 指向目标笔记本。

## 用法

```bash
# 扫一次收件箱（默认 dry-run，只预演不动文件）
python classify.py scan

# 确认没问题后实际执行
python classify.py scan --apply

# 常驻监听：写完丢进收件箱就自动处理
python classify.py watch --apply

# 只判断不移动 —— 上线前拿真实笔记试效果
python classify.py judge /path/to/notes --json out.json

# 跑一批样本看置信度/价值分布，用来定阈值
python classify.py calibrate --limit 100
```

`scan` 和 `watch` 默认都是 **dry-run**，必须显式加 `--apply` 才会真的移动文件。

## 它做什么

1. 读收件箱里的 `.md`（跳过 `_` `.` 开头的，索引文件不碰）
2. 一次 `system_one` 同时问两个问题：**属于哪一类** + **有多大长期价值**
3. 分类置信度 ≥ 阈值 → 移进目标文件夹，同时重写全库受影响的带路径双链，并把判断结果写进 frontmatter
4. 置信度不足 → 留在收件箱等人工，只打印不改动

移动不会覆盖重名文件，会自动追加 ` (1)` ` (2)`。重复执行是幂等的。

## 分类目标

8 个互斥类别，对应笔记本的 8 个顶层目录（`00 收件箱`、`09 模板`、`10 附件` 不参与分类）：

| 类别 | 目标文件夹 |
| --- | --- |
| `meeting` | `01 会议纪要` |
| `work` | `02 工作文档` |
| `tech` | `03 技术文档` |
| `study` | `04 学习笔记` |
| `reading` | `05 读书笔记` |
| `life` | `06 生活记录` |
| `collect` | `07 资料收集` |
| `idea` | `08 想法灵感` |

**为什么是 8 类**：laya 的 `choice` 选项数落在哪个温度桶决定置信度是否已校准。`choice:6-10` 桶温度 1.0 属校准区间，`choice:11+` 桶被 clamp 到 0.1006 属未校准——加到第 9 类以上会得到不可信的置信度。`config.py` 会拒绝超过 10 类的配置。

同理，选项描述要短：全部选项文本共用 `head_max_len=192`，超长直接抛 `ValueError`。

## 价值判断怎么用

用 `score` 类型打 0–3 分（4 档，落在已校准的 `score:3-5` 桶），结果写进 frontmatter：

```yaml
laya_category: 技术文档
laya_confidence: 0.3478
laya_value: 0.70          # 归一化到 0-1
laya_value_label: 2 中：有参考意义，会回看
laya_value_confidence: 0.1087
laya_reviewed: 2026-09-23
laya_moved_to: 03 技术文档
```

**要留意**：实测价值判断的 `confidence` 普遍只有 0.03–0.14，比分类置信度还低。`购物清单` 这种内容也会被打成"中等"。所以：

- 分数**低于** `value_threshold` 时可信度相对更高，可以拿来筛掉明确的无价值笔记
- 分数**高**不代表真的是好笔记，别单凭它做归档决策
- `confidence < 0.15` 时 label 会自动追加"（模型拿不准，仅供参考）"

想让它更可靠，先用 `calibrate` 跑一批你熟悉好坏的笔记，看分布再定阈值。

## 阈值怎么调

`config.yaml` 两个阈值：

- `category_confidence_threshold`（默认 0.25）：低于此值留在收件箱。实测清晰的技术笔记 0.32、模糊笔记 0.13、旧库历史分布 0.04–0.49。调高→更多笔记需人工，调低→更多笔记可能归错类
- `value_threshold`（默认 1.0）：`score` 期望分 0–3，低于此判定低价值

`calibrate` 会直接给出"想让约 2/3 自动归位该设多少"的参考值。

## 双链安全

移动笔记最大的风险是断链。裸文件名双链 `[[某笔记]]` 由 Obsidian 自行解析，移动后不受影响；但带路径的 `[[00 收件箱/某笔记]]` 会失效。

`mover.rewrite_links` 会在移动后扫全库，把这些带路径双链改到新位置，同时处理 `|别名`、`#标题`、`.md` 后缀几种写法。`.obsidian/` 和 `.git/` 内的文件不碰。

## 项目结构

```
obsidian_classify/
  config.py     配置加载与合法性校验（类别数、路径展开）
  extract.py    笔记解析：frontmatter、标题、标签、摘要
  engine.py     laya 封装，一次 system_one 问两个问题
  mover.py      移动 + 双链重写 + 重名兜底
  annotate.py   判断结果写回 frontmatter
  worker.py     单条处理编排：判断→决策→移动/留置
  watch.py      收件箱轮询
  cli.py        scan / watch / judge / calibrate
```

## 已知限制

- 输入被截断到 512 token，只看标题、标签、标题层级和前 400 字摘要，长文的后半部分不参与判断
- 没有 `fswatch`/`watchdog`，监听靠轮询（默认 5s），千级笔记量可忽略
- 价值判断置信度低，见上文
- `system_one` 返回的 `act_probability` 恒为 1.0，暂未用到 escalate 逻辑
