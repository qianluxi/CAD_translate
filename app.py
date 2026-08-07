import gradio as gr
from pathlib import Path
import shutil
import subprocess

BASE_DIR = Path(__file__).parent
SOURCE_DXF = BASE_DIR / "source.dxf"
OUTPUT_DXF = BASE_DIR / "translated.dxf"


def translate_dxf(uploaded_file):
    """
    uploaded_file: Gradio 上传的文件对象
    """
    if uploaded_file is None:
        return None, "⚠️ 请上传一个 DXF 文件"

    uploaded_path = Path(uploaded_file.name) if hasattr(uploaded_file, "name") else Path(uploaded_file)

    if uploaded_path.suffix.lower() != ".dxf":
        return None, "❌ 仅支持 DXF 文件，请先将 DWG 转换为 DXF"

    if SOURCE_DXF.exists():
        SOURCE_DXF.unlink()

    shutil.copy(uploaded_path, SOURCE_DXF)

    try:
        subprocess.run(["python", str(BASE_DIR / "main.py")], check=True)
    except subprocess.CalledProcessError as e:
        return None, f"❌ 翻译失败: {e}"

    if not OUTPUT_DXF.exists():
        return None, "❌ 翻译完成，但未生成 translated.dxf"

    return str(OUTPUT_DXF), "✅ 翻译完成，可下载 translated.dxf"


# =============================
# Gradio 界面
# =============================
with gr.Blocks(title="CAD DXF 翻译工具") as demo:
    gr.Markdown(
        """
        # 🏗️ CAD DXF 翻译工具

        **输入：DXF 文件**  
        **输出：translated.dxf（已翻译文本）**

        ---

        ## ⚠️ 使用说明（请务必阅读）

        - ✅ **仅支持 `.dxf` 文件**
        - ❌ **不支持 `.dwg` 文件**
        - 👉 如果你的原文件是 DWG，请 **自行先转换为 DXF** 再上传

        ### 翻译范围说明
        - ✔️ 翻译 CAD 中的文字内容（TEXT / MTEXT / 块内文字等）
        - ❌ 不修改任何图形元素（线、块几何、填充等）

        ---
        """
    )

    with gr.Row():
        file_input = gr.File(
            label="📁 上传 DXF 文件（仅支持 .dxf）",
            file_types=[".dxf"]
        )
        output_file = gr.File(
            label="⬇️ 下载翻译后的 DXF",
            interactive=False
        )

    status = gr.Textbox(
        label="状态信息",
        interactive=False
    )

    translate_btn = gr.Button("🚀 开始翻译")
    translate_btn.click(
        fn=translate_dxf,
        inputs=file_input,
        outputs=[output_file, status]
    )


# 启动 Gradio
demo.launch(server_name="0.0.0.0", server_port=7860)
