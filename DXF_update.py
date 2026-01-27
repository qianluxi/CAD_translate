import json
from pathlib import Path
import ezdxf

# =========================================================
# 1. 路径配置
# =========================================================
BASE_DIR = Path(__file__).parent
SOURCE_DXF = BASE_DIR / "source.dxf"
OUTPUT_DXF = BASE_DIR / "translated.dxf"
RESULT_JSON = BASE_DIR / "result.json"

# =========================================================
# 2. 读取翻译结果
# =========================================================
with open(RESULT_JSON, "r", encoding="utf-8") as f:
    handle_to_translated = json.load(f)

# =========================================================
# 3. 打开 DXF
# =========================================================
if not SOURCE_DXF.exists():
    raise FileNotFoundError(f"DXF 文件不存在: {SOURCE_DXF}")

doc = ezdxf.readfile(str(SOURCE_DXF))
msp = doc.modelspace()

# =========================================================
# 4. 更新 TEXT / MTEXT / BlockReference
# =========================================================
def update_entity_text(obj):
    """
    根据 handle 更新 TEXT / MTEXT / Attribute
    """
    handle = obj.dxf.handle
    if handle in handle_to_translated:
        new_text = handle_to_translated[handle]
        if obj.dxftype() in ("TEXT", "MTEXT", "ATTRIB"):
            obj.dxf.text = new_text

# ---------- 更新 modelspace ----------
for e in msp:
    if e.dxftype() in ("TEXT", "MTEXT", "ATTRIB"):
        update_entity_text(e)
    elif e.dxftype() == "INSERT":
        # 更新块内 ATTRIB
        for att in e.attribs:
            update_entity_text(att)
        # 块内 TEXT / MTEXT 可以展开处理
        # 如果不想炸开块，可以忽略块内 TEXT / MTEXT
        # 若要严格保持块内部翻译，可按需解开块再翻译
        # for blk_e in e.virtual_entities():
        #     if blk_e.dxftype() in ("TEXT", "MTEXT", "ATTRIB"):
        #         update_entity_text(blk_e)

# =========================================================
# 5. 保存
# =========================================================
try:
    doc.saveas(str(OUTPUT_DXF))
    print(f"✅ Translated DXF saved: {OUTPUT_DXF}")
except PermissionError as e:
    print(f"❌ 无法保存文件，可能被打开: {OUTPUT_DXF}")
    print(e)

print("⚠ 注意：程序不会关闭 DXF，请确保不要同时打开源文件。")
