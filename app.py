import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st


DATA_PATH = Path("fluffygo_demo_poi.json")
DEFAULT_USER_MESSAGE = (
    "我现在在南京新街口，想带一只中型犬出门 2.5 小时，不想去太挤的地方，"
    "能短暂散步，再找个宠物友好咖啡坐一会儿，预算 100 元以内。"
)


def load_demo_data() -> Optional[Dict[str, Any]]:
    if not DATA_PATH.exists():
        st.error(f"找不到 Demo 数据文件：{DATA_PATH.resolve()}")
        st.info("请先运行 convert_shortlist_to_demo_json.py 生成 fluffygo_demo_poi.json。")
        return None

    try:
        with DATA_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        st.error(f"JSON 文件格式错误：{exc}")
        return None


def safe_text(value: Any, fallback: str = "待补充") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def safe_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [safe_text(item, "") for item in value if safe_text(item, "")]
    return [safe_text(value)]


def join_list(value: Any) -> str:
    items = safe_list(value)
    return "、".join(items) if items else "待补充"


def get_all_pois(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pois = data.get("pois", {})
    if not isinstance(pois, dict):
        return []

    all_pois: List[Dict[str, Any]] = []
    for group in pois.values():
        if isinstance(group, list):
            all_pois.extend(item for item in group if isinstance(item, dict))
    return all_pois


def find_poi_by_id(data: Dict[str, Any], poi_id: str) -> Optional[Dict[str, Any]]:
    for poi in get_all_pois(data):
        if poi.get("poi_id") == poi_id:
            return poi
    return None


def find_route(data: Dict[str, Any], route_type: str) -> Optional[Dict[str, Any]]:
    for route in data.get("route_templates", []):
        if isinstance(route, dict) and route.get("route_type") == route_type:
            return route
    return None


def find_adjustment_case(data: Dict[str, Any], target_route_type: str) -> Optional[Dict[str, Any]]:
    for case in data.get("adjustment_cases", []):
        if isinstance(case, dict) and case.get("target_route_type") == target_route_type:
            return case
    return None


def render_header(data: Dict[str, Any]) -> None:
    project = data.get("project", {})
    st.title(safe_text(project.get("name"), "FluffyGo"))
    st.subheader("AI 宠物友好本地生活消费路线助手")
    st.caption("一句话，规划你和毛茸茸的友好出行。")
    st.markdown(
        f"**Demo 场景：** {safe_text(project.get('demo_area'), '南京新街口')}｜"
        f"{safe_text(project.get('scenario'), '核心商圈 2.5 小时短时带宠友好消费路线')}"
    )
    st.info(
        "FluffyGo 把“我想带宠出门”解析成可执行路线：街区活动空间 + 宠物友好消费点 + "
        "服务/补给节点，并把咖啡、餐饮、洗护、用品连接到美团本地生活交易。"
    )


def render_input_area() -> bool:
    st.markdown("### 1. 用户一句话输入")
    st.text_area("带宠出行需求", value=DEFAULT_USER_MESSAGE, height=110)
    return st.button("生成路线", type="primary", width="stretch")


def render_parsed_input(data: Dict[str, Any]) -> None:
    st.markdown("### 2. AI 解析结果")
    user_input = data.get("user_input_example", {})

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("出发位置", safe_text(user_input.get("location")))
    col2.metric("可用时间", safe_text(user_input.get("available_time")))
    col3.metric("宠物", f"{safe_text(user_input.get('pet_type'))}｜{safe_text(user_input.get('pet_size'))}")
    col4.metric("预算", f"{safe_text(user_input.get('budget'))} 元")

    st.dataframe(
        [
            {"字段": "偏好", "解析结果": join_list(user_input.get("preferences"))},
            {"字段": "避免项", "解析结果": join_list(user_input.get("avoid"))},
            {"字段": "消费意图", "解析结果": join_list(user_input.get("commercial_intent"))},
        ],
        hide_index=True,
        width="stretch",
    )


def format_meituan_action(action: Any) -> str:
    text = safe_text(action, "加入路线")
    if any(word in text for word in ("洗护", "服务", "预约")):
        return f"美团预约：{text}"
    if any(word in text for word in ("电话", "确认", "咨询")):
        return f"美团咨询：{text}"
    if any(word in text for word in ("团购", "咖啡", "餐饮", "消费")):
        return f"美团查看：{text}"
    return f"美团动作：{text}"


def render_poi_card(poi: Dict[str, Any], stop: Dict[str, Any]) -> None:
    pet = poi.get("pet_friendly", {})
    experience = poi.get("experience", {})
    business = poi.get("business", {})

    with st.container(border=True):
        st.markdown(f"#### {stop.get('order')}. {safe_text(poi.get('name'))}")
        st.caption(f"{safe_text(stop.get('role'))}｜建议停留 {safe_text(stop.get('suggested_stay_time'))}")
        st.write(safe_text(stop.get("reason")))

        col1, col2, col3 = st.columns(3)
        col1.write(f"**地址**：{safe_text(poi.get('address'))}")
        col2.write(f"**距离**：{safe_text(poi.get('distance_m'))} m")
        col3.write(f"**空间类型**：{safe_text(experience.get('space_type'))}")

        col4, col5, col6 = st.columns(3)
        col4.write(f"**宠物友好**：{safe_text(pet.get('status'))}")
        col5.write(f"**可信度**：{safe_text(pet.get('confidence_level'))}")
        col6.write(f"**适合犬型**：{safe_text(pet.get('suitable_pet_size'))}")

        col7, col8 = st.columns(2)
        col7.write(f"**人流拥挤度**：{safe_text(experience.get('crowd_level'))}")
        col8.write(f"**宠物压力等级**：{safe_text(experience.get('pet_stress_level'))}")

        st.write(f"**证据来源**：{safe_text(pet.get('evidence_source'))}")
        st.info(f"风险提示：{safe_text(poi.get('risk_note'))}")
        st.button(
            format_meituan_action(business.get("transaction_action")),
            key=f"action_{poi.get('poi_id')}_{stop.get('order')}",
            width="stretch",
        )


def render_route(data: Dict[str, Any], route_type: str) -> None:
    route = find_route(data, route_type)
    if not route:
        st.warning(f"未找到 route_type = {route_type} 的路线模板。")
        return

    st.markdown("### 3. 推荐路线")
    with st.container(border=True):
        st.markdown(f"## {safe_text(route.get('route_name'))}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("时间", safe_text(route.get("estimated_time")))
        col2.metric("预算", safe_text(route.get("estimated_budget")))
        col3.metric("宠物友好分", safe_text(route.get("pet_friendly_score")))
        col4.metric("压力等级", safe_text(route.get("pet_stress_level")))
        st.write(safe_text(route.get("summary")))
        st.warning(safe_text(route.get("risk_summary")))

    stops = route.get("stops", [])
    if not isinstance(stops, list) or not stops:
        st.warning("当前路线暂无站点，请检查 route_templates.stops 数据。")
        return

    for stop in stops:
        if not isinstance(stop, dict):
            continue
        poi = find_poi_by_id(data, stop.get("poi_id", ""))
        if poi:
            render_poi_card(poi, stop)
        else:
            st.warning(f"找不到站点 POI：{stop.get('poi_id')}")


def render_adjustment_cases(data: Dict[str, Any]) -> None:
    st.markdown("### 4. 多轮调整场景")
    col1, col2, col3 = st.columns(3)

    if col1.button("现在太挤了", width="stretch"):
        case = find_adjustment_case(data, "low_stress")
        st.session_state.route_type = "low_stress"
        st.session_state.adjustment_message = case.get("response_summary") if case else "已切换到低压力路线。"

    if col2.button("下雨了怎么办", width="stretch"):
        case = find_adjustment_case(data, "rainy_day")
        st.session_state.route_type = "rainy_day"
        st.session_state.adjustment_message = case.get("response_summary") if case else "已切换到雨天备选路线。"

    if col3.button("预算只有 60", width="stretch"):
        case = next(
            (
                item
                for item in data.get("adjustment_cases", [])
                if isinstance(item, dict) and item.get("case_id") == "adjust_budget_001"
            ),
            None,
        )
        st.session_state.route_type = "main"
        st.session_state.adjustment_message = (
            case.get("response_summary")
            if case
            else "已为你保留免费街区活动空间，优先选择低客单消费点，并移除洗护等高消费服务点。"
        )

    if st.session_state.get("adjustment_message"):
        st.success(st.session_state.adjustment_message)


def render_business_value() -> None:
    st.markdown("### 为什么这对美团有价值？")
    st.markdown(
        """
- 将“带宠出行”从单点搜索升级为组合式本地生活消费路线；
- 路线中可连接咖啡、餐饮、洗护、用品等美团交易入口；
- 用户反馈可反哺宠物友好标签，沉淀高质量本地生活数据资产。
"""
    )


def main() -> None:
    st.set_page_config(page_title="FluffyGo Demo", page_icon="🐾", layout="wide")
    data = load_demo_data()
    if not data:
        return

    st.session_state.setdefault("route_type", "main")
    st.session_state.setdefault("route_generated", False)
    st.session_state.setdefault("adjustment_message", "")

    render_header(data)
    if render_input_area():
        st.session_state.route_generated = True
        st.session_state.route_type = "main"
        st.session_state.adjustment_message = ""

    if st.session_state.route_generated:
        render_parsed_input(data)
        render_adjustment_cases(data)
        render_route(data, st.session_state.route_type)
        render_business_value()
    else:
        st.info("点击“生成路线”后展示 AI 解析结果、推荐路线和可调整场景。")


if __name__ == "__main__":
    main()
