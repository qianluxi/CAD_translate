import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

# Windows GBK 控制台打印 emoji 会触发 UnicodeEncodeError，这里兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# =========================================================
# 1. 路径与参数
# =========================================================
BASE_DIR = Path(__file__).parent

INPUT_JSON = BASE_DIR / "texts.json"
OUTPUT_JSON = BASE_DIR / "result.json"
CACHE_JSON = BASE_DIR / "translation_cache.json"

BATCH_SIZE = 200
SLEEP_TIME = 0.3

BASE_URL = "https://api-inference.modelscope.cn/v1"
DEFAULT_MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"

# 界面语言显示名 -> 提示词中使用的英文名
LANGUAGES = {
    "中文": "Chinese",
    "English": "English",
    "日本語": "Japanese",
    "한국어": "Korean",
    "Français": "French",
    "Deutsch": "German",
    "Español": "Spanish",
    "Русский": "Russian",
    "自动检测": "auto-detect",
}


# =========================================================
# 2. 命令行参数
# =========================================================
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="CAD DXF 文本批量翻译（ModelScope API）")
    parser.add_argument("--source-lang", default="中文", help="源语言（界面显示名）")
    parser.add_argument("--target-lang", default="English", help="目标语言（界面显示名）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ModelScope 模型 ID")
    parser.add_argument("--api-key", default="", help="ModelScope API Key，留空则使用环境变量")
    return parser.parse_args(argv)


# =========================================================
# 3. API 客户端
# =========================================================
def get_api_key(provided: str) -> str:
    return provided.strip() or os.getenv("MODELSCOPE_API_KEY") or os.getenv("MS_API_KEY") or ""


def make_client(api_key: str) -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=api_key)


# =========================================================
# 4. 缓存（按“语言对”隔离，兼容旧版扁平缓存）
# =========================================================
def make_pair_key(source_lang: str, target_lang: str) -> str:
    """统一用英文语言名作为缓存键，避免显示名/英文名混用产生不同缓存桶。"""
    src = LANGUAGES.get(source_lang, source_lang)
    tgt = LANGUAGES.get(target_lang, target_lang)
    return f"{src}|{tgt}"


def _normalize_pair_key(key: str) -> str:
    """把旧版显示名缓存键（如 中文|English）归一化为英文键（Chinese|English）。"""
    parts = key.split("|", 1)
    if len(parts) != 2:
        return key
    return f"{LANGUAGES.get(parts[0], parts[0])}|{LANGUAGES.get(parts[1], parts[1])}"


def load_cache() -> dict:
    """
    新版结构：{"Chinese|English": {原文: 译文}, ...}
    旧版结构：{原文: 译文}（仅中文 -> 英文），自动迁移到 "Chinese|English" 下。
    """
    if not CACHE_JSON.exists():
        return {}
    with open(CACHE_JSON, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return {}
    # 旧版扁平缓存（原文 -> 译文，仅中文 -> 英文）
    if raw and all(not isinstance(v, dict) for v in raw.values()):
        return {"Chinese|English": raw}
    # 新版嵌套缓存：把旧显示名键（中文|English）统一归一化为英文键
    normalized = {}
    for k, v in raw.items():
        nk = _normalize_pair_key(k)
        if nk in normalized and isinstance(v, dict) and isinstance(normalized[nk], dict):
            normalized[nk].update(v)
        else:
            normalized[nk] = v
    return normalized


def save_cache(cache: dict):
    with open(CACHE_JSON, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# =========================================================
# 5. 批量翻译（核心）
# =========================================================
def build_prompt(texts, source_lang, target_lang) -> str:
    src = LANGUAGES.get(source_lang, source_lang)
    tgt = LANGUAGES.get(target_lang, target_lang)
    if source_lang == "自动检测":
        direction = f"Detect the language of each text and translate it into {tgt}."
    else:
        direction = f"Translate the following {src} text into {tgt}."

    prompt_lines = [
        "You are a professional CAD / structural drawing translator.",
        direction,
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

    return "\n".join(prompt_lines)


def batch_translate_texts(client, model, texts, source_lang, target_lang) -> dict:
    """
    texts: [原文1, 原文2, ...]
    return: {原文: 译文}
    """
    prompt = build_prompt(texts, source_lang, target_lang)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"enable_thinking": False},
    )

    content = response.choices[0].message.content

    # 按 [ID:x] 切分
    blocks = re.split(r"\[ID:(\d+)\]", content or "")

    result = {}

    for i in range(1, len(blocks), 2):
        try:
            idx = int(blocks[i])
            translated = blocks[i + 1].strip()
            if 0 <= idx < len(texts):
                result[texts[idx]] = translated
        except Exception:
            # 防御：模型输出异常时，不记录这条结果，交给上层按原文兜底
            continue

    return result


# =========================================================
# 6. 主流程
# =========================================================
def main(argv=None):
    args = parse_args(argv)

    api_key = get_api_key(args.api_key)
    if not api_key:
        print(
            "[ERROR] 未提供 API Key：请在前端填写，或设置环境变量 MODELSCOPE_API_KEY / MS_API_KEY",
            flush=True,
        )
        sys.exit(1)
    client = make_client(api_key)

    # ---------- 读取提取文本 ----------
    try:
        with open(INPUT_JSON, "r", encoding="utf-8") as f:
            handle_to_text = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] 缺少 {INPUT_JSON.name}，请先运行 DXF_xtract.py 提取文本", flush=True)
        sys.exit(1)

    cache = load_cache()
    pair_key = make_pair_key(args.source_lang, args.target_lang)
    pair_cache = cache.setdefault(pair_key, {})

    # ---------- 收集唯一文本 ----------
    unique_texts = set(handle_to_text.values())

    # ---------- 找出需要翻译的 ----------
    to_translate = [
        t for t in unique_texts
        if t not in pair_cache
    ]

    print(f"Source -> Target: {args.source_lang} -> {args.target_lang}", flush=True)
    print(f"Model: {args.model}", flush=True)
    print(f"Unique texts: {len(unique_texts)}", flush=True)
    print(f"Need API translation: {len(to_translate)}", flush=True)

    # ---------- 批量翻译 ----------
    had_failure = False
    batch_count = 0
    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i:i + BATCH_SIZE]
        batch_count += 1

        try:
            translated = batch_translate_texts(
                client, args.model, batch, args.source_lang, args.target_lang
            )

            # 只缓存真正返回译文的条目；缺失/失败的不缓存，便于下次重试
            for t in batch:
                if t in translated:
                    pair_cache[t] = translated[t]
                else:
                    had_failure = True
                    print(f"[WARN] 模型未返回译文，回退原文: {t[:50]}", flush=True)

            print(f"✓ Translated batch {batch_count}: {len(batch)}", flush=True)
            time.sleep(SLEEP_TIME)

        except Exception as e:
            had_failure = True
            print(f"[ERROR] 批次 {batch_count} 翻译失败: {e}", flush=True)

    save_cache(cache)

    # ---------- 回映射到 handle ----------
    result = {
        handle: pair_cache.get(text, text)
        for handle, text in handle_to_text.items()
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if had_failure:
        print(
            "[ERROR] 部分文本翻译失败：已跳过未翻译条目，请检查 API Key / 网络 / 模型后重试",
            flush=True,
        )
        sys.exit(1)

    print("✓ Translation finished (MTEXT + TEXT, cached, batch optimized)", flush=True)


if __name__ == "__main__":
    main()
