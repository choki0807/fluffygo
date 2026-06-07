# 面试发送话术

## 邮件/微信正文版本

您好，这是我面试中提到的 FluffyGo Demo 项目整理版。

FluffyGo 是一个 AI 宠物友好本地生活消费路线助手，面向城市养宠用户在核心商圈中的短时带宠出行需求，基于 POI 数据生成可执行的本地生活消费路线。

我主要完成了：

1. 百度地图 POI 采集与清洗；
2. 宠物友好状态、可信度、风险提示、路线角色等规则打标；
3. Demo JSON 数据结构设计；
4. Streamlit MVP 验证页；
5. Stitch 风格前端整合与交互展示。

项目中包含：

- 可运行 Demo 页面；
- 结构化 Demo 数据；
- POI 采集与转换脚本；
- 产品简介和演示流程说明。

如果您想快速查看效果，建议先打开 `stitch_demo.html` 版本；如果想看工程链路，可以查看 `baidu_poi_collector.py`、`convert_shortlist_to_demo_json.py` 和 `fluffygo_demo_poi.json`。

感谢查看，也期待进一步交流。

## GitHub 项目描述

FluffyGo: AI pet-friendly local lifestyle route assistant. A hackathon/interview demo that turns natural-language pet outing needs into structured local life routes using POI collection, rule-based pet-friendly tagging, route templates, and an interactive front-end demo.

## 面试中 30 秒介绍

FluffyGo 是我做的一个 AI 宠物友好本地生活路线 Demo。它不是简单搜索一个宠物友好店铺，而是把用户的一句话需求转化为一条可执行的消费路线，比如先短时散步，再去宠物友好咖啡，最后可选宠物用品或洗护补给。我完成了从百度地图 POI 采集、规则清洗、宠物友好打标、结构化 JSON 建模到前端展示的完整链路。这个项目的核心价值是把带宠出行从单点搜索升级为组合式本地生活消费场景。
