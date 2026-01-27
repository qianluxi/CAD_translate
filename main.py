import json
from pathlib import Path
import subprocess
import shutil
import sys

# =============================
# 1️⃣ 配置路径
# =============================
BASE_DIR = Path(__file__).parent

DXF_XTRACT_SCRIPT = BASE_DIR / "DXF_xtract.py"
TRANSLATE_SCRIPT = BASE_DIR / "CAD_translate.py"
UPDATE_SCRIPT = BASE_DIR / "DXF_update.py"
REGEN_CAD_SCRIPT = BASE_DIR / "regen_CAD.py"

TEXTS_JSON = BASE_DIR / "texts.json"
RESULT_JSON = BASE_DIR / "result.json"
OUTPUT_DXF = BASE_DIR / "translated.dxf"
SOURCE_DXF = BASE_DIR / "source.dxf"

# =============================
# 2️⃣ 用户输入 DXF 文件处理
# =============================
if len(sys.argv) > 1:
    USER_DXF = Path(sys.argv[1])
    if not USER_DXF.exists():
        raise FileNotFoundError(f"DXF 文件不存在: {USER_DXF}")
    if USER_DXF.suffix.lower() != ".dxf":
        raise ValueError(f"不是 DXF 文件: {USER_DXF}")

    # 备份用户原文件
    backup = BASE_DIR / f"{USER_DXF.stem}_backup.dxf"
    shutil.copy(USER_DXF, backup)

    # 复制为 source.dxf
    SOURCE_DXF = BASE_DIR / "source.dxf"
    shutil.copy(USER_DXF, SOURCE_DXF)
    print(f"✅ 使用 {USER_DXF.name} 作为 source.dxf，备份保存为 {backup.name}")

else:
    SOURCE_DXF = BASE_DIR / "source.dxf"
    if not SOURCE_DXF.exists():
        raise FileNotFoundError(f"DXF 文件不存在: {SOURCE_DXF}")
    print(f"✅ 使用默认 source.dxf")
# =============================
# 参数配置
# =============================
incremental = True        # 是否启用增量翻译
use_regen_cad = False     # True 调用 regen_CAD.py 回写，False 调用 DXF_update.py

# =============================
# 3️⃣ 提取文本
# =============================
print("=== Step 1: Extract TEXT / MTEXT / Block / Attributes ===")
subprocess.run(["python", str(DXF_XTRACT_SCRIPT)], check=True)
print("✅ texts.json generated.")

# =============================
# 4 增量翻译（可选）
# =============================
if incremental and RESULT_JSON.exists():
    with open(TEXTS_JSON, "r", encoding="utf-8") as f:
        new_texts = json.load(f)
    with open(RESULT_JSON, "r", encoding="utf-8") as f:
        old_results = json.load(f)

    # 找出新增或修改的文本
    texts_to_translate = {
        h: t for h, t in new_texts.items()
        if h not in old_results or old_results[h] != t
    }

    if texts_to_translate:
        print(f"⚡ Incremental: {len(texts_to_translate)} items to translate")
        # 备份完整 texts.json
        backup_json = BASE_DIR / "texts_backup.json"
        shutil.copy(TEXTS_JSON, backup_json)
        # 临时只保留需要翻译的部分
        with open(TEXTS_JSON, "w", encoding="utf-8") as f:
            json.dump(texts_to_translate, f, ensure_ascii=False, indent=2)

        # 调用翻译
        subprocess.run(["python", str(TRANSLATE_SCRIPT)], check=True)

        # 合并翻译结果回原来的 result.json
        with open(RESULT_JSON, "r", encoding="utf-8") as f:
            new_results = json.load(f)
        old_results.update(new_results)
        with open(RESULT_JSON, "w", encoding="utf-8") as f:
            json.dump(old_results, f, ensure_ascii=False, indent=2)

        # 恢复完整 texts.json
        shutil.move(backup_json, TEXTS_JSON)
    else:
        print("⚡ Incremental: No new/changed texts. Skipping translation.")
else:
    print("=== Step 2: Full translation ===")
    subprocess.run(["python", str(TRANSLATE_SCRIPT)], check=True)

# =============================
# 5 回写翻译结果
# =============================
if use_regen_cad:
    print("=== Step 3: Run regen_CAD.py to regenerate DXF ===")
    subprocess.run(["python", str(REGEN_CAD_SCRIPT)], check=True)
else:
    print("=== Step 3: Run DXF_update.py to update DXF with translation ===")
    subprocess.run(["python", str(UPDATE_SCRIPT)], check=True)

print("✅ All steps completed successfully.")
