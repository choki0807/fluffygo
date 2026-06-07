# FluffyGo Demo

FluffyGo 是一个 AI 宠物友好本地生活消费路线助手。它面向城市养宠用户在核心商圈中的短时带宠出行需求，把一句话需求转化为可执行的本地生活消费路线，串联街区活动空间、宠物友好咖啡、宠物服务/补给点和雨天备选点。

本项目是一个面试/黑客松 Demo，重点展示从 POI 数据采集、规则清洗、结构化数据建模到前端产品演示的完整链路。

## 项目亮点

- 基于百度地图 Place API 采集南京新街口周边 POI。
- 使用轻量规则生成宠物友好状态、可信度、风险提示、路线角色等字段。
- 将 shortlist CSV 转换为可直接喂给前端的结构化 JSON。
- 提供 Streamlit MVP 验证页和 Stitch 风格静态前端 Demo。
- 新增 FastAPI 后端，提供真实 API 层、健康检查、路线规划接口和 LLM-ready 扩展点。
- 支持主路线、低压力路线、雨天备选路线，以及“太拥挤 / 下雨 / 预算降低”等调整场景。
- 新增出行可行性评分、风险雷达和路线对比卡，让 Demo 从单一路线推荐升级为带宠出行决策助手。
- 增加 C 端带宠互助社区和代溜服务概念模块，展示用户反馈闭环和服务交易扩展。
- 新增 POI 到店反馈闭环，用户反馈会反哺宠物友好标签证据层。
- 推荐排序已接入用户反馈：近期负反馈会让 POI 降权并退出主推荐，正反馈会提升证据层和排序权重。
- 路线对比卡展示预算、参考距离、可行性、交易点等取舍差异，帮助用户理解为什么推荐某条路线。
- 新增“为什么这样推荐”决策轨迹，展示预算、偏好、避免项、最大风险和每个站点的选择分数。
- 路线对比卡和主路线地图均接入真实百度步行路线，起点来自用户输入位置。
- 将咖啡、餐饮、洗护、用品补给等节点连接到美团本地生活交易动作。
- 新增“可携宠条件卡”：每个站点会给出可进入范围、适合犬型、核验问题、证据来源和交易准备度，避免只展示模糊的“宠物友好”标签。

## 项目结构

```text
.
├── baidu_poi_collector.py                 # 百度地图 POI 采集与规则打标
├── convert_shortlist_to_demo_json.py      # shortlist CSV 转 Demo JSON
├── app.py                                 # Streamlit MVP 验证页
├── api_server.py                          # FastAPI 后端路线规划 API
├── stitch_demo.html                       # 高颜值静态前端 Demo
├── start_demo.ps1                         # Windows 一键启动脚本
├── start_demo.bat                         # Windows 批处理启动脚本，绕过 PowerShell 执行策略
├── SUBMISSION_GUIDE.md                    # 6/7 提交与路演说明
├── test_backend.py                        # 后端接口测试脚本
├── fluffygo_demo_poi.json                 # 前端使用的结构化 Demo 数据
├── fluffygo_xinjiekou_poi_shortlist.csv   # Demo 候选 POI 短名单
├── fluffygo_xinjiekou_poi_raw.csv         # 原始采集 POI 样例
├── requirements.txt
├── .env.example
└── docs/
    ├── product_brief.md
    ├── demo_flow.md
    ├── technical_notes.md
    └── interview_send_note.md
```

## 安装依赖

```powershell
pip install -r requirements.txt
```

如果本机 `python` 或 `pip` 没有加入 PATH，可以使用 Codex 内置 Python：

```powershell
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pip install -r requirements.txt
```

## 准备数据

项目中已经包含可演示的结构化数据：

```text
fluffygo_demo_poi.json
```

如需从 shortlist 重新生成 JSON：

```powershell
python convert_shortlist_to_demo_json.py
```

如需重新采集百度地图 POI，需要先创建 `.env`：

```text
BAIDU_MAP_AK=你的百度地图AK
BAIDU_MAP_WEB_AK=你的百度地图浏览器端AK
```

然后运行：

```powershell
python baidu_poi_collector.py
```

注意：请不要提交或发送 `.env` 文件。

## 运行 Stitch 前端 Demo

推荐面试展示使用这个版本。完整版包含一个后端 API 和一个静态前端。

### 一键启动

PowerShell 中运行：

```powershell
.\start_demo.ps1
```

如果 PowerShell 提示执行策略阻止脚本，使用：

```bat
start_demo.bat
```

