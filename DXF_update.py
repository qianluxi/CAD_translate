import json
from pathlib import Path
import ezdxf

# =============================
# 路径配置
# =============================
BASE_DIR = Path(__file__).parent
SOURCE_DXF = BASE_DIR / "source.dxf"
OUTPUT_DXF = BASE_DIR / "translated.dxf"
RESULT_JSON = BASE_DIR / "result.json"
HANDLE_MAP_JSON = BASE_DIR / "handle_map.json"  # 瘦身DXF → 原始DXF handle映射

# =============================
# 加载翻译结果
# =============================
with open(RESULT_JSON, "r", encoding="utf-8") as f:
    translations = json.load(f)

# =============================
# 加载 handle 映射
# =============================
if HANDLE_MAP_JSON.exists():
    with open(HANDLE_MAP_JSON, "r", encoding="utf-8") as f:
        handle_map = json.load(f)  # {pruned_handle: original_handle}
else:
    # 如果没有映射，则直接用 result.json 的 handle 当原始 handle（兼容旧版本）
    handle_map = {h: h for h in translations.keys()}

# =============================
# 打开原始 DXF
# =============================
doc = ezdxf.readfile(str(SOURCE_DXF))
msp = doc.modelspace()

# =============================
# 更新实体文本
# =============================
def update_entity_text(entity):
    handle = entity.dxf.handle
    # 找到对应的瘦身DXF handle
    pruned_handle = None
    for k, v in handle_map.items():
        if v == handle:
            pruned_handle = k
            break
    if pruned_handle and pruned_handle in translations:
        new_text = translations[pruned_handle]
        if entity.dxftype() == "TEXT" or entity.dxftype() == "ATTRIB":
            entity.dxf.text = new_text
        elif entity.dxftype() == "MTEXT":
            entity.text = new_text

# =============================
# 递归处理块中的实体
# =============================
def process_entities(entities, doc_ref):
    for e in entities:
        if e.dxftype() in ["TEXT", "MTEXT", "ATTRIB"]:
            update_entity_text(e)
        elif e.dxftype() == "INSERT":
            blk_name = e.dxf.name
            if blk_name in doc_ref.blocks:
                blk = doc_ref.blocks[blk_name]
                process_entities(blk, doc_ref)

# =============================
# 更新模型空间
# =============================
process_entities(msp, doc)

# =============================
# 保存输出 DXF
# =============================
doc.saveas(str(OUTPUT_DXF))
print(f"✅ Translated DXF saved: {OUTPUT_DXF.name}")

# 提示：不要在程序里关闭DXF，避免文件锁冲突
print("ℹ️ Please ensure DXF is closed in CAD before opening translated.dxf")
