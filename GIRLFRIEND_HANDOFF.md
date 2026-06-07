# FluffyGo 交接说明

## 快速运行

在项目根目录运行：

```powershell
pip install -r requirements.txt
start_demo.bat
```

或：

```powershell
python api_server.py
python -m http.server 8000 --bind 127.0.0.1
```

浏览器打开：

```text
http://127.0.0.1:8000/stitch_demo.html
```

后端健康检查：

```text
http://127.0.0.1:8001/api/health
```

## 最重要文件

- `stitch_demo.html`：最终前端 Demo 页面。
- `api_server.py`：FastAPI 后端与推荐逻辑。
- `fluffygo_demo_poi.json`：前端和后端使用的结构化 Demo 数据。
- `test_backend.py`：后端测试脚本。
- `README.md`：项目运行说明。
- `SUBMISSION_GUIDE.md`：提交和路演说明。
- `docs/FluffyGo_PRD.md`：产品需求文档。
- `docs/FluffyGo_项目介绍文档.md`：项目介绍、技术栈、创新点、商业价值。
- `docs/technical_notes.md`：技术说明。
- `docs/business_value_pitch.md`：商业价值路演文案。

## 当前 Demo 能力

- 移动端优先产品界面。
- 首页周边宠物友好目的地。
- 一句话输入生成路线。
- 多区域支持：新街口、鼓楼、秦淮、玄武。
- 百度地图真实步行路线。
- 多路线对比：低压力、省钱、雨天、纯散步、服务补给。
- 出行可行性评分、风险雷达、宠物友好证据体系。
- 用户反馈闭环，影响后续推荐排序。
- C 端社区情报和代溜服务概念。
- 个人记录页：路线收藏、到店确认、核验贡献、宠物档案。

## 注意事项

本交接包包含 `.env`，里面可能有真实百度地图 AK。可以本地协作使用，但不要直接公开上传 GitHub、比赛平台或网盘公开链接。

如果要公开提交，请删除 `.env`，只保留 `.env.example`。

## 下一步建议

1. 优先把项目部署成公网链接，提交表单里的“作品链接”要填公网 URL，不能填 localhost。
2. 部署后更新百度地图浏览器端 AK 的 Referer 白名单。
3. 检查手机端页面：首页、生成路线、地图、社区、记录页都要能打开。
4. 如果还有时间，做正式路演 PPT：痛点、方案、Demo、技术架构、商业价值、未来计划。
