#!/usr/bin/env bash
# 统一入口：找到装有 laya 的 Python 并运行 classify.py。
# 用法: ./run.sh scan --apply | ./run.sh scan | ./run.sh judge <path>
# 换环境: LAYA_PYTHON=/path/to/python ./run.sh ...
set -euo pipefail

# -P：经软链安装时也落到仓库真实目录（config/相对候选路径都认这里）
cd -P "$(dirname "$0")"

candidates=(
  "${LAYA_PYTHON:-}"
  ".venv/bin/python"
  "$HOME/Desktop/project/.venv-laya/bin/python"  # 本机开发环境，他人可忽略
  "python3"
  "python"
)

for py in "${candidates[@]}"; do
  [ -n "$py" ] || continue
  command -v "$py" >/dev/null 2>&1 || continue
  # 只探测包是否存在，不真 import（import laya 会拖 5s+ torch）
  if "$py" -c 'import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("laya") else 1)' 2>/dev/null; then
    exec "$py" classify.py "$@"
  fi
done

{
  echo "未找到装有 laya 的 Python。"
  echo "  pip install -r requirements.txt     # 或指定环境："
  echo "  export LAYA_PYTHON=/path/to/python"
} >&2
exit 1
