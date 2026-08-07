import subprocess
import shutil
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

# =============================
# 2. 用户输入 DXF 文件处理
# =============================
USER_DXF = None

if len(sys.argv) > 1:
    USER_DXF = Path(sys.argv[1]).resolve()

    if not USER_DXF.exists():
        raise FileNotFoundError(f"DXF 文件不存在: {USER_DXF}")

    if USER_DXF.suffix.lower() != ".dxf":
        raise ValueError(f"不是 DXF 文件: {USER_DXF}")

    # 清理旧文件
    if SOURCE_DXF.exists():
        SOURCE_DXF.unlink()

    # 复制用户 DXF → source.dxf
    shutil.copy(USER_DXF, SOURCE_DXF)
    print(f"📁 使用 {USER_DXF.name} 作为 source.dxf")

else:
    if not SOURCE_DXF.exists():
        raise FileNotFoundError(
            "未提供 DXF 文件，且 source.dxf 不存在。\n"
            "用法示例：python main.py your_file.dxf"
        )
    print("📁 使用已有 source.dxf")

# =============================
# 3. 提取文本（直接读原始 DXF：TEXT / MTEXT / 块属性）
# =============================
print("=== Step 1: Extract TEXT / MTEXT / ATTRIB ===")
subprocess.run([sys.executable, str(DXF_XTRACT_SCRIPT)], check=True)
print("✅ texts.json generated.")

# =============================
# 4. 批量翻译
# translation_cache.json 按原文缓存译文，已翻译过的文本会自动跳过，
# 因此天然支持增量翻译，无需额外判断。
# =============================
print("=== Step 2: Translate ===")
subprocess.run([sys.executable, str(TRANSLATE_SCRIPT)], check=True)

# =============================
# 5. 回写翻译结果
# =============================
print("=== Step 3: Update DXF with translation ===")
subprocess.run([sys.executable, str(UPDATE_SCRIPT)], check=True)

# =============================
# 6. 清理临时文件
# =============================
for f in [SOURCE_DXF] + STALE_FILES:
    if f.exists():
        f.unlink()

print("🧹 已清理临时 DXF 文件")
print("✅ All steps completed successfully.")
print(f"📦 Output DXF: {OUTPUT_DXF.name}")
