# -*- coding: utf-8 -*-
"""临时验证脚本：验证失败不静默、步骤标记、环境变量传 Key、缓存迁移等修复。"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import ezdxf

PROJECT = Path(__file__).resolve().parent

# 与 app.py 中一致的正则
STEP_RE = re.compile(r"\[STEP\s+(\d+)/(\d+)\]\s*(.+)")


class FakeCompletions:
    def __init__(self, parent):
        self.parent = parent

    def create(self, model, messages, extra_body):
        self.parent.calls.append({"model": model, "messages": messages, "extra_body": extra_body})
        prompt = messages[0]["content"]
        items = re.findall(r"\[ID:(\d+)\]\n(.*?)(?=\n\[ID:|\Z)", prompt, re.S)
        texts = [t for _, t in items]
        content = "\n".join(f"[ID:{i}]\nTR:{t}\n" for i, t in enumerate(texts))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class RaisingCompletions:
    def __init__(self, parent=None):
        pass

    def create(self, model, messages, extra_body):
        raise RuntimeError("模拟 API 失败")


class PartialCompletions:
    """只返回前 N-1 条译文，模拟模型漏掉最后一条。"""

    def __init__(self, parent=None):
        pass

    def create(self, model, messages, extra_body):
        prompt = messages[0]["content"]
        items = re.findall(r"\[ID:(\d+)\]\n(.*?)(?=\n\[ID:|\Z)", prompt, re.S)
        texts = [t for _, t in items]
        content = "\n".join(f"[ID:{i}]\nTR:{t}\n" for i, t in enumerate(texts[:-1]))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeClient:
    def __init__(self, completions_cls=FakeCompletions):
        self.calls = []
        self.chat = SimpleNamespace(completions=completions_cls(self))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_quiet(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def make_sample_dxf(path):
    doc = ezdxf.new("R2010")
    doc.encoding = "utf-8"
    msp = doc.modelspace()
    msp.add_text("混凝土强度 C30", dxfattribs={"height": 2.5})
    msp.add_mtext("梁截面 300x600mm", dxfattribs={"char_height": 2.5})
    block = doc.blocks.new("TESTBLOCK")
    block.add_text("块内文字", dxfattribs={"height": 2.0})
    ins = msp.add_blockref("TESTBLOCK", (0, 0))
    ins.add_attrib("TAG1", "属性文字")
    doc.saveas(str(path))


def main():
    ok = True
    tmp = Path(tempfile.mkdtemp(prefix="cadtrans_fix_test_"))
    original_run = subprocess.run
    try:
        for f in ("DXF_xtract.py", "CAD_translate.py", "DXF_update.py", "main.py"):
            shutil.copy(PROJECT / f, tmp / f)
        sample = tmp / "sample.dxf"
        make_sample_dxf(sample)

        # ---------- 1. 提取 ----------
        shutil.copy(sample, tmp / "source.dxf")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, str(tmp / "DXF_xtract.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(tmp), env=env)
        assert r.returncode == 0, r.stderr
        texts = json.loads((tmp / "texts.json").read_text(encoding="utf-8"))
        assert len(texts) == 4, texts

        # ---------- 2. 成功翻译（中->英），缓存键为英文语言名 ----------
        ct = load_module("ct", tmp / "CAD_translate.py")
        fake = FakeClient()
        ct.make_client = lambda api_key: fake
        out = run_quiet(ct.main, ["--source-lang", "中文", "--target-lang", "English", "--model", "M1", "--api-key", "k1"])
        cache = json.loads((tmp / "translation_cache.json").read_text(encoding="utf-8"))
        assert "Chinese|English" in cache, cache
        assert all(v.startswith("TR:") for v in cache["Chinese|English"].values()), cache
        assert "Translate the following Chinese text into English." in fake.calls[0]["messages"][0]["content"]

        # ---------- 3. 旧显示名缓存键迁移 ----------
        (tmp / "translation_cache.json").write_text(
            json.dumps({"中文|English": {"旧1": "旧译文"}, "English|中文": {"旧2": "旧译文2"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        cache = ct.load_cache()
        assert set(cache) == {"Chinese|English", "English|Chinese"}, cache
        assert cache["Chinese|English"]["旧1"] == "旧译文"

        # ---------- 4. 旧版扁平缓存迁移 ----------
        (tmp / "translation_cache.json").write_text(
            json.dumps({"旧文本": "Old translation"}, ensure_ascii=False), encoding="utf-8"
        )
        cache = ct.load_cache()
        assert set(cache) == {"Chinese|English"}, cache
        assert cache["Chinese|English"]["旧文本"] == "Old translation"

        # ---------- 5. 整批失败：不静默，失败条目不入缓存 ----------
        (tmp / "translation_cache.json").unlink(missing_ok=True)
        (tmp / "texts.json").write_text(
            json.dumps({"h1": "alpha", "h2": "beta"}, ensure_ascii=False), encoding="utf-8"
        )
        ct.make_client = lambda api_key: FakeClient(RaisingCompletions)
        try:
            run_quiet(ct.main, ["--source-lang", "中文", "--target-lang", "English", "--model", "M", "--api-key", "k"])
            raise AssertionError("整批失败时应非零退出")
        except SystemExit as e:
            assert e.code == 1
        cache = json.loads((tmp / "translation_cache.json").read_text(encoding="utf-8"))
        assert "alpha" not in cache["Chinese|English"] and "beta" not in cache["Chinese|English"], cache

        # ---------- 6. 部分缺失：漏译条目不入缓存并报错 ----------
        (tmp / "translation_cache.json").unlink(missing_ok=True)
        ct.make_client = lambda api_key: FakeClient(PartialCompletions)
        try:
            run_quiet(ct.main, ["--source-lang", "中文", "--target-lang", "English", "--model", "M", "--api-key", "k"])
            raise AssertionError("部分缺失时应非零退出")
        except SystemExit as e:
            assert e.code == 1
        cache = json.loads((tmp / "translation_cache.json").read_text(encoding="utf-8"))
        assert len(cache["Chinese|English"]) == 1, cache
        assert list(cache["Chinese|English"].values())[0].startswith("TR:"), cache

        # ---------- 7. DXF 回写 ----------
        result = {h: "TR:" + t for h, t in texts.items()}
        (tmp / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        shutil.copy(sample, tmp / "source.dxf")
        r = subprocess.run([sys.executable, str(tmp / "DXF_update.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(tmp))
        assert r.returncode == 0, r.stderr
        out_doc = ezdxf.readfile(str(tmp / "translated.dxf"))
        updated = set()
        for e in out_doc.modelspace():
            if e.dxftype() in ("TEXT", "MTEXT"):
                updated.add(e.dxf.text if e.dxftype() == "TEXT" else e.text)
            elif e.dxftype() == "INSERT":
                for a in e.attribs:
                    updated.add(a.dxf.text)
        for blk in out_doc.blocks:
            if not blk.name.startswith("*"):
                for e in blk:
                    if e.dxftype() == "TEXT":
                        updated.add(e.dxf.text)
        assert all(v.startswith("TR:") for v in updated if v), updated

        # ---------- 8. main.py：步骤标记 + API Key 走环境变量 ----------
        mm = load_module("mm", tmp / "main.py")
        shutil.copy(sample, tmp / "source.dxf")
        recorded = []
        mm.subprocess.run = lambda cmd, check=False, timeout=None, env=None: recorded.append((cmd, env))
        out = run_quiet(mm.main, ["--source-lang", "中文", "--target-lang", "English", "--model", "M", "--api-key", "kk"])
        assert len(recorded) == 3, len(recorded)
        step_cmds = [c[0] for c in recorded]
        assert step_cmds[0][-1].endswith("DXF_xtract.py")
        assert "--api-key" not in step_cmds[1], step_cmds[1]
        assert step_cmds[1][step_cmds[1].index("--model") + 1] == "M"
        assert recorded[1][1]["MODELSCOPE_API_KEY"] == "kk", "API Key 未通过环境变量传递"
        markers = STEP_RE.findall(out)
        assert [m[0] for m in markers] == ["1", "2", "3"], markers
        assert "✓ All steps completed successfully." in out

        # ---------- 9. main.py 子步骤失败：明确报错并非零退出 ----------
        def raise_cpe(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd)

        mm.subprocess.run = raise_cpe
        shutil.copy(sample, tmp / "source.dxf")
        try:
            run_quiet(mm.main, ["--source-lang", "中文", "--target-lang", "English"])
            raise AssertionError("子步骤失败时应非零退出")
        except SystemExit as e:
            assert e.code == 1
        subprocess.run = original_run

        # ---------- 10. 提取失败：非零退出 ----------
        tmp2 = Path(tempfile.mkdtemp(prefix="cadtrans_xtract_fail_"))
        try:
            shutil.copy(PROJECT / "DXF_xtract.py", tmp2 / "DXF_xtract.py")
            r = subprocess.run([sys.executable, str(tmp2 / "DXF_xtract.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(tmp2))
            assert r.returncode == 1, r.returncode
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        print("ALL CHECKS PASSED ✓")
    except Exception:
        ok = False
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
