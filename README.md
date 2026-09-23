# obsidian-classify

用本地 laya 模型给 Obsidian 笔记自动分类，并顺带判断有没有长期价值。
写完一篇丢进 `00 收件箱`，说一句「分类笔记」（或跑一条命令）就归位；
拿不准的留在原地等你手动处理，绝不乱挪。

它同时是一个 **OpenCode 技能**：仓库根目录的 `SKILL.md` 就是技能定义，
克隆进技能目录即可让 AI 助手按需调用。

## 安装为技能

```bash
git clone https://github.com/adra2n/obsidian-classify.git \
  ~/.config/opencode/skills/obsidian-classify
cd ~/.config/opencode/skills/obsidian-classify
pip install -r requirements.txt
cp config.example.yaml config.yaml
# 编辑 config.yaml：vault 改成你的库路径，categories 的 folder 对齐你的文件夹名
```

装好后直接对 OpenCode 说「分类笔记」「整理收件箱」「笔记归位」即触发。

## 手动用法

```bash
./run.sh scan --apply   # 分类并移动
./run.sh scan           # 只预演，不动文件（默认 dry-run）
./run.sh judge notes/   # 只判断不移动 —— 拿真实笔记试效果
```

`run.sh` 自动寻找装了 laya 的 Python，也可以显式指定：

```bash
export LAYA_PYTHON=/path/to/python
./run.sh scan --apply
```

`scan` 默认 **dry-run**，必须显式加 `--apply` 才会真的移动文件。

## 它做什么

1. 读收件箱里的 `.md`（跳过 `_` 和 `.` 开头的）
2. 取**标题 + 正文预览 + 现有标签**，一次问模型两个问题：
   分类、长期价值
3. 分类置信度够高 → 从配置的文件夹里选一个最像的，移动过去
   （文件夹不存在会自动创建）；置信度不够 → 留在收件箱，下次再说
4. 在 frontmatter 里写入 `category` / `confidence` / `value_score`
5. 其他笔记里指向它的**带路径** `[[链接]]` 同步改成新路径；
   被移动笔记的文件名和正文本身一个字不动

## 分类目标

固定 8 类，文件夹名以你的 `config.yaml` 为准（下面是默认值）：

| 类别 | 默认文件夹 | 大概是什么 |
|---|---|---|
| `meeting` | `01 会议纪要` | 会议记录、讨论纪要、行动项 |
| `work` | `02 工作文档` | 工作报告、总结、方案、项目 |
| `tech` | `03 技术文档` | 技术、编程、运维、架构、排障 |
| `study` | `04 学习笔记` | 课程、培训、技能、考证 |
| `reading` | `05 读书笔记` | 书籍笔记、书单、文章精读 |
| `life` | `06 生活记录` | 生活、日记、健康、家庭 |
| `collect` | `07 资料收集` | 剪藏、参考资料、调研素材 |
| `idea` | `08 想法灵感` | 想法、灵感、点子、草稿 |

只在这 8 个里选——模型偶尔会吐出别的词，会被代码拦下来留置。
`config.py` 拒绝超过 10 类：laya 的 choice:6-10 桶已校准，第 11 类以上未校准。

## 价值判断怎么用

模型给 0-3 分和四档 label，`value_norm` 归一到 0-1，和 `value_threshold`（默认 1.0）
比较：低于阈值的**只分类、不打标**，笔记本身照常归位。

它决定的是「值不值得额外做点什么」，比如要不要挂标签方便日后检索。
注意 laya 的价值判断 confidence 实测偏低（多在 0.03-0.14），
低于 0.15 时输出里会带个提醒标——**分数本身比 confidence 可靠**，别只看 confidence。

## 阈值怎么调

- `category_confidence_threshold`（默认 0.25）：分类置信度下限，低了就留置
- `value_threshold`（默认 1.0）：价值分下限，低了就不打标

想让它更可靠，用 `judge --json` 跑一批你熟悉好坏的笔记，看输出的分布再定阈值。
判太松会乱归位，判太严会全留置，两个方向都得试一次。

## 双链安全

移动笔记最危险的不是 `mv` 而是断链，这里的处理是：

- 被移动的笔记：文件名、正文**完全不动**——Obsidian 按文件名（不含路径）
  解析 `[[链接]]`，所以同名不重复的前提下，搬去哪个文件夹裸链接都不断
- 其他笔记里指向它的**带路径** `[[00 收件箱/xxx]]`：全库扫一遍改成新路径，
  改不动的（目标不在库里）原样留着
- 目标重名自动加序号 `xxx (1).md`，绝不覆盖

## 环境

Python 3.10+，`pip install -r requirements.txt`（`laya` + `pyyaml`），模型跑本地。

已知可用组合（Intel Mac x86）：

```
Python 3.11.13 / laya 0.3.6 / torch 2.2.2 / transformers 4.48.3 / pyyaml 6.0.3
```

x86 Mac 装不上 torch 2.5+，pip 解析失败时按上面固定版本。
模型冷启动约 19s，`state_mode: full` 单篇推理约 4-5s。
模型文件默认走 HuggingFace 缓存，不在本地时：
`huggingface-cli download convaiinnovations/laya`。

## 配置

`config.yaml` 不入库（含你的库路径），从模板复制：

```bash
cp config.example.yaml config.yaml
```

| 键 | 说明 |
|---|---|
| `vault` | 库根路径（必改） |
| `model` | laya 模型路径 |
| `inbox` | 收件箱文件夹名，默认 `00 收件箱` |
| `categories` | 8 类 → 文件夹映射，folder 可改成你已有的名字 |
| `category_confidence_threshold` | 留置阈值，默认 0.25 |
| `value_threshold` | 打标阈值，默认 1.0 |
| `state_mode` | `full`（读正文，日常）/ `title`（只读标题，快 3 倍但空标题会判错） |

## 项目结构

```
SKILL.md              技能定义（OpenCode 入口）
run.sh                统一入口：找 laya Python → classify.py
classify.py           命令行兼容入口
config.example.yaml   配置模板
requirements.txt
obsidian_classify/
  cli.py        scan / judge 子命令
  config.py     配置加载（拒绝超过 10 类）
  engine.py     laya 封装（一次提问同时拿分类与价值）
  extract.py    读笔记、组 state
  inbox.py      收件箱扫描
  mover.py      移动 + 双链重写
  annotate.py   写 frontmatter
  worker.py     单篇处理编排
```

## 已知限制

- 没有常驻监听（`watch` 子命令已移除）——按需触发，用完即走
- 价值判断的 confidence 普遍偏低，看分数别只看 confidence
- 断链、空索引这类历史遗留问题不处理，留人工
- `state_mode: title` 只在批量迁移提速时用过，日常必须 `full`
