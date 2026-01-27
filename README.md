# CAD DXF Translation Toolkit

A Python-based toolkit to extract, batch translate, and update **DXF/DWG** text content (TEXT, MTEXT, and block attributes) for CAD drawings, with support for **special CAD symbols** (e.g., AutoCAD SHX codes like `%%132`). Optimized for **incremental translation** and **ModelScope Qwen large model API** integration.

---

## Features

* ✅ Extract **TEXT, MTEXT, and block attributes** from DXF/DWG.
* ✅ Translate Chinese → English (or other languages via API).
* ✅ Preserve **numbers, units, and CAD symbols** during translation.
* ✅ **Batch translation** with caching to minimize API calls.
* ✅ Incremental translation: only translate new or modified text.
* ✅ Update DXF/DWG with translated text without exploding blocks.
* ✅ Flexible file input: works with any user-specified DXF/DWG file.

---

## Directory Structure

```
├── main.py                 # Main script to run full pipeline
├── DXF_xtract.py           # Extract text content from DXF
├── CAD_translate.py        # Translate extracted text via ModelScope API
├── DXF_update.py           # Write translation back into DXF
├── regen_CAD.py            # Optional DXF regeneration script
├── source.dxf              # Default input DXF (can be overridden)
├── translated.dxf          # Output DXF with translated text
├── texts.json              # Extracted text mapping
├── result.json             # Translated text mapping
├── translation_cache.json  # Optional cache for incremental translation
└── uploaded_project.zip    # Example project files (optional)
```

---

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/cad-dxf-translation.git
cd cad-dxf-translation
```

2. Create a Python environment (recommended):

```bash
python -m venv venv
source venv/bin/activate       # Linux/macOS
venv\Scripts\activate          # Windows
```

3. Install required packages:

```bash
pip install -r requirements.txt
```

**Dependencies:**

* `ezdxf` – for DXF reading/writing
* `openai` – for ModelScope Qwen API calls
* Standard Python packages: `json`, `pathlib`, `time`, `re`, `shutil`, `subprocess`

---

## Usage

### 1. Run full pipeline

```bash
python main.py <input_file.dxf>
```

* `<input_file.dxf>` can be any DXF file in the working directory.
* The script will automatically copy it as `source.dxf` for internal processing.
* Outputs:

  * `translated.dxf` – the translated DXF file
  * `texts.json` – extracted text content
  * `result.json` – translated text mapping
  * `translation_cache.json` – cached translations for future incremental runs

### 2. Incremental translation

If `result.json` exists, only new or modified text is sent to the translation API, reducing costs and improving speed.

---

## Notes

* **Special symbols** like `%%132` (AutoCAD reinforcement symbols) are preserved and not translated.
* Blocks are **not exploded** during update; text inside blocks is translated in place.
* MTEXT content, including multi-line notes, is fully translated.
* Avoid opening the output DXF (`translated.dxf`) while the script is running to prevent file locks.

---

## Configuration

* `BATCH_SIZE` in `CAD_translate.py`: number of texts sent to API at once (default `40`).
* `SLEEP_TIME`: seconds to wait between batches to avoid API throttling (default `0.3`).
* Model API settings are in `CAD_translate.py` under `MODEL_ID` and `client` configuration.

---

## Recommended Workflow

1. Place your DXF file in the project directory.
2. Run `main.py <your_file.dxf>` to execute the full pipeline.
3. Check `translated.dxf` for translated content.
4. Optional: reuse `translation_cache.json` for incremental updates when modifying the DXF.

---

## License

MIT License – free to use and modify.

---

## Acknowledgments

* [ezdxf](https://pypi.org/project/ezdxf/) – DXF parsing library
* [ModelScope Qwen](https://www.modelscope.cn/models) – large language model API

---


