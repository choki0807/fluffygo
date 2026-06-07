# FluffyGo Backend Engine

更新时间：2026-05-18

## 当前目标

后端不再只是读取静态路线模板，而是根据用户一句话输入动态选择 POI、重排路线、输出风险和商业动作。

## 当前后端能力

`api_server.py` 现在包含以下能力：

- `parse_intent`：从用户输入中抽取地点、时间、宠物类型、宠物体型、预算、偏好、避免项和消费意图。
- `select_route_type`：根据雨天、拥挤、预算等信号选择 `main`、`low_stress`、`rainy_day`。
- `score_poi_for_intent`：按用户意图对 POI 打分。
- `build_dynamic_stops`：从 POI 分组中动态选出活动空间、消费点、服务点或雨天备选点。
- `build_risk_radar`：生成六类风险：人流拥挤、室内准入、犬型适配、天气变化、规则不确定、宠物压力。
- `build_feasibility`：生成出行可行性评分。
- `build_route_comparisons`：生成三条路线对比。
- `extract_commercial_actions`：把 POI 的交易动作映射成美团式动作。
- `build_decision_trace`：输出后端决策过程，便于面试和调试说明。

## 动态选点逻辑

POI 打分会综合：

- 宠物友好可信度：高 > 中 > 低。
- 宠物压力：低 > 中 > 高。
- 人流拥挤度：低 > 中 > 高。
- 距离：越近越优先。
- 消费意图：咖啡、餐饮、洗护、用品补给。
- 场景约束：雨天、避开拥挤、预算降低、犬型大小。

示例：

- 输入“想喝咖啡”会优先选择 `consumption_004` 缇里咖啡。
- 输入“想吃饭”会优先选择 `consumption_002` 段氏川味江湖菜馆。
- 输入“下雨”会优先选择 `rainy_day_backups`。
- 输入“预算只有 60”会移除宠物服务/补给点。
- 输入“不想太挤”会切换到 `low_stress` 并减少停留点。

## API

### `GET /api/health`

返回后端状态、数据文件状态和 LLM 配置状态。

### `GET /api/demo-data`

返回本地 Demo JSON 数据。

### `POST /api/plan-route`

请求示例：

```json
{
  "user_message": "我在南京新街口，带中型犬出门2.5小时，想喝咖啡，不想太挤，预算100",
  "use_llm": false
}
```

核心返回字段：

- `parsed_input`
- `selected_route_type`
- `response_summary`
- `route`
- `feasibility`
- `risk_radar`
- `route_comparisons`
- `community_modules`
- `commercial_actions`
- `decision_trace`
- `backend_capabilities`

## 测试

运行：

```powershell
python test_backend.py
```

当前测试覆盖：

- 三种路线类型：main、low_stress、rainy_day。
- 咖啡输入动态选咖啡 POI。
- 餐饮输入动态选餐饮 POI。
- 洗护输入动态保留宠物服务点。
- 预算 60 时移除服务/补给点。
- 返回可行性评分、风险雷达、路线对比、社区模块和决策链路。

## 下一步

1. 拆分 `api_server.py` 为模块化结构：
   - `intent_parser.py`
   - `poi_scoring.py`
   - `route_planner.py`
   - `risk_engine.py`
   - `commerce_engine.py`

2. 引入更细的 POI 标签：
   - 是否室内
   - 是否外摆
   - 犬型限制
   - 是否需要电话确认
   - 是否适合代溜

3. 接入真实 LLM：
   - LLM 负责自然语言理解和自然语言解释。
   - 规则引擎负责约束、排序和兜底。
   - 不允许 LLM 编造不存在的 POI。

