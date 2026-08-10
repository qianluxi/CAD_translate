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
RETRY_BATCH_SIZE = 50
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
def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def build_prompt(texts, source_lang, target_lang, strict=False) -> str:
    src = LANGUAGES.get(source_lang, source_lang)
    tgt = LANGUAGES.get(target_lang, target_lang)
    if source_lang == "自动检测":
        direction = f"Detect the language of each text and translate it into {tgt}."
    else:
        direction = f"Translate the following {src} text into {tgt}."

    if strict:
        rules = [
            "- You MUST return exactly one [ID:x] entry for every text, in the same order.",
            "- Do NOT omit or merge any [ID:x].",
            "- If a text needs no translation (codes, part numbers, dimensions, proper nouns), return it unchanged.",
            "- One line per entry, no explanations, no extra text.",
            "- Keep numbers, units, symbols unchanged (mm, kN, %, ±, etc.).",
        ]
    else:
        rules = [
            "- Keep numbers, units, symbols unchanged (mm, kN, %, ±, etc.)",
            "- Keep special CAD symbols like %%132 intact",
            "- If a text needs no translation (codes, part numbers, dimensions), return it unchanged",
            "- No explanation, no extra text",
            "- Keep original formatting as much as possible",
        ]

    prompt_lines = [
        "You are a professional CAD / structural drawing translator.",
        direction,
        "Rules:",
    ]
    prompt_lines += rules
    prompt_lines.append("")

    for i, text in enumerate(texts):
        prompt_lines.append(f"[ID:{i}]")
        prompt_lines.append(text)
        prompt_lines.append("")

    return "\n".join(prompt_lines)


def batch_translate_texts(client, model, texts, source_lang, target_lang, strict=False) -> dict:
    """
    texts: [原文1, 原文2, ...]
    return: {原文: 译文}（只包含模型真正返回了非空译文的条目）
    """
    prompt = build_prompt(texts, source_lang, target_lang, strict=strict)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"enable_thinking": False},
    )

    content = response.choices[0].message.content or ""

    # 按 [ID:x] 切分（容忍 [ID: 0] / [ID:0] 等空格差异）
    blocks = re.split(r"\[ID\s*:\s*(\d+)\s*\]", content)

    result = {}

    for i in range(1, len(blocks), 2):
        try:
            idx = int(blocks[i])
            translated = blocks[i + 1].strip()
            # 空译文视为缺失，避免把空串写进 DXF
            if translated and 0 <= idx < len(texts):
                result[texts[idx]] = translated
        except Exception:
            # 防御：模型输出异常时，不记录这条结果，交给上层兜底
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

    done = 0
    missing = []
    api_failure = False

    # ---------- 第一轮：常规批量翻译 ----------
    for i, batch in enumerate(chunk_list(to_translate, BATCH_SIZE), 1):
        try:
            translated = batch_translate_texts(
                client, args.model, batch, args.source_lang, args.target_lang
            )
        except Exception as e:
            print(f"[WARN] 批次 {i} 调用失败，稍后重试一次: {e}", flush=True)
            time.sleep(1)
            try:
                translated = batch_translate_texts(
                    client, args.model, batch, args.source_lang, args.target_lang
                )
            except Exception as e2:
                api_failure = True
                print(f"[ERROR] 批次 {i} 两次调用均失败: {e2}", flush=True)
                continue

        for t in batch:
            if t in translated and translated[t]:
                pair_cache[t] = translated[t]
                done += 1
            else:
                missing.append(t)

        print(f"✓ Translated batch {i}: {len(batch)}", flush=True)
        time.sleep(SLEEP_TIME)

    # ---------- 第二轮/第三轮：小批次严格重试缺失项 ----------
    round_no = 0
    while missing and round_no < 2:
        round_no += 1
        print(f"[INFO] 第 {round_no} 轮重试缺失项（{len(missing)} 条）...", flush=True)
        still_missing = []
        for batch in chunk_list(missing, RETRY_BATCH_SIZE):
            try:
                translated = batch_translate_texts(
                    client, args.model, batch, args.source_lang, args.target_lang, strict=True
                )
            except Exception as e:
                print(f"[WARN] 重试批次失败: {e}", flush=True)
                still_missing.extend(batch)
                continue

            for t in batch:
                if t in translated and translated[t]:
                    pair_cache[t] = translated[t]
                    done += 1
                else:
                    still_missing.append(t)
            time.sleep(SLEEP_TIME)
        missing = still_missing

    # ---------- API 级失败：中止 ----------
    if api_failure:
        save_cache(cache)
        print(
            "[ERROR] 存在 API 调用失败，流程中止，请检查 API Key / 网络 / 模型后重试",
            flush=True,
        )
        sys.exit(1)

    # ---------- 仍缺失的条目：保留原文并缓存，避免下次重复调用 ----------
    for t in missing:
        pair_cache[t] = t

    save_cache(cache)

    # ---------- 回映射到 handle ----------
    result = {
        handle: pair_cache.get(text, text)
        for handle, text in handle_to_text.items()
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---------- 结果汇总 ----------
    skipped = len(missing)
    if skipped:
        for t in missing[:10]:
            print(f"[WARN] 未翻译，保留原文: {t[:60]}", flush=True)
        if skipped > 10:
            print(f"[WARN] … 另有 {skipped - 10} 条未翻译", flush=True)
        print(f"[WARN] 完成，但 {skipped} 条文本未翻译（已保留原文）", flush=True)
    else:
        print("✓ Translation finished (MTEXT + TEXT, cached, batch optimized)", flush=True)
    # 汇总行放在最后，保证 app.py 的尾部缓冲一定能读到
    print(f"[SUMMARY] translated={done} skipped={skipped}", flush=True)


if __name__ == "__main__":
    main()
