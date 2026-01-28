import json
from pathlib import Path
import subprocess
import shutil
import sys

# =============================
# 1️⃣ 配置路径
# =============================
BASE_DIR = Path(__file__).parent

DXF_PRUNE_SCRIPT   = BASE_DIR / "dxf_prune.py"
DXF_XTRACT_SCRIPT  = BASE_DIR / "DXF_xtract.py"
TRANSLATE_SCRIPT   = BASE_DIR / "CAD_translate.py"
UPDATE_SCRIPT      = BASE_DIR / "DXF_update.py"

TEXTS_JSON   = BASE_DIR / "texts.json"
RESULT_JSON  = BASE_DIR / "result.json"

SOURCE_DXF      = BASE_DIR / "source.dxf"
TEXT_ONLY_DXF   = BASE_DIR / "text_only.dxf"
OUTPUT_DXF      = BASE_DIR / "translated.dxf"

# =============================
# 2️⃣ 用户输入 DXF 文件处理
# =============================
USER_DXF = None

if len(sys.argv) > 1:
    USER_DXF = Path(sys.argv[1]).resolve()

    if not USER_DXF.exists():
        raise FileNotFoundError(f"DXF 文件不存在: {USER_DXF}")

    if USER_DXF.suffix.lower() != ".dxf":
        raise ValueError(f"不是 DXF 文件: {USER_DXF}")

    # 清理旧文件
    for f in [SOURCE_DXF, TEXT_ONLY_DXF]:
        if f.exists():
            f.unlink()

    # 复制用户 DXF → source.dxf
    shutil.copy(USER_DXF, SOURCE_DXF)
    print(f"📄 使用 {USER_DXF.name} 作为 source.dxf")

else:
    if not SOURCE_DXF.exists():
        raise FileNotFoundError(
            "未提供 DXF 文件，且 source.dxf 不存在。\n"
            "用法示例：python main.py your_file.dxf"
        )
    print("📄 使用已有 source.dxf")

# =============================
# 参数配置
# =============================
incremental = True   # 是否启用增量翻译

# =============================
# 3️⃣ DXF 瘦身（只保留文字）
# =============================
print("=== Step 0: Prune DXF (text only) ===")
subprocess.run(["python", str(DXF_PRUNE_SCRIPT)], check=True)
print("✅ text_only.dxf generated.")

# =============================
# 4️⃣ 提取文本
# =============================
print("=== Step 1: Extract TEXT / MTEXT / ATTRIB ===")
subprocess.run(["python", str(DXF_XTRACT_SCRIPT)], check=True)
print("✅ texts.json generated.")

# =============================
# 5️⃣ 增量翻译（可选）
# =============================
if incremental and RESULT_JSON.exists():
    with open(TEXTS_JSON, "r", encoding="utf-8") as f:
        new_texts = json.load(f)
    with open(RESULT_JSON, "r", encoding="utf-8") as f:
        old_results = json.load(f)

    texts_to_translate = {
        h: t for h, t in new_texts.items()
        if h not in old_results or old_results[h] != t
    }

    if texts_to_translate:
        print(f"⚡ Incremental: {len(texts_to_translate)} items to translate")

        backup_json = BASE_DIR / "texts_backup.json"
        shutil.copy(TEXTS_JSON, backup_json)

        with open(TEXTS_JSON, "w", encoding="utf-8") as f:
            json.dump(texts_to_translate, f, ensure_ascii=False, indent=2)

        subprocess.run(["python", str(TRANSLATE_SCRIPT)], check=True)

        with open(RESULT_JSON, "r", encoding="utf-8") as f:
            new_results = json.load(f)

        old_results.update(new_results)

        with open(RESULT_JSON, "w", encoding="utf-8") as f:
            json.dump(old_results, f, ensure_ascii=False, indent=2)

        shutil.move(backup_json, TEXTS_JSON)
    else:
        print("⚡ Incremental: No new/changed texts. Skipping translation.")

else:
    print("=== Step 2: Full translation ===")
    subprocess.run(["python", str(TRANSLATE_SCRIPT)], check=True)

# =============================
# 6️⃣ 回写翻译结果
# =============================
print("=== Step 3: Update DXF with translation ===")
subprocess.run(["python", str(UPDATE_SCRIPT)], check=True)

# =============================
# 7️⃣ 清理临时文件
# =============================
for f in [SOURCE_DXF, TEXT_ONLY_DXF]:
    if f.exists():
        f.unlink()

print("🧹 已清理临时 DXF 文件")
print("✅ All steps completed successfully.")
print(f"📦 Output DXF: {OUTPUT_DXF.name}")
