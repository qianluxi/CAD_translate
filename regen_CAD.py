import json
from pathlib import Path
import ezdxf  # pip install ezdxf

# =============================
# 配置路径
# =============================
BASE_DIR = Path(__file__).parent

DXF_INPUT = BASE_DIR / "source.dxf"
DXF_OUTPUT = BASE_DIR / "translated.dxf"
RESULT_JSON = BASE_DIR / "result.json"

# =============================
# 回写函数
# =============================
def write_translation_to_dxf(dxf_input, dxf_output, translations):
    """
    将 translations（handle -> 翻译文本）回写到 DXF 文件
    """
    doc = ezdxf.readfile(str(dxf_input))
    msp = doc.modelspace()
    skipped = 0
    updated = 0

    for e in msp:
        handle = e.dxf.handle
        if handle in translations:
            try:
                if e.dxftype() == 'TEXT':
                    e.dxf.text = translations[handle]
                    updated += 1
                elif e.dxftype() == 'MTEXT':
                    e.text = translations[handle]  # ezdxf 自动处理换行
                    updated += 1
                # 其它类型忽略
            except Exception:
                skipped += 1
        else:
            skipped += 1

    doc.saveas(str(dxf_output))
    print(f"✅ Translated DXF saved: {dxf_output}")
    print(f"Updated entities: {updated}, skipped: {skipped}")


# =============================
# 主程序
# =============================
if __name__ == "__main__":
    # 读取翻译结果
    with open(RESULT_JSON, "r", encoding="utf-8") as f:
        translations = json.load(f)

    write_translation_to_dxf(DXF_INPUT, DXF_OUTPUT, translations)