或者：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
```

然后打开：

```text
http://127.0.0.1:8000/stitch_demo.html
```

后端健康检查：

```text
http://127.0.0.1:8001/api/health
```

Demo 完整度检查：

```text
http://127.0.0.1:8001/api/demo-readiness
```

### 手动启动

终端 1，启动后端：

```powershell
python api_server.py
```

终端 2，启动前端：

```powershell
python -m http.server 8000 --bind 127.0.0.1
```

浏览器打开：

```text
http://127.0.0.1:8000/stitch_demo.html
```

前端会优先调用：

```text
POST http://127.0.0.1:8001/api/plan-route
```

如果后端没有启动，前端会自动回退到本地规则，保证 Demo 不崩。

## 后端 API

### 健康检查

```text
GET /api/health
```

返回服务状态、数据文件是否存在、是否配置 LLM。

### 获取 Demo 数据

```text
GET /api/demo-data
```

返回 `fluffygo_demo_poi.json`。

### Demo 完整度检查

```text
GET /api/demo-readiness
```

返回 POI 数量、路线模板数量、百度地图 AK 状态、反馈闭环状态和当前后端能力列表，适合提交前快速自检。

### 规划路线

```text
POST /api/plan-route
```

请求示例：

```json
{
  "user_message": "如果下雨怎么办，最好室内一点，预算100",
  "use_llm": true
}
```

返回内容包括：

- 结构化解析结果
- 选中的路线类型
- 路线模板
- 每个 stop 对应的完整 POI
- 出行可行性评分
- 风险雷达
- 三条路线对比
- 路线间预算/距离/可行性/交易机会取舍
- 后端决策轨迹和站点选择分数
- C 端论坛与代溜服务模块
- 风险摘要
- 美团交易动作
- 是否使用 LLM

### 提交 POI 到店反馈

```text
POST /api/poi-feedback
```

请求示例：

```json
{
  "poi_id": "activity_001",
  "poi_name": "莫愁湖公园-湖心亭",
  "vote": "可以带狗",
  "note": "周末下午到店，牵引即可。",
  "source": "mobile_demo"
}
```

反馈会写入本地 `data/user_feedback.json`。该文件是运行时数据，默认不会提交到版本库。再次规划路线时，相关 POI 的宠物友好标签会把近期用户反馈纳入证据层。

如果某个 POI 收到“不可带宠”等负向反馈，下一次同类路线规划会自动降权该 POI，优先选择其他候选点。

### 反馈汇总

```text
GET /api/feedback-summary
```

返回全局反馈统计和按 POI 聚合的反馈统计。

## 接入真实 LLM

当前后端默认使用规则引擎，稳定可演示。如果配置 OpenAI-compatible API，可以启用 LLM 增强解释：

```text
LLM_API_KEY=你的APIKey
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_MODEL=gpt-4o-mini
```

后端不会把 API Key 暴露给前端。LLM 调用失败时自动回退到规则引擎。

## 后端测试

```powershell
python test_backend.py
```

测试会覆盖：

- 低压力路线
- 雨天备选路线
- 预算 60 降级策略
- 输入否定意图时避开咖啡
- POI 到店反馈持久化与标签证据升级

## 运行 Streamlit MVP

```powershell
streamlit run app.py
```

或：

```powershell
python -m streamlit run app.py
```

## 当前边界

- 当前版本没有爬取美团或大众点评。
- 当前前端使用本地 JSON 和轻量规则模拟 AI 解析，已经预留升级为真实 LLM 后端的空间。
- 宠物友好状态来自 POI 类别和关键词规则，真实上线前需要人工复核或引入更高质量数据源。

## 多区域与实时地图 API

当前后端已支持南京核心区域扩展：

- 新街口：核心商圈短时带宠消费路线；
- 鼓楼区：高校、公园、社区型低压力路线；
- 秦淮区：夫子庙、老门东文旅消费路线；
- 玄武区：玄武湖、紫金山周边活动路线。

相关接口：

```text
GET /api/areas
GET /api/live-pois?area_id=xuanwu&keyword=公园
POST /api/plan-route
```

`POST /api/plan-route` 可传入：

```json
{
  "user_message": "我在玄武区，想带中型犬去公园散步，不想消费",
  "area_id": "xuanwu",
  "use_live_data": true,
  "use_llm": true
}
```

如需批量采集新街口、鼓楼区、秦淮区、玄武区的 POI，可运行：

```powershell
python baidu_multi_area_collector.py
```

输出文件：

```text
fluffygo_nanjing_core_poi_raw.csv
```
