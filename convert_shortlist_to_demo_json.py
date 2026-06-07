import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


INPUT_CSV = Path("fluffygo_xinjiekou_poi_shortlist.csv")
OUTPUT_JSON = Path("fluffygo_demo_poi.json")

ROLE_CONFIG = {
    "短时活动空间": {
        "group_key": "activity_spaces",
        "id_prefix": "activity",
    },
    "宠物友好消费点": {
        "group_key": "consumption_points",
        "id_prefix": "consumption",
    },
    "宠物服务/补给点": {
        "group_key": "pet_services",
        "id_prefix": "service",
    },
    "雨天备选点": {
        "group_key": "rainy_day_backups",
        "id_prefix": "rainy",
    },
}

STRESS_RANK = {"低": 0, "中": 1, "高": 2}
CROWD_RANK = {"低": 0, "中": 1, "高": 2}


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def to_number(value: Any) -> Optional[float]:
    if value is None or pd.isna(value) or clean_text(value) == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def to_bool_review(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return True
    return text == "是"


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


def poi_to_json(row: pd.Series, poi_id: str) -> Dict[str, Any]:
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
            "status": clean_text(row.get("pet_friendly_status")),
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
            ),
        },
        "business": {
            "transaction_action": clean_text(row.get("transaction_action")),
        },
        "risk_note": clean_text(row.get("risk_note")),
        "manual_review_required": to_bool_review(row.get("manual_review_required")),
        "demo_selected_reason": clean_text(row.get("demo_selected_reason")),
    }


