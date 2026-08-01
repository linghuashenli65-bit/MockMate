# 识图能力

当前底层模型不具备原生识图能力。遇到图片时，**不要用 Read 工具直接解析图片**，改用项目根目录的 `vision.js`：

```
node vision.js "<图片路径>" "用中文描述这张图片"
```

网络图片链接：

```
node vision.js --url "<图片链接>" "用中文描述这张图片"
```

## 触发场景

- 用户分享图片路径（本地或网络 URL）
- 消息中出现 "Saved attachments:" 并列出图片
- 用户要求分析、描述、识别图片内容

## 配置说明

- API Key、模型名、Base URL 配置在项目根目录 `.env` 中（`DASHSCOPE_API_KEY` / `VISION_MODEL` / `DASHSCOPE_BASE_URL`），`.env` 已被 gitignore
- 当前模型：`qwen3.7-flash-2026-07-15`（阿里云百炼 OpenAI 兼容接口）
- 本地图片直接传路径；网络图片用 `--url` 参数
