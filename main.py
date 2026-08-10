import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows GBK 控制台打印 emoji 会触发 UnicodeEncodeError，这里兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# =============================
# 1. 配置路径
# =============================
BASE_DIR = Path(__file__).parent

DXF_XTRACT_SCRIPT = BASE_DIR / "DXF_xtract.py"
TRANSLATE_SCRIPT = BASE_DIR / "CAD_translate.py"
UPDATE_SCRIPT = BASE_DIR / "DXF_update.py"

SOURCE_DXF = BASE_DIR / "source.dxf"
OUTPUT_DXF = BASE_DIR / "translated.dxf"

# 历史版本遗留的临时文件（瘦身 DXF、handle 映射、增量备份），一并清理
STALE_FILES = [
    BASE_DIR / "text_only.dxf",
    BASE_DIR / "handle_map.json",
    BASE_DIR / "texts_backup.json",
]

# 每步最长执行时间，防止 API 卡死导致流程无限等待
STEP_TIMEOUT = 1800


# =============================
# 2. 命令行参数
# =============================
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="CAD DXF 翻译流水线（提取 -> 翻译 -> 回写）")
    parser.add_argument("dxf_path", nargs="?", default=None, help="DXF 文件路径（可选）")
    parser.add_argument("--dxf", dest="dxf_flag", default=None, help="DXF 文件路径（可选）")
    parser.add_argument("--source-lang", default="中文", help="源语言，如：中文 / English / 自动检测")
    parser.add_argument("--target-lang", default="English", help="目标语言，如：English / 中文 / 日本語")
    parser.add_argument("--model", default="", help="ModelScope 模型 ID，留空使用默认模型")
    parser.add_argument("--api-key", default="", help="ModelScope API Key，留空使用环境变量")
    return parser.parse_args(argv)


# =============================
# 3. 子步骤执行
# =============================
def run_step(step_no, total, name, cmd, env=None):
    """打印步骤标记并执行子步骤；失败时明确报错并退出。"""
    print(f"[STEP {step_no}/{total}] {name}", flush=True)
    try:
        subprocess.run(cmd, check=True, timeout=STEP_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] 步骤 {step_no}/{total}（{name}）超时（超过 {STEP_TIMEOUT}s）", flush=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 步骤 {step_no}/{total}（{name}）失败，退出码 {e.returncode}", flush=True)
        sys.exit(1)


# =============================
# 4. 主流程
# =============================
def main(argv=None):
    args = parse_args(argv)
    user_dxf = args.dxf_path or args.dxf_flag

    # ---------- 用户输入 DXF 文件处理 ----------
    if user_dxf:
        user_path = Path(user_dxf).resolve()

        if not user_path.exists():
            raise FileNotFoundError(f"DXF 文件不存在: {user_path}")

        if user_path.suffix.lower() != ".dxf":
            raise ValueError(f"不是 DXF 文件: {user_path}")

        # 清理旧文件
        if SOURCE_DXF.exists():
            SOURCE_DXF.unlink()

        # 复制用户 DXF -> source.dxf
        shutil.copy(user_path, SOURCE_DXF)
        print(f"📁 使用 {user_path.name} 作为 source.dxf", flush=True)

    else:
        if not SOURCE_DXF.exists():
            raise FileNotFoundError(
                "未提供 DXF 文件，且 source.dxf 不存在。\n"
                "用法示例：python main.py your_file.dxf"
            )
        print("📁 使用已有 source.dxf", flush=True)

    # API Key 只通过环境变量传给子进程，避免出现在命令行参数中
    env = os.environ.copy()
    if args.api_key:
        env["MODELSCOPE_API_KEY"] = args.api_key

    # ---------- 提取文本（直接读原始 DXF：TEXT / MTEXT / 块属性）----------
    run_step(1, 3, "提取文本（TEXT / MTEXT / 块属性）", [sys.executable, str(DXF_XTRACT_SCRIPT)], env=env)

    # ---------- 批量翻译 ----------
    # translation_cache.json 按“语言对 + 原文”缓存译文，已翻译过的文本自动跳过，
    # 因此天然支持增量翻译，无需额外判断。
    translate_cmd = [
        sys.executable,
        str(TRANSLATE_SCRIPT),
        "--source-lang", args.source_lang,
        "--target-lang", args.target_lang,
    ]
    if args.model:
        translate_cmd += ["--model", args.model]
    run_step(2, 3, "批量翻译（调用 ModelScope API）", translate_cmd, env=env)

    # ---------- 回写翻译结果 ----------
    run_step(3, 3, "回写翻译结果到 DXF", [sys.executable, str(UPDATE_SCRIPT)], env=env)

    # ---------- 清理临时文件 ----------
    for f in [SOURCE_DXF] + STALE_FILES:
        if f.exists():
            f.unlink()

    print("🧹 已清理临时 DXF 文件", flush=True)
    print("✓ All steps completed successfully.", flush=True)
    print(f"📥 Output DXF: {OUTPUT_DXF.name}", flush=True)


if __name__ == "__main__":
    main()
