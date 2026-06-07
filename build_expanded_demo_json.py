import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


INPUT_CSV = Path("fluffygo_xinjiekou_poi_raw.csv")
OUTPUT_JSON = Path("fluffygo_demo_poi.json")

GROUP_LIMITS = {
    "activity_spaces": 24,
    "consumption_points": 36,
    "pet_services": 24,
    "rainy_day_backups": 18,
}

ROLE_LABELS = {
    "activity_spaces": "短时活动空间",
    "consumption_points": "宠物友好消费点",
    "pet_services": "宠物服务/补给点",
    "rainy_day_backups": "雨天备选点",
}

ID_PREFIX = {
    "activity_spaces": "activity",
    "consumption_points": "consumption",
    "pet_services": "service",
    "rainy_day_backups": "rainy",
}

CONFIDENCE_RANK = {"高": 0, "中": 1, "低": 2}
STRESS_RANK = {"低": 0, "中": 1, "高": 2}
CROWD_RANK = {"低": 0, "中": 1, "高": 2}


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def to_number(value: Any) -> Optional[float]:
    text = clean_text(value)
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def contains(text: str, words: Tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def row_text(row: pd.Series) -> str:
    fields = [
        "poi_name",
        "category",
        "source_keyword",
        "address",
        "pet_friendly_status",
        "space_type",
    ]
    return " ".join(clean_text(row.get(field)) for field in fields)


def infer_group(row: pd.Series) -> Optional[str]:
    text = row_text(row)
    name_category = f"{clean_text(row.get('poi_name'))} {clean_text(row.get('category'))}"
    name = clean_text(row.get("poi_name"))
    category = clean_text(row.get("category"))

    if contains(name_category, ("宠物", "动物医院", "宠物医院", "宠物服务", "宠物用品", "洗护", "宠物美容")):
        return "pet_services"

    indoor_excluded = ("停车场", "出入口", "写字楼", "住宅区", "酒店", "门", "公共厕所")
    if contains(name_category, ("商场", "购物中心", "商城", "百货", "商业综合体", "书店")) and not contains(category, indoor_excluded):
        return "rainy_day_backups"

    activity_excluded = (
        "出入口",
        "地铁",
        "公交",
        "停车场",
        "酒店",
        "房地产",
        "公司企业",
        "购物",
        "美食",
        "丽人",
        "洗衣",
        "公共厕所",
        "政府机构",
        "售票处",
    )
    is_true_park = contains(category, ("旅游景点;公园", "旅游景点;植物园", "休闲娱乐;休闲广场"))
    is_named_walk_space = contains(name, ("步行街", "商业街社区", "玄武广场", "绿地广场"))
    is_lake_scenic = contains(name, ("玄武湖景区", "南湖公园", "莫愁湖公园", "白马公园", "和平公园", "鼓楼公园"))
    if is_true_park or is_named_walk_space or is_lake_scenic:
        if not contains(category, activity_excluded):
            return "activity_spaces"

    if contains(name_category, ("咖啡", "餐厅", "中餐厅", "外国餐厅", "菜馆", "料理", "小吃", "茶饮", "甜品", "轻食", "美食")):
        return "consumption_points"

    if contains(text, ("外摆", "露台", "户外")) and contains(clean_text(row.get("category")), ("美食", "餐饮", "咖啡")):
        return "consumption_points"

    return None


def sort_key(row: pd.Series) -> Tuple[int, int, int, int, str]:
    confidence = CONFIDENCE_RANK.get(clean_text(row.get("confidence_level")), 9)
    stress = STRESS_RANK.get(clean_text(row.get("pet_stress_level")), 9)
    crowd = CROWD_RANK.get(clean_text(row.get("crowd_level")), 9)
    distance = int(to_number(row.get("distance")) or 999999)
    return confidence, stress, crowd, distance, clean_text(row.get("poi_name"))


def role_reason(group_key: str) -> str:
    return {
        "activity_spaces": "适合作为遛宠路线中的短时活动、牵引散步或临时停留空间",
        "consumption_points": "适合作为路线中的咖啡、餐饮、轻食或低客单消费停靠点",
        "pet_services": "适合作为宠物洗护、用品补给、医疗咨询或到店服务节点",
        "rainy_day_backups": "适合作为雨天、炎热天气或临时避雨时的备选空间",
    }[group_key]


def split_tags(*values: Any) -> List[str]:
    tags: List[str] = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        normalized = text.replace("、", ",").replace("/", ",").replace(";", ",").replace("；", ",")
        for part in normalized.split(","):
            tag = part.strip()
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def infer_cost_tier(row: pd.Series, group_key: str) -> str:
    text = row_text(row)
    if group_key == "activity_spaces":
        return "0-20元"
    if group_key == "pet_services":
        return "60-150元"
    if contains(text, ("小吃", "茶饮", "瑞幸", "甜品")):
        return "20-60元"
    if contains(text, ("咖啡", "轻食")):
        return "30-80元"
    if group_key == "rainy_day_backups":
        return "0-100元"
    return "60-120元"


def poi_to_json(row: pd.Series, poi_id: str, group_key: str) -> Dict[str, Any]:
    cost_tier = infer_cost_tier(row, group_key)
    return {
        "poi_id": poi_id,
        "name": clean_text(row.get("poi_name")),
        "category": clean_text(row.get("category")),
        "address": clean_text(row.get("address")),
        "distance_m": to_number(row.get("distance")),
        "location": {
            "lat": to_number(row.get("lat")),
            "lng": to_number(row.get("lng")),
        },
        "pet_friendly": {
            "status": clean_text(row.get("pet_friendly_status"),),
            "confidence_level": clean_text(row.get("confidence_level")),
            "evidence_source": clean_text(row.get("evidence_source")),
            "evidence_text": clean_text(row.get("evidence_text")),
            "suitable_pet_size": clean_text(row.get("suitable_pet_size")),
        },
        "experience": {
            "space_type": clean_text(row.get("space_type")),
            "crowd_level": clean_text(row.get("crowd_level")),
            "pet_stress_level": clean_text(row.get("pet_stress_level")),
            "tags": split_tags(
                row.get("category"),
                row.get("space_type"),
                row.get("pet_friendly_status"),
                row.get("source_keyword"),
                cost_tier,
            ),
        },
        "business": {
            "transaction_action": clean_text(row.get("transaction_action")),
            "estimated_cost": cost_tier,
        },
        "risk_note": clean_text(row.get("risk_note")),
        "manual_review_required": True,
        "demo_selected_reason": role_reason(group_key),
    }


def build_grouped_pois(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    work_df = df.copy()
    work_df["_group"] = work_df.apply(infer_group, axis=1)
    work_df = work_df[work_df["_group"].notna()].drop_duplicates(subset=["poi_name"], keep="first")

    grouped: Dict[str, List[Dict[str, Any]]] = {key: [] for key in GROUP_LIMITS}
    for group_key, limit in GROUP_LIMITS.items():
        candidates = work_df[work_df["_group"] == group_key].copy()
        candidates["_sort"] = candidates.apply(sort_key, axis=1)
        candidates = candidates.sort_values("_sort").head(limit)
        for index, (_, row) in enumerate(candidates.iterrows(), start=1):
            poi_id = f"{ID_PREFIX[group_key]}_{index:03d}"
            grouped[group_key].append(poi_to_json(row, poi_id, group_key))

    return grouped


def first(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return items[0] if items else None


def make_stop(order: int, poi: Dict[str, Any], role: str, stay_time: str, reason: str) -> Dict[str, Any]:
    return {
        "order": order,
        "poi_id": poi["poi_id"],
        "role": role,
        "suggested_stay_time": stay_time,
        "reason": reason,
    }


def build_route_templates(pois: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    activity = first(pois["activity_spaces"])
    consumption = first(pois["consumption_points"])
    service = first(pois["pet_services"])
    rainy = first(pois["rainy_day_backups"])

    main_stops: List[Dict[str, Any]] = []
    if activity:
        main_stops.append(make_stop(1, activity, "短时活动空间", "30-45分钟", "适合中型犬短时牵引散步，距离核心消费点较近。"))
    if consumption:
        main_stops.append(make_stop(len(main_stops) + 1, consumption, "宠物友好消费点", "45-60分钟", "作为散步后的消费停靠点，适合承接低客单本地生活交易。"))
    if service:
        main_stops.append(make_stop(len(main_stops) + 1, service, "宠物服务/补给点", "15-30分钟", "可作为用品补给或护理咨询的可选节点。"))

    low_stops: List[Dict[str, Any]] = []
    if activity:
        low_stops.append(make_stop(1, activity, "短时活动空间", "20-35分钟", "优先选择可控的活动空间，减少宠物压力。"))
    if consumption:
        low_stops.append(make_stop(2, consumption, "宠物友好消费点", "30-45分钟", "保留一个低压力消费停靠点，避免路线过长。"))

    rainy_stops: List[Dict[str, Any]] = []
    if rainy:
        rainy_stops.append(make_stop(1, rainy, "雨天备选点", "45-60分钟", "雨天优先选择室内或半室内空间。"))
    if consumption:
        rainy_stops.append(make_stop(len(rainy_stops) + 1, consumption, "宠物友好消费点", "30-45分钟", "搭配消费点，保留轻消费场景。"))
    if service:
        rainy_stops.append(make_stop(len(rainy_stops) + 1, service, "宠物服务/补给点", "15-30分钟", "可作为雨天用品或洗护咨询补给点。"))

    return [
        {
            "route_id": "route_main_001",
            "route_name": "新街口轻松短逛消费线",
            "route_type": "main",
            "estimated_time": "2-2.5小时",
            "estimated_budget": "60-100元",
            "pet_friendly_score": 4.0,
            "pet_stress_level": "中",
            "stops": main_stops,
            "summary": "适合周末下午在新街口进行短时带宠出行，兼顾短暂停留、消费和可选宠物补给。",
            "risk_summary": "新街口周末人流较大，建议全程牵引并避开 16:00-18:00 高峰。",
        },
        {
            "route_id": "route_low_stress_001",
            "route_name": "新街口低压力避峰线",
            "route_type": "low_stress",
            "estimated_time": "1.5-2小时",
            "estimated_budget": "40-80元",
            "pet_friendly_score": 3.8,
            "pet_stress_level": "低",
            "stops": low_stops,
            "summary": "适合对拥挤敏感的宠物，减少停留点并优先选择低压力 POI。",
            "risk_summary": "仍需避开核心商圈高峰，并在进入室内或门店前确认携宠规则。",
        },
        {
            "route_id": "route_rainy_001",
            "route_name": "新街口雨天友好备选线",
            "route_type": "rainy_day",
            "estimated_time": "1.5-2小时",
            "estimated_budget": "60-100元",
            "pet_friendly_score": 3.6,
            "pet_stress_level": "中",
            "stops": rainy_stops,
            "summary": "适合遇到降雨时快速切换，优先使用雨天备选点并搭配消费或补给节点。",
            "risk_summary": "室内区域是否允许携宠需提前确认，雨天路面湿滑建议缩短步行距离。",
        },
    ]


def build_adjustment_cases() -> List[Dict[str, str]]:
    return [
        {
            "case_id": "adjust_crowded_001",
            "user_message": "现在太挤了，能不能换一条低压力路线？",
            "system_strategy": "切换到低压力路线，优先选择商圈边缘、低拥挤度、低宠物压力的 POI。",
            "target_route_type": "low_stress",
            "response_summary": "已为你切换为新街口低压力避峰线，减少非必要停留点，并优先选择人流较低的 POI。",
        },
        {
            "case_id": "adjust_rainy_001",
            "user_message": "如果下雨怎么办？",
            "system_strategy": "切换到雨天备选路线，优先室内、半室内、商场或宠物用品点。",
            "target_route_type": "rainy_day",
            "response_summary": "已为你切换为新街口雨天友好备选线，优先选择可避雨停靠点。",
        },
        {
            "case_id": "adjust_budget_001",
            "user_message": "我预算只有 60。",
            "system_strategy": "预算作为硬约束，保留免费活动空间和低客单消费点，移除高消费服务点。",
            "target_route_type": "main",
            "response_summary": "已按 60 元预算重新规划，优先免费活动空间和低客单停靠点。",
        },
    ]


def build_demo_json(pois: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {
        "project": {
            "name": "FluffyGo",
            "demo_area": "南京新街口",
            "scenario": "核心商圈 2.5 小时短时带宠友好消费路线",
            "description": "面向城市养狗人在高密度核心商圈中的短时带宠出行需求，生成街区活动空间、宠物友好消费点和宠物服务点组合路线。",
        },
        "user_input_example": {
            "location": "南京新街口",
            "available_time": "2.5小时",
            "pet_type": "狗",
            "pet_size": "中型犬",
            "budget": 100,
            "preferences": ["短时散步", "低拥挤度"],
            "avoid": ["太拥挤", "太远"],
            "commercial_intent": ["咖啡", "轻食", "可选用品补给"],
        },
        "pois": pois,
        "route_templates": build_route_templates(pois),
        "adjustment_cases": build_adjustment_cases(),
    }


def main() -> None:
    if not INPUT_CSV.exists():
        raise SystemExit(f"Missing input CSV: {INPUT_CSV.resolve()}")

    df = pd.read_csv(INPUT_CSV)
    pois = build_grouped_pois(df)
    payload = build_demo_json(pois)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {key: len(value) for key, value in pois.items()}
    print(f"Input: {INPUT_CSV.resolve()}")
    print(f"Output: {OUTPUT_JSON.resolve()}")
    print(f"POI counts: {counts}, total={sum(counts.values())}")


if __name__ == "__main__":
    main()
