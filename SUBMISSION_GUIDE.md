# FluffyGo 6/7 提交说明

## 一句话简介

FluffyGo 是一个面向城市养宠用户的 AI 宠物友好本地生活路线助手。它把一句话带宠需求转化为可执行路线，并结合真实地图、宠物友好证据体系、风险雷达、路线对比、用户反馈闭环和本地生活交易动作。

## 推荐演示入口

```text
http://127.0.0.1:8000/stitch_demo.html
```

Windows 一键启动：

```bat
start_demo.bat
```

如果使用 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
```

后端健康检查：

```text
http://127.0.0.1:8001/api/health
```

Demo 完整度检查：

```text
http://127.0.0.1:8001/api/demo-readiness
```

## 路演建议输入

主场景：

```text
我在南京新街口，带中型犬出门2.5小时，想喝咖啡，不想太挤，预算100
```

只想散步：

```text
我在德基，带大型犬去公园散步，不想去咖啡店，不想消费
```

低预算：

```text
我预算只有30，想短时散步，不想花钱
```

雨天：

```text
如果下雨怎么办，最好室内一点，预算100
```

洗护补给：

```text
我在南京新街口，想顺路给狗洗护补给，预算120
```

## 路演讲法

1. FluffyGo 不是宠物频道的单点搜索，而是带宠出行决策助手。
2. 用户输入一句话后，后端解析地点、时间、宠物体型、预算、偏好和避免项。
3. 路线推荐会动态考虑预算、拥挤、雨天、服务意图和反馈记录。
4. 地图路线使用用户输入位置作为起点，并连接途经点和终点。
5. 宠物友好标签不是拍脑袋，而是结构化证据体系：
   - 商户后台确认
   - 近期用户反馈
   - POI 类目/商户名称
   - 外摆/露台/户外线索
   - 开放空间/街区场景
   - 室内/商场风险规则
6. 用户到店反馈会反哺标签和排序。负反馈会让 POI 降权并退出推荐。
7. 路线节点连接美团式交易动作，如查看门店、预约洗护、电话咨询、加入路线。

## 当前技术栈

- Python
- FastAPI
- Pydantic
- Requests
- Pandas
- python-dotenv
- 百度地图 Place API
- 百度地图 JavaScript API / WalkingRoute
- HTML / CSS / JavaScript
- 本地 JSON 数据
- 本地运行时用户反馈文件
- Streamlit MVP 备份页

## 已完成能力

- 百度地图 POI 采集与 CSV 输出
- shortlist 转结构化 JSON
- 动态意图解析
- 预算敏感路线生成
- 雨天/低压力/纯散步/洗护补给路线
- 真实百度步行地图
- 路线对比真实地图小预览
- 出行可行性评分
- 六边形风险雷达
- 宠物友好证据体系
- 到店反馈闭环
- C 端社区与代溜服务概念页
- 后端 readiness 检查

## 兜底说明

- 如果百度地图浏览器 AK 不可用，页面会显示离线地图兜底。
- 如果 LLM Key 未配置，后端使用规则引擎，Demo 仍可完整演示。
- 如果 PowerShell 禁止脚本，使用 `start_demo.bat` 启动。

## 提交前检查

```powershell
python test_backend.py
```

确认输出全部为 `OK`。
