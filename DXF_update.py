import json
import sys
from pathlib import Path
import ezdxf

# Windows GBK 控制台打印 emoji 会触发 UnicodeEncodeError，这里兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# =============================
# 路径配置
# =============================
BASE_DIR = Path(__file__).parent
SOURCE_DXF = BASE_DIR / "source.dxf"
OUTPUT_DXF = BASE_DIR / "translated.dxf"
RESULT_JSON = BASE_DIR / "result.json"

# =============================
# 加载翻译结果（{原始 handle: 译文}）
# =============================
with open(RESULT_JSON, "r", encoding="utf-8") as f:
    translations = json.load(f)

# =============================
# 打开原始 DXF
# =============================
doc = ezdxf.readfile(str(SOURCE_DXF))


# =============================
# 更新实体文本
# =============================
def apply_translation(entity):
    new_text = translations.get(entity.dxf.handle)
    if new_text is None:
        return
    if entity.dxftype() == "MTEXT":
        entity.text = new_text
    else:  # TEXT / ATTRIB
        entity.dxf.text = new_text


def process_entities(entities):
    for e in entities:
        if e.dxftype() in ("TEXT", "MTEXT", "ATTRIB"):
            apply_translation(e)
        elif e.dxftype() == "INSERT":
            # 块属性挂在 INSERT 上，不是块定义里的独立实体
            for attrib in e.attribs:
                apply_translation(attrib)


# =============================
# 更新模型空间 + 所有真实块定义（跳过伪块）
# =============================
process_entities(doc.modelspace())
for block in doc.blocks:
    if block.name.startswith("*"):
        continue
    process_entities(block)

# =============================
# 保存输出 DXF
# =============================
doc.saveas(str(OUTPUT_DXF))
print(f"✅ Translated DXF saved: {OUTPUT_DXF.name}")

# 提示：不要在程序里关闭 DXF，避免文件锁冲突
print("ℹ️ Please ensure DXF is closed in CAD before opening translated.dxf")
