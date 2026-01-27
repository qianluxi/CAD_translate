import json
from pathlib import Path
import ezdxf  # pip install ezdxf

# =============================
# 配置
# =============================
BASE_DIR = Path(__file__).parent
DXF_FILE = BASE_DIR / "source.dxf"
OUTPUT_JSON = BASE_DIR / "texts.json"

# =============================
# 提取函数
# =============================
def extract_texts_from_dxf(dxf_path):
    """
    提取 DXF 文件中：
    - MODELSPACE 的 TEXT / MTEXT
    - BLOCK 定义内部的 TEXT / MTEXT
    - INSERT 属性 ATTRIB/ATTDEF
    返回 {唯一handle: 文本} 字典
    """
    doc = ezdxf.readfile(str(dxf_path))
    texts = {}

    # === 1. MODELSPACE TEXT / MTEXT ===
    msp = doc.modelspace()
    for e in msp:
        handle = e.dxf.handle
        if e.dxftype() == 'TEXT':
            texts[handle] = e.dxf.text
        elif e.dxftype() == 'MTEXT':
            texts[handle] = e.text
        elif e.dxftype() == 'INSERT':
            # INSERT 的属性
            for attrib in e.attribs:  # ✅ 注意这里去掉括号
                key = f"INSERT:{handle}:{attrib.dxf.handle}"
                texts[key] = attrib.dxf.text

    # === 2. BLOCK 定义内部 TEXT / MTEXT ===
    for block in doc.blocks:
        block_name = block.name
        for e in block:
            if e.dxftype() in ['TEXT', 'MTEXT']:
                key = f"BLOCK:{block_name}:{e.dxf.handle}"
                if e.dxftype() == 'TEXT':
                    texts[key] = e.dxf.text
                else:
                    texts[key] = e.text

    return texts

# =============================
# 主程序
# =============================
if __name__ == "__main__":
    try:
        texts = extract_texts_from_dxf(DXF_FILE)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(texts, f, ensure_ascii=False, indent=2)
        print(f"✅ texts.json generated: {OUTPUT_JSON}")
        print(f"Total texts extracted: {len(texts)}")
    except Exception as e:
        print(f"❌ Failed to extract texts: {e}")