def group_pois(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    grouped = {
        "activity_spaces": [],
        "consumption_points": [],
        "pet_services": [],
        "rainy_day_backups": [],
    }
    counters = {config["group_key"]: 0 for config in ROLE_CONFIG.values()}

    for _, row in df.iterrows():
        role = clean_text(row.get("route_role"))
        config = ROLE_CONFIG.get(role)
        if not config:
            continue

        group_key = config["group_key"]
        counters[group_key] += 1
        poi_id = f"{config['id_prefix']}_{counters[group_key]:03d}"
        grouped[group_key].append(poi_to_json(row, poi_id))

    return grouped


def first_or_none(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return items[0] if items else None


def sort_low_stress(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            STRESS_RANK.get(item["experience"]["pet_stress_level"], 9),
            CROWD_RANK.get(item["experience"]["crowd_level"], 9),
            item["distance_m"] if item["distance_m"] is not None else 999999,
        ),
    )


def make_stop(
    order: int,
    poi: Dict[str, Any],
    role: str,
    suggested_stay_time: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "order": order,
        "poi_id": poi["poi_id"],
        "role": role,
        "suggested_stay_time": suggested_stay_time,
        "reason": reason,
    }


def build_route_templates(pois: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    activity = first_or_none(pois["activity_spaces"])
    consumption = first_or_none(pois["consumption_points"])
    service = first_or_none(pois["pet_services"])
    rainy = first_or_none(pois["rainy_day_backups"])

    routes: List[Dict[str, Any]] = []

    main_stops = []
    if activity:
        main_stops.append(make_stop(1, activity, "短时活动空间", "30-45分钟", "适合中型犬短时牵引散步，距离新街口核心消费点较近。"))
    if consumption:
        main_stops.append(make_stop(len(main_stops) + 1, consumption, "宠物友好消费点", "45-60分钟", "作为短逛后的咖啡或轻食消费点，适合做 Demo 转化节点。"))
    if service:
        main_stops.append(make_stop(len(main_stops) + 1, service, "宠物服务/补给点", "15-30分钟", "可作为用品补给或护理咨询的可选节点。"))
    routes.append({
        "route_id": "route_main_001",
        "route_name": "新街口轻松短逛咖啡线",
        "route_type": "main",
        "estimated_time": "2-2.5小时",
        "estimated_budget": "60-100元",
        "pet_friendly_score": 4.0,
        "pet_stress_level": "中",
        "stops": main_stops,
        "summary": "适合周末下午在新街口进行短时带宠出行，兼顾短暂停留、咖啡消费和可选宠物补给。",
        "risk_summary": "新街口周末人流较大，建议全程牵引并避开 16:00-18:00 高峰。",
    })

    low_activity = first_or_none(sort_low_stress(pois["activity_spaces"]))
    low_consumption = first_or_none(sort_low_stress(pois["consumption_points"]))
    low_service = first_or_none(sort_low_stress(pois["pet_services"]))
    low_stops = []
    if low_activity:
        low_stops.append(make_stop(1, low_activity, "短时活动空间", "20-30分钟", "优先选择宠物压力较低、停留时间可控的活动空间。"))
    if low_consumption:
        low_stops.append(make_stop(len(low_stops) + 1, low_consumption, "宠物友好消费点", "30-45分钟", "减少停留点并优先选择低压力消费节点。"))
    if low_service:
        low_stops.append(make_stop(len(low_stops) + 1, low_service, "宠物服务/补给点", "10-20分钟", "仅保留必要补给，避免在拥挤区域长时间逗留。"))
    routes.append({
        "route_id": "route_low_stress_001",
        "route_name": "新街口低压力避峰线",
        "route_type": "low_stress",
        "estimated_time": "1.5-2小时",
        "estimated_budget": "40-80元",
        "pet_friendly_score": 3.8,
        "pet_stress_level": "低",
        "stops": low_stops,
        "summary": "适合对拥挤敏感的中型犬，减少停留点并优先选择低压力 POI。",
        "risk_summary": "仍需避开核心商圈高峰，并在进入室内或门店前确认携宠规则。",
    })

    rainy_stops = []
    if rainy:
        rainy_stops.append(make_stop(1, rainy, "雨天备选点", "45-60分钟", "雨天优先选择室内或半室内空间，降低天气影响。"))
    rainy_consumption = first_or_none(sort_low_stress(pois["consumption_points"]))
    if rainy_consumption:
        rainy_stops.append(make_stop(len(rainy_stops) + 1, rainy_consumption, "宠物友好消费点", "30-45分钟", "搭配消费点，保留咖啡或轻食场景。"))
    rainy_service = first_or_none(sort_low_stress(pois["pet_services"]))
    if rainy_service:
        rainy_stops.append(make_stop(len(rainy_stops) + 1, rainy_service, "宠物服务/补给点", "15-30分钟", "可作为雨具、用品或洗护咨询补给点。"))
    routes.append({
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
    })

    return routes


def build_adjustment_cases() -> List[Dict[str, str]]:
    return [
        {
            "case_id": "adjust_crowded_001",
            "user_message": "现在太挤了，能不能换一条低压力路线？",
            "system_strategy": "切换到低压力路线，优先选择商圈边缘、低拥挤度、低宠物压力的 POI。",
            "target_route_type": "low_stress",
            "response_summary": "已为你切换为新街口低压力避峰线，减少非必要停留点，并优先选择人流较低的外摆友好咖啡。",
        },
        {
            "case_id": "adjust_rainy_001",
            "user_message": "如果下雨怎么办？",
            "system_strategy": "切换到雨天备选路线，优先半室内、外摆或宠物用品点，并减少露天步行距离。",
            "target_route_type": "rainy_day",
            "response_summary": "已为你切换为新街口雨天友好备选线，优先选择可避雨的停靠点并保留咖啡消费场景。",
        },
        {
            "case_id": "adjust_budget_001",
            "user_message": "我预算只有 60。",
            "system_strategy": "保留免费街区活动空间，选择低客单消费点，移除洗护等高消费服务点。",
            "target_route_type": "main",
            "response_summary": "已将路线压缩到 60 元预算内，保留免费活动空间和低客单咖啡点，暂不安排洗护服务。",
        },
    ]


def build_demo_json(df: pd.DataFrame) -> Dict[str, Any]:
    pois = group_pois(df)
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
            "preferences": ["短时散步", "宠物友好咖啡", "低拥挤度"],
            "avoid": ["太拥挤", "太远"],
            "commercial_intent": ["咖啡", "轻食", "可选用品补给"],
        },
        "pois": pois,
        "route_templates": build_route_templates(pois),
        "adjustment_cases": build_adjustment_cases(),
    }


def main() -> None:
    if not INPUT_CSV.exists():
        raise SystemExit(f"Input file not found: {INPUT_CSV.resolve()}")

    df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig").fillna("")
    demo_json = build_demo_json(df)

    with OUTPUT_JSON.open("w", encoding="utf-8") as file:
        json.dump(demo_json, file, ensure_ascii=False, indent=2)

    group_counts = {key: len(value) for key, value in demo_json["pois"].items()}
    print(f"Input file: {INPUT_CSV.resolve()}")
    print(f"Output file: {OUTPUT_JSON.resolve()}")
    print(f"POI total: {sum(group_counts.values())}")
    print(f"activity_spaces: {group_counts['activity_spaces']}")
    print(f"consumption_points: {group_counts['consumption_points']}")
    print(f"pet_services: {group_counts['pet_services']}")
    print(f"rainy_day_backups: {group_counts['rainy_day_backups']}")
    print(f"route_templates: {len(demo_json['route_templates'])}")
    print(f"adjustment_cases: {len(demo_json['adjustment_cases'])}")


if __name__ == "__main__":
    main()
