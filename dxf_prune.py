import ezdxf
from pathlib import Path
import json

# =============================
# 路径配置
# =============================
BASE_DIR = Path(__file__).parent
SOURCE_DXF = BASE_DIR / "source.dxf"
PRUNED_DXF = BASE_DIR / "text_only.dxf"
HANDLE_MAP_JSON = BASE_DIR / "handle_map.json"

# =============================
# 打开原始 DXF
# =============================
doc = ezdxf.readfile(str(SOURCE_DXF))
msp = doc.modelspace()

# =============================
# 创建瘦身 DXF
# =============================
pruned_doc = ezdxf.new(dxfversion=doc.dxfversion)
pruned_msp = pruned_doc.modelspace()

# 保存 handle 映射 {pruned_handle: original_handle}
handle_map = {}

# =============================
# 复制 TEXT / MTEXT / ATTRIB
# =============================
def prune_entities(entities, pruned_msp, doc_ref):
    for e in entities:
        dxftype = e.dxftype()
        if dxftype in ["TEXT", "MTEXT", "ATTRIB"]:
            # 复制到瘦身DXF
            if dxftype == "TEXT":
                new_e = pruned_msp.add_text(
                    e.dxf.text,
                    dxfattribs={
                        "insert": e.dxf.insert,
                        "height": e.dxf.height,
                        "rotation": e.dxf.rotation,
                        "layer": e.dxf.layer,
                        "style": e.dxf.style,
                    },
                )
            elif dxftype == "MTEXT":
                new_e = pruned_msp.add_mtext(
                    e.text,
                    dxfattribs={
                        "insert": e.dxf.insert,
                        "layer": e.dxf.layer,
                        "style": e.dxf.style,
                        "width": e.dxf.width,
                    },
                )
            elif dxftype == "ATTRIB":
                new_e = pruned_msp.add_attrib(
                    tag=e.dxf.tag,
                    text=e.dxf.text,
                    dxfattribs={
                        "insert": e.dxf.insert,
                        "height": e.dxf.height,
                        "layer": e.dxf.layer,
                        "rotation": e.dxf.rotation,
                        "style": e.dxf.style,
                    },
                )
            # 记录 handle 映射
            handle_map[str(new_e.dxf.handle)] = str(e.dxf.handle)

        elif dxftype == "INSERT":
            # 递归处理块，不 explode
            blk_name = e.dxf.name
            if blk_name in doc_ref.blocks:
                blk = doc_ref.blocks[blk_name]
                prune_entities(blk, pruned_msp, doc_ref)

# =============================
# 开始瘦身
# =============================
prune_entities(msp, pruned_msp, doc)

# =============================
# 保存瘦身 DXF
# =============================
pruned_doc.saveas(str(PRUNED_DXF))
print(f"✅ text_only DXF saved: {PRUNED_DXF.name}")

# =============================
# 保存 handle 映射
# =============================
with open(HANDLE_MAP_JSON, "w", encoding="utf-8") as f:
    json.dump(handle_map, f, ensure_ascii=False, indent=2)
print(f"✅ handle map saved: {HANDLE_MAP_JSON.name}")
