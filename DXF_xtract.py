import json
import sys
from pathlib import Path
import ezdxf  # pip install ezdxf

# Windows GBK 控制台打印 emoji 会触发 UnicodeEncodeError，这里兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# =============================
# 配置
# =============================
BASE_DIR = Path(__file__).parent
DXF_FILE = BASE_DIR / "source.dxf"
OUTPUT_JSON = BASE_DIR / "texts.json"


# =============================
# 提取函数
# =============================
def collect_texts(entities, texts):
    """从一组实体中收集文本，键为原始 DXF handle。"""
    for e in entities:
        if e.dxftype() == "TEXT":
            texts[e.dxf.handle] = e.dxf.text
        elif e.dxftype() == "MTEXT":
            # plain_text() 把 DXF 换行符 \P 转成普通 \n，方便大模型理解
            texts[e.dxf.handle] = e.plain_text()
        elif e.dxftype() == "INSERT":
            # ATTRIB 不是独立顶层实体，必须从 insert.attribs 里取
            for attrib in e.attribs:
                texts[attrib.dxf.handle] = attrib.dxf.text


def extract_texts_from_dxf(dxf_path):
    """
    直接读取原始 DXF，提取：
    - MODELSPACE 的 TEXT / MTEXT / INSERT 属性
    - 真实 BLOCK 定义内部的 TEXT / MTEXT / INSERT 属性

    跳过 *Model_Space / *Paper_Space 等伪块，避免模型空间文本被重复提取。
    返回 {handle: 文本} 字典，handle 即原始 DXF 的 handle，回写时直接对应。
    """
    doc = ezdxf.readfile(str(dxf_path))
    texts = {}

    collect_texts(doc.modelspace(), texts)

    for block in doc.blocks:
        if block.name.startswith("*"):
            continue
        collect_texts(block, texts)

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
