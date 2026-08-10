import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import gradio as gr

BASE_DIR = Path(__file__).parent
SOURCE_DXF = BASE_DIR / "source.dxf"
OUTPUT_DXF = BASE_DIR / "translated.dxf"

DEFAULT_MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"
MODELS = [
    DEFAULT_MODEL,
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
]
CUSTOM_MODEL_OPTION = "自定义（在下方输入模型 ID）"

LANGUAGES = ["中文", "English", "日本語", "한국어", "Français", "Deutsch", "Español", "Русский", "自动检测"]
TARGET_LANGUAGES = [lang for lang in LANGUAGES if lang != "自动检测"]

# 匹配 main.py 输出的步骤标记，如 [STEP 1/3] 提取文本...
STEP_RE = re.compile(r"\[STEP\s+(\d+)/(\d+)\]\s*(.+)")


def translate_dxf(uploaded_file, source_lang, target_lang, model, custom_model, api_key):
    """生成器：逐行读取流水线输出，实时更新状态栏。"""
    if uploaded_file is None:
        yield gr.update(value=None), "⚠️ 请上传一个 DXF 文件"
        return

    uploaded_path = Path(uploaded_file.name) if hasattr(uploaded_file, "name") else Path(uploaded_file)

    if uploaded_path.suffix.lower() != ".dxf":
        yield gr.update(value=None), "❌ 仅支持 DXF 文件，请先将 DWG 转换为 DXF"
        return

    # 模型解析：选“自定义”时必须填写模型 ID
    if model == CUSTOM_MODEL_OPTION:
        model_id = (custom_model or "").strip()
        if not model_id:
            yield gr.update(value=None), "❌ 已选择自定义模型，请先在下方填写模型 ID"
            return
    else:
        model_id = model

    # API Key：前端填写优先，否则要求服务端已配置环境变量
    has_env_key = bool(os.environ.get("MODELSCOPE_API_KEY") or os.environ.get("MS_API_KEY"))
    if not (api_key and api_key.strip()) and not has_env_key:
        yield gr.update(value=None), "❌ 未填写 API Key，且服务端未配置环境变量，请先填写后再翻译"
        return

    yield gr.update(value=None), "📤 准备中：正在复制文件..."

    if SOURCE_DXF.exists():
        SOURCE_DXF.unlink()
    shutil.copy(uploaded_path, SOURCE_DXF)

    cmd = [
        sys.executable,
        str(BASE_DIR / "main.py"),
        "--source-lang", source_lang,
        "--target-lang", target_lang,
        "--model", model_id,
    ]
    # API Key 走环境变量，避免出现在命令行参数中
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if api_key and api_key.strip():
        env["MODELSCOPE_API_KEY"] = api_key.strip()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as e:
        yield gr.update(value=None), f"❌ 启动翻译失败: {e}"
        return

    tail = []
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            tail.append(line)
            if len(tail) > 15:
                tail.pop(0)
            m = STEP_RE.search(line)
            if m:
                yield gr.update(value=None), f"⏳ 步骤 {m.group(1)}/{m.group(2)}：{m.group(3)}..."
        rc = proc.wait()
    except Exception as e:
        proc.kill()
        yield gr.update(value=None), f"❌ 翻译过程异常: {e}"
        return

    if rc != 0:
        detail = "\n".join(tail[-6:]).strip()
        yield gr.update(value=None), f"❌ 翻译失败（退出码 {rc}）\n{detail}"
        return

    if not OUTPUT_DXF.exists():
        yield gr.update(value=None), "❌ 翻译完成，但未生成 translated.dxf"
        return

    # 解析 [SUMMARY] translated=N skipped=M，有保留原文时给出提示
    skipped = 0
    for ln in tail:
        m = re.search(r"\[SUMMARY\] translated=(\d+) skipped=(\d+)", ln)
        if m:
            skipped = int(m.group(2))

    if skipped:
        yield str(OUTPUT_DXF), f"⚠️ 翻译完成（{skipped} 条未翻译，已保留原文），可下载 translated.dxf"
    else:
        yield str(OUTPUT_DXF), "✅ 翻译完成，可下载 translated.dxf"


# =============================
# Gradio 界面
# =============================
with gr.Blocks(title="CAD DXF 翻译工具") as demo:
    gr.Markdown(
        """
        # 🛠️ CAD DXF 翻译工具

        **输入：DXF 文件**  
        **输出：translated.dxf（已翻译文本）**

        ---

        ## 📖 使用说明（请务必阅读）

        - ✅ **仅支持 `.dxf` 文件**
        - ❌ **不支持 `.dwg` 文件**
        - 💡 如果你的原文件是 DWG，请 **自行先转换为 DXF** 再上传

        ### 翻译范围说明
        - ✅ 翻译 CAD 中的文字内容（TEXT / MTEXT / 块内文字等）
        - ❌ 不修改任何图形元素（线、块几何、填充等）

        ### 新增选项
        - 🌐 **翻译方向**：选择源语言和目标语言（中英、英中或其他语言）
        - 🤖 **模型选择**：可选不同 Qwen 模型，或自定义模型 ID
        - 🔑 **API Key**：可填入自己的 ModelScope API Key；留空则使用服务端环境变量
        - ⏳ **运行状态**：翻译过程中，状态栏会实时显示当前步骤（提取 / 翻译 / 回写）

        ---
        """
    )

    with gr.Row():
        file_input = gr.File(
            label="📄 上传 DXF 文件（仅支持 .dxf）",
            file_types=[".dxf"]
        )
        output_file = gr.File(
            label="📥 下载翻译后的 DXF",
            interactive=False
        )

    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🌐 翻译方向")
            with gr.Row():
                source_lang = gr.Dropdown(
                    LANGUAGES, value="中文", label="源语言"
                )
                target_lang = gr.Dropdown(
                    TARGET_LANGUAGES, value="English", label="目标语言"
                )
        with gr.Column():
            gr.Markdown("### 🤖 模型与 API Key")
            model = gr.Dropdown(
                MODELS + [CUSTOM_MODEL_OPTION],
                value=DEFAULT_MODEL,
                label="模型",
            )
            custom_model = gr.Textbox(
                label="自定义模型 ID",
                placeholder="如 Qwen/Qwen2.5-32B-Instruct",
                visible=False,
            )
            api_key = gr.Textbox(
                label="ModelScope API Key",
                type="password",
                placeholder="留空则使用服务端环境变量 MODELSCOPE_API_KEY",
            )

    status = gr.Textbox(
        label="状态信息",
        interactive=False,
        lines=3,
    )

    translate_btn = gr.Button("🚀 开始翻译")
    translate_btn.click(
        fn=translate_dxf,
        inputs=[file_input, source_lang, target_lang, model, custom_model, api_key],
        outputs=[output_file, status]
    )

    # 选择“自定义”时显示模型 ID 输入框
    model.change(
        fn=lambda m: gr.update(visible=(m == CUSTOM_MODEL_OPTION)),
        inputs=model,
        outputs=custom_model,
    )


# 启动 Gradio
demo.launch(server_name="0.0.0.0", server_port=7860)
