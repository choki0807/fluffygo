# FluffyGo Project Context

更新时间：2026-05-18

## 项目一句话

FluffyGo 是一个面向城市养狗人的 AI 宠物友好本地生活消费路线助手。当前 Demo 聚焦南京新街口核心商圈，用户用一句话输入带宠出行需求，系统返回可执行、可调整、可交易的短时路线。

## 当前项目状态

当前项目已经不只是对话，主要代码和数据都已落在本地项目目录：

`C:\Users\Administrator\Documents\Codex\2026-04-26\prd-demo`

核心文件：

- `stitch_demo.html`：当前主 Demo 前端，移动端优先，包含首页、路线、社区、代溜、我的、社区详情页。
- `api_server.py`：FastAPI 后端，提供 Demo 数据、路线规划、可行性评分、风险雷达、路线对比、社区模块等接口。
- `fluffygo_demo_poi.json`：结构化 Demo POI 和路线数据。
- `baidu_poi_collector.py`：百度地图 POI 采集脚本。
- `convert_shortlist_to_demo_json.py`：shortlist CSV 转 Demo JSON 脚本。
- `test_backend.py`：后端最小验证测试。
- `start_demo.ps1`：启动 Demo 的 PowerShell 脚本。
- `assets/`：边牧风格 logo 和首页插图资源。
- `docs/`：产品、技术、演示和项目上下文文档。

## 当前前端能力

前端已经完成到可以作为黑客松/面试 Demo 展示的程度：

- 移动端 App 风格主界面。
- 底部 5 个导航：首页、路线、社区、代溜、我的。
- 顶部一句话输入和 4 个 icon 化快捷入口：宠物咖啡、避开拥挤、雨天备选、洗护补给。
- 路线页展示 AI 解析、推荐路线、站点 POI、风险提示、交易动作。
- 支持调整场景：拥挤、下雨、预算降低。
- 展示出行可行性评分、六边形风险雷达、路线对比卡。
- 社区图文内容可点击进入详情页。
- 代溜服务和个人主页已有 MVP 形态。
- 使用边牧风格 logo 和插图，增强宠物产品亲和力。

## 当前后端能力

后端已经具备基础 Demo 闭环：

- 读取 `fluffygo_demo_poi.json`。
- 根据用户输入和场景返回路线结果。
- 支持 main、low_stress、rainy_day 等路线类型。
- 输出结构化字段：解析结果、推荐路线、风险、评分、对比、社区模块。
- 有本地规则兜底，即使没有真实 LLM 也能演示。
- 预留了真实 LLM 接入配置思路，但当前重点还不是生产级 LLM 编排。

## 如何运行

推荐使用：

```powershell
cd C:\Users\Administrator\Documents\Codex\2026-04-26\prd-demo
powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
```

如果手动启动：

```powershell
cd C:\Users\Administrator\Documents\Codex\2026-04-26\prd-demo
python api_server.py
python -m http.server 8000 --bind 127.0.0.1
```

浏览器访问：

```text
http://127.0.0.1:8000/stitch_demo.html
```

验证后端：

```powershell
python test_backend.py
```

## 不要提交或分享的内容

- `.env` 里可能包含真实百度地图 AK 或后续 LLM Key，不应进入面试包或公开仓库。
- 面试或发送给他人时使用 `.env.example`。

## 当前交付包

面试/发送版本：

`C:\Users\Administrator\Documents\Codex\2026-04-26\prd-demo\fluffygo_interview_package.zip`

这个包已包含前端、后端、数据、文档和 assets。

## 明天建议优先级

建议明天优先做后端，而不是继续抠前端。

原因：

- 前端已经能表达产品形态和商业入口。
- 后端才决定项目技术含量：需求解析、动态路线生成、风险评分、标签反哺、交易动作推荐。
- 面试官更关心“为什么用户换一句话结果会变”，而不是按钮再精致一点。

## 明天建议任务拆解

1. 梳理后端模块边界：
   - 需求解析 `intent_parser`
   - POI 标签系统 `poi_tagger`
   - 路线生成 `route_planner`
   - 风险评分 `risk_engine`
   - 社区反馈反哺 `feedback_engine`
   - 交易动作推荐 `commerce_action_engine`

2. 让用户输入真正影响结果：
   - 输入“下雨”时提高室内/商场/雨天备选权重。
   - 输入“太挤”时降低核心商圈/高压力 POI 权重。
   - 输入“预算 60”时移除高消费洗护点，保留免费活动空间。
   - 输入“中型犬”时降低室内和小型犬限制点置信度。

3. 把评分逻辑显式化：
   - pet_friendly_score
   - feasibility_score
   - risk_radar
   - route_explainability

4. 再考虑真实 LLM：
   - LLM 负责自然语言理解和解释生成。
   - 规则引擎负责可控排序、风险约束和兜底。
   - 不要让 LLM 直接凭空编 POI。

## 当前产品定位

FluffyGo 不是单纯“宠物地图”，而是：

- 宠物友好本地生活路线生成器；
- 美团本地生活消费链路扩展；
- 用户反馈驱动的宠物友好标签资产系统；
- 可拓展到代溜、洗护、用品、咖啡餐饮等交易场景。

