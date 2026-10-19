# Harbor v1.6 遗留项目标机验证报告

生成时间：2026-10-19T15:10:56（target_verify.py v1.6）

## DeepSeek 校准（T4） — **FAIL**
- POST /v1/chat/completions → HTTP 401
- 响应体: {"error": {"message": "Authentication Fails, Your api key: ****e000 is invalid (request_id: 28fb6355-2b83-451e-a45a-013f255375c7)", "type": "authentication_error", "param": null, "code": "invalid_request_error"}}

## GitHub Models 真机复核（T2/T3） — **FAIL**
- GET https://models.github.ai/catalog/models → HTTP 200
-   响应: "OK\r\n"
- GET https://models.github.ai/inference/models → HTTP 200
-   响应: "OK\r\n"
- POST /inference/chat/completions → HTTP 200
- 限流相关响应头: （本次未返回，触发 429 时复查）
- chat 返回 200 但非 JSON 响应体（'OK\r\n'）——疑似中间网络设备拦截，该环境无法完成 GitHub 真机验证
- 目录/清单双路径均失败——将 L2 fallback 打印的真实结构回填到 _parse_github_catalog/_parse_github_models_list

## Ollama /api/tags（KNOWN_ISSUES #2） — **FAIL**
- GET /api/tags → HTTP 502（Ollama 未运行？）

## 基准链 token 统计（-15% 目标） — **FAIL**
- 纯问答 → HTTP 401（不计入）
- 单文件改 → HTTP 401（不计入）
- 多文件+命令 → HTTP 401（不计入）

---
合计：PASS 0 / FAIL 4 / SKIP 0

销项规则：DeepSeek PASS → T4 销项；GitHub 目录结构打印回填 → T2/T3 校准；Ollama PASS → KNOWN_ISSUES #2 销项；基准链合计 ≥ -15% → 量化目标达成。