import json
import time
import re
from pathlib import Path
from openai import OpenAI

# =========================================================
# 1. ModelScope API 配置
# =========================================================
client = OpenAI(
    base_url="https://api-inference.modelscope.cn/v1",
    api_key="ms-a008e17e-882d-4622-ae01-150918799925"
)

MODEL_ID = "Qwen/Qwen3-235B-A22B-Instruct-2507"

EXTRA_BODY = {
    "enable_thinking": False
}

# =========================================================
# 2. 路径与参数
# =========================================================
BASE_DIR = Path(__file__).parent

INPUT_JSON  = BASE_DIR / "texts.json"
OUTPUT_JSON = BASE_DIR / "result.json"
CACHE_JSON  = BASE_DIR / "translation_cache.json"

BATCH_SIZE = 200
SLEEP_TIME = 0.3

# =========================================================
# 3. 工具函数
# =========================================================
def load_cache() -> dict:
    if CACHE_JSON.exists():
        with open(CACHE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache: dict):
    with open(CACHE_JSON, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# =========================================================
# 4. 批量翻译（核心）
# =========================================================
def batch_translate_texts(texts: list[str]) -> dict:
    """
    texts: [原文1, 原文2, ...]
    return: {原文: 翻译}
    """

    prompt_lines = [
        "You are a professional CAD / structural drawing translator.",
        "Translate the following Chinese text into ENGLISH.",
        "Rules:",
        "- Keep numbers, units, symbols unchanged (mm, kN, %, ±, etc.)",
        "- Keep special CAD symbols like %%132 intact",
        "- No explanation, no extra text",
        "- Keep original formatting as much as possible",
        "",
    ]

    for i, text in enumerate(texts):
        prompt_lines.append(f"[ID:{i}]")
        prompt_lines.append(text)
        prompt_lines.append("")

    prompt = "\n".join(prompt_lines)

    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        extra_body=EXTRA_BODY
    )

    content = response.choices[0].message.content

    # 按 [ID:x] 切分
    blocks = re.split(r"\[ID:(\d+)\]", content)

    result = {}

    for i in range(1, len(blocks), 2):
        try:
            idx = int(blocks[i])
            translated = blocks[i + 1].strip()
            result[texts[idx]] = translated
        except Exception:
            # 防御：模型输出异常时，不让程序炸
            result[texts[idx]] = texts[idx]

    return result

# =========================================================
# 5. 主流程
# =========================================================
def main():
    # ---------- 读取提取文本 ----------
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        handle_to_text = json.load(f)

    cache = load_cache()

    # ---------- 收集唯一文本 ----------
    unique_texts = set(handle_to_text.values())

    # ---------- 找出需要翻译的 ----------
    to_translate = [
        t for t in unique_texts
        if t not in cache
    ]

    print(f"Unique texts: {len(unique_texts)}")
    print(f"Need API translation: {len(to_translate)}")

    # ---------- 批量翻译 ----------
    batch_count = 0
    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i:i + BATCH_SIZE]
        batch_count += 1

        try:
            translated = batch_translate_texts(batch)

            # 确保每个原文都有结果
            for t in batch:
                cache[t] = translated.get(t, t)

            print(f"✅ Translated batch {batch_count}: {len(batch)}")
            time.sleep(SLEEP_TIME)

        except Exception as e:
            print(f"❌ Batch {batch_count} failed, fallback to original")
            print(e)
            for t in batch:
                cache[t] = t

    save_cache(cache)

    # ---------- 回映射到 handle ----------
    result = {
        handle: cache.get(text, text)
        for handle, text in handle_to_text.items()
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("✅ Translation finished (MTEXT + TEXT, cached, batch optimized)")

if __name__ == "__main__":
    main()
