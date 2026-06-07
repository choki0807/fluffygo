# 技术说明

## 技术栈

- Python
- Pandas
- Requests
- python-dotenv
- Streamlit
- FastAPI
- Uvicorn
- HTTPX
- HTML / CSS / JavaScript
- Baidu Place API

## 数据链路

```text
baidu_poi_collector.py
  -> fluffygo_xinjiekou_poi_raw.csv
  -> fluffygo_xinjiekou_poi_shortlist.csv
  -> convert_shortlist_to_demo_json.py
  -> fluffygo_demo_poi.json
  -> api_server.py
  -> app.py / stitch_demo.html
```

## 核心脚本

### baidu_poi_collector.py

负责调用百度地图 Place API，采集南京新街口周边 POI，并基于轻量规则生成：

- pet_friendly_status
- confidence_level
- evidence_source
- evidence_text
- suitable_pet_size
- space_type
- crowd_level
- pet_stress_level
- risk_note
- transaction_action
- route_role

同时会生成 Demo shortlist。

### convert_shortlist_to_demo_json.py

负责将 shortlist CSV 转换为前端可直接读取的 JSON，结构包括：

- project
- user_input_example
- pois
- route_templates
- adjustment_cases

### app.py

Streamlit MVP 验证页，用于快速验证数据结构和产品链路。

### stitch_demo.html

面试展示版本，使用本地 JSON 展示更完整的前端体验，并用轻量前端规则模拟自然语言解析和路线切换。

### api_server.py

FastAPI 后端服务，提供：

- `GET /api/health`
- `GET /api/demo-data`
- `POST /api/plan-route`

后端会解析用户输入，选择路线类型，聚合对应 POI，生成风险摘要和商业交易动作。默认使用规则引擎，保证 Demo 稳定；如果配置 LLM API Key，会用真实 LLM 增强推荐理由和风险摘要。

## 当前 AI 实现方式

当前版本采用“LLM-ready”架构思路：

- 前端已经有自然语言输入区和动态解析结果。
- 当前解析由 FastAPI 后端规则引擎完成，保证演示稳定。
- 后端已经预留真实 LLM 增强路径。

推荐真实 LLM 接入方式：

```text
stitch_demo.html
  -> FastAPI /api/plan-route
  -> Rule Engine
  -> Optional LLM API
  -> fluffygo_demo_poi.json
  -> structured route JSON
```

这样可以避免把 API Key 暴露在前端。

## 降级策略

- 后端不可用：前端回退到本地规则。
- LLM 未配置：后端使用规则引擎。
- LLM 超时或返回异常：后端回退规则结果。
- JSON 缺字段：前端展示兜底文案，避免页面崩溃。

## 安全注意事项

- `.env` 中包含真实百度地图 AK，不应提交或发送。
- 面试分享包只包含 `.env.example`。
- 当前 Demo 不爬取美团或大众点评。
