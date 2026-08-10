---
title: "CAD DXF 中文翻译工具"
description: "支持 DXF 文本提取、翻译和回写，可自定义语言方向、模型与 API Key 的批量翻译"
---

# CAD DXF 翻译工具

本工具用于将 CAD DXF 文件中的文本（TEXT、MTEXT、块属性）批量翻译为指定语言，并生成翻译后的 DXF 文件。支持自定义翻译方向（中英、英中或其他语言）、选择模型以及填写自己的 API Key。

## 功能

1. 支持用户上传任意 DXF 文件，自动处理为 `source.dxf`
2. 提取 DXF 文件中的文本、块属性和多行文本
3. 调用 ModelScope API（Qwen 模型）进行翻译
4. 支持自定义翻译方向（源语言 / 目标语言），如中英、英中、中日等
5. 支持选择模型（内置常用 Qwen 模型或自定义模型 ID）
6. 支持在前端填写自己的 ModelScope API Key（留空则使用服务端环境变量）
7. 支持增量翻译（按“语言对 + 原文”缓存），避免重复调用 API
8. 将翻译结果回写到 DXF 中，保留原图形元素
9. 支持清理临时文件，防止不同文件混淆

## 使用方法

### 本地运行

```bash
python main.py your_file.dxf
```

程序会依次完成：

1. 提取文本生成 `texts.json`
2. 批量翻译（生成或更新 `result.json`，已翻译过的文本自动跳过）
3. 回写翻译到 `translated.dxf`
4. 清理临时文件

自定义语言方向、模型和 API Key：

```bash
python main.py your_file.dxf \
  --source-lang 中文 \
  --target-lang English \
  --model Qwen/Qwen3-235B-A22B-Instruct-2507 \
  --api-key "你的apikey"
```

* `--source-lang` / `--target-lang`：源语言 / 目标语言，支持 `中文`、`English`、`日本語`、`한국어`、`Français`、`Deutsch`、`Español`、`Русский` 等，源语言还可填 `自动检测`
* `--model`：ModelScope 模型 ID，留空使用默认模型
* `--api-key`：ModelScope API Key，留空使用环境变量

### 部署到创空间

* 将 DXF 文件上传到界面
* 选择翻译方向（源语言 / 目标语言）
* 选择模型（或选择“自定义”并输入模型 ID）
* 可填写自己的 API Key（留空则使用服务端环境变量）
* 翻译过程中，状态栏会实时显示当前步骤（提取文本 / 批量翻译 / 回写 DXF）
* 程序自动处理并返回翻译后的 DXF
* 注意：请关闭 CAD 软件中正在打开的 DXF 文件，否则无法写入

## 文件说明

| 文件                 | 功能                     |
| ------------------ | ---------------------- |
| `main.py`          | 总入口，控制整体流程             |
| `DXF_xtract.py`    | 提取文本、MTEXT、块属性（直接读取原始 DXF） |
| `CAD_translate.py` | 调用 ModelScope API 进行翻译，带原文缓存 |
| `DXF_update.py`    | 将翻译结果回写到 DXF（含块属性）     |
| `dxf_prune.py`     | 遗留脚本，已不再参与流程（瘦身方案已移除） |
| `texts.json`       | 提取的原文文本                |
| `result.json`      | 翻译结果（按 handle 对应）       |
| `translation_cache.json` | 按“语言对 + 原文”的翻译缓存，用于增量翻译   |
| `source.dxf`       | 当前处理的 DXF 文件（临时）       |
| `translated.dxf`   | 最终生成的翻译 DXF 文件         |

## 注意事项

* 确保 DXF 文件不在 CAD 中打开
* 翻译仅对文本内容有效，图形元素保持原样
* 文件较大时（>50MB），可能需要等待较长时间
* 使用环境变量设置 ModelScope API Key：`MODELSCOPE_API_KEY`（兼容旧名 `MS_API_KEY`），也可以直接在创空间界面填写
* 翻译缓存按“语言对”隔离，同一原文在不同语言方向下互不影响
* 翻译失败（如 API Key 无效、网络异常）会明确报错并中止，不会静默返回未翻译的文件
* 个别无法翻译的文本（如编号、型号、尺寸）会自动用小批次重试两轮，仍失败则保留原文并在结果中提示，不会中断整体翻译
* 保留原文的条目会写入缓存（标记为已处理，避免每次重复调用 API）；如需强制重新翻译，删除 `translation_cache.json` 即可

```bash
export MODELSCOPE_API_KEY="你的apikey"
```

## 联系方式

如有问题，请在项目页面提交 Issue。
