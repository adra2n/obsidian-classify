---
name: obsidian-classify
description: Obsidian 笔记自动分类归档 - 用本地 laya 模型读 00 收件箱里的笔记（标题+正文，state_mode: full），判断属于哪 8 类文档之一，按分值最高的一类移入对应文件夹并把 category/confidence/value 写进 frontmatter（阈值 0 时低置信也归档，置信度看 laya_confidence 事后筛查），仅模型未给出有效类别时留在收件箱等人工。当用户说"分类笔记"、"整理收件箱"、"收件箱归档"、"笔记归位"、"把笔记移动到对应文件夹"、"处理一下收件箱"、"Obsidian 分类"、"跑分类"、"这批笔记放哪" 时使用。按需调用，不常驻监听。不处理断链与旧库迁移问题。
---

# Obsidian 笔记分类

把收件箱里的笔记判断类别并移入对应文件夹。全程本地 laya 模型，不联网。
本仓库即技能——克隆到技能目录即完成安装；个人路径只写在 `config.yaml`，不写死在技能里。

## 首次安装

```bash
SKILL_DIR=~/.config/opencode/skills/obsidian-classify
git clone https://github.com/adra2n/obsidian-classify.git "$SKILL_DIR"
pip install -r "$SKILL_DIR/requirements.txt"
cp "$SKILL_DIR/config.example.yaml" "$SKILL_DIR/config.yaml"
# 编辑 config.yaml：vault 改成你的库路径；categories 的 folder 对齐你的文件夹名
```

## 执行

```bash
SKILL_DIR=~/.config/opencode/skills/obsidian-classify

# 1. 先查收件箱 —— 空的直接回复，别白等模型加载
VAULT=$(awk -F': ' '/^vault:/{print $2; exit}' "$SKILL_DIR/config.yaml")
INBOX=$(awk -F': ' '/^inbox:/{print $2; exit}' "$SKILL_DIR/config.yaml")
ls -la "$VAULT/$INBOX/"

# 2. 有笔记才跑（模型冷启动约 19s，full 模式单篇约 4-5s）
"$SKILL_DIR/run.sh" scan --apply
```

- 用户只想看结果、没让动文件时，去掉 `--apply`
- 空收件箱（只有 `_` 开头的索引和 `.gitkeep`）→ 直接回复「收件箱是空的」

## 分类目标（固定 8 类，folder 以 config.yaml 为准）

| 类别 | 默认文件夹 |
|---|---|
| `meeting` | `01 会议纪要` |
| `work` | `02 工作文档` |
| `tech` | `03 技术文档` |
| `study` | `04 学习笔记` |
| `reading` | `05 读书笔记` |
| `life` | `06 生活记录` |
| `collect` | `07 资料收集` |
| `idea` | `08 想法灵感` |

## 判定规则

- **必须结合正文**：`state_mode: full`（标题+标签+标题层级+正文预览）。
  别改成 title 模式——空标题笔记（如「随手记」）会判错。
- 分类置信度阈值 `category_confidence_threshold`（config.yaml，当前 `0`）：
  **永远按 8 类中分值最高的一类归档**，置信度写进 frontmatter 的
  `laya_confidence` 供事后筛查；只有模型未给出有效类别时才留置。
- 价值分 `< 1.0` → 照常分类移动，只是不打标签。
- 目标文件夹不存在会自动创建；重名笔记加序号，绝不覆盖。

## 输出怎么读

```
笔记                     类别    置信    价值  动作
随手记                   tech   0.385   0.56 移动  → 03 技术文档
某篇                     study  0.180   0.80 移动  → 04 学习笔记（低置信仍归档）
缺类                     (无)   —       —    留置  模型未给出有效类别
```

- `移动`：已归位，frontmatter 写入 `category` / `confidence` / `value_score`
- `留置`：模型未给出有效类别，仍在收件箱，**必须告知用户哪些没归位及原因**
- `失败`：读取或模型报错，报告文件名和错误信息

报告三档统计：移动几篇、留置几篇、失败几篇，并列出留置篇目。

## 明确不做

- 不处理断链、空索引等历史遗留问题——留给用户人工。
- 不主动 `git commit` 用户的库（交给库自己的自动化）。
- 不常驻轮询（`watch` 子命令已移除），只按需扫描一次。
- 移动的笔记本身：文件名与正文不动；只有**其他笔记**里指向它的带路径
  `[[链接]]` 会同步更新路径——这正是不断链的机制。

## 故障排查

- `配置文件不存在` → `cp config.example.yaml config.yaml` 后改 vault
- `vault 不存在` / `收件箱不存在` → 检查 `config.yaml` 的 `vault`
- `模型路径不存在` → 检查 `config.yaml` 的 `model`；可用
  `huggingface-cli download convaiinnovations/laya` 拉取
- 卡在 `加载模型...` 约 19s 属正常，torch 冷启动
- `未找到装有 laya 的 Python` → `pip install -r requirements.txt`，
  或指定环境 `export LAYA_PYTHON=/path/to/python`
