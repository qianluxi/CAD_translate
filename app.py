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
        return None, "⚠️ 上传的不是 DXF 文件"

    if SOURCE_DXF.exists():
        SOURCE_DXF.unlink()

    shutil.copy(uploaded_path, SOURCE_DXF)

    try:
        subprocess.run(["python", str(BASE_DIR / "main.py")], check=True)
    except subprocess.CalledProcessError as e:
        return None, f"❌ 翻译失败: {e}"

    if not OUTPUT_DXF.exists():
        return None, "❌ 翻译完成，但 translated.dxf 未生成"

    # ⚠️ 返回字符串路径给 Gradio
    return str(OUTPUT_DXF), "✅ 翻译完成，可以下载 translated.dxf"

# =============================
# Gradio 界面
# =============================
with gr.Blocks(title="CAD DXF 翻译") as demo:
    gr.Markdown(
        """
        # CAD DXF 翻译工具
        上传任意 DXF 文件，程序会翻译其中文本元素并生成 translated.dxf。
        """
    )

    with gr.Row():
        file_input = gr.File(label="上传 DXF 文件", file_types=[".dxf"])
        output_file = gr.File(label="下载翻译后的 DXF", interactive=False)

    status = gr.Textbox(label="状态信息", interactive=False)

    translate_btn = gr.Button("开始翻译")
    translate_btn.click(
        fn=translate_dxf,
        inputs=file_input,
        outputs=[output_file, status]
    )

# 启动 Gradio
demo.launch(server_name="0.0.0.0", server_port=7860)
