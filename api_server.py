import json
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "fluffygo_demo_poi.json"
DATA_DIR = BASE_DIR / "data"
FEEDBACK_PATH = DATA_DIR / "user_feedback.json"
DEFAULT_LLM_URL = "https://api.openai.com/v1/chat/completions"
SUPPORTED_ROUTE_TYPES = {
    "main",
    "balanced",
    "budget_saver",
    "low_stress",
    "rainy_day",
    "service_supply",
    "quick_walk",
}
BASE_ROUTE_TYPE = {
    "balanced": "main",
    "budget_saver": "main",
    "service_supply": "main",
    "quick_walk": "main",
}

app = FastAPI(
    title="FluffyGo Route Planning API",
    version="1.0.0",
    description="LLM-ready backend for the FluffyGo pet-friendly local life route demo.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (images, etc.)
app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")


@app.get("/")
async def serve_frontend():
    return FileResponse(BASE_DIR / "stitch_demo.html", media_type="text/html")


@app.get("/fluffygo_demo_poi.json")
async def serve_demo_data():
    return FileResponse(BASE_DIR / "fluffygo_demo_poi.json", media_type="application/json")


class PlanRouteRequest(BaseModel):
    user_message: str = Field(..., min_length=1)
    force_route_type: Optional[str] = None
    use_llm: bool = True
    use_live_data: bool = False
    area_id: Optional[str] = None


class PoiFeedbackRequest(BaseModel):
    poi_id: str = Field(..., min_length=1)
    poi_name: str = ""
    vote: str = Field(..., min_length=1)
    note: str = ""
    source: str = "demo_user"


def load_demo_data() -> Dict[str, Any]:
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Missing data file: {DATA_PATH.resolve()}")

    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_feedback_log() -> List[Dict[str, Any]]:
    if not FEEDBACK_PATH.exists():
        return []
    with FEEDBACK_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else []


def save_feedback_log(items: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with FEEDBACK_PATH.open("w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def unique(items: List[str]) -> List[str]:
    output: List[str] = []
    for item in items:
        value = clean_text(item)
        if value and value not in output:
            output.append(value)
    return output


def feedback_sentiment(vote: str) -> str:
    text_value = clean_text(vote)
    if any(word in text_value for word in ["不可", "不能", "拒绝", "关闭", "不友好", "差"]):
        return "negative"
    if any(word in text_value for word in ["只限", "外摆", "小型", "需确认", "一般"]):
        return "limited"
    return "positive"


def summarize_feedback(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(items)
    positive = sum(1 for item in items if item.get("sentiment") == "positive")
    limited = sum(1 for item in items if item.get("sentiment") == "limited")
    negative = sum(1 for item in items if item.get("sentiment") == "negative")
    return {
        "total": total,
        "positive": positive,
        "limited": limited,
        "negative": negative,
        "latest": items[-3:],
    }


def feedback_by_poi() -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in load_feedback_log():
        poi_id = clean_text(item.get("poi_id"))
        if poi_id:
            grouped.setdefault(poi_id, []).append(item)
    return {poi_id: summarize_feedback(items) for poi_id, items in grouped.items()}


def empty_feedback_summary() -> Dict[str, Any]:
    return summarize_feedback([])


def enrich_policy_with_feedback(policy: Dict[str, Any], feedback: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(policy)
    enriched["evidence_items"] = list(policy.get("evidence_items", []))
    positive = int(feedback.get("positive", 0))
    limited = int(feedback.get("limited", 0))
    negative = int(feedback.get("negative", 0))
    total = int(feedback.get("total", 0))
    basis = clean_text(enriched.get("basis"))

    if total <= 0:
        enriched["user_feedback"] = empty_feedback_summary()
        enriched["evidence_gaps"] = evidence_gaps_for_policy(enriched)
        enriched["review_status"] = review_status_for_policy(enriched)
        enriched["trust_explanation"] = trust_explanation_for_policy(enriched)
        return enriched

    if positive > negative and positive >= 1:
        enriched["layer"] = "L2"
        enriched["label"] = "近期用户验证"
        enriched["evidence_level"] = "用户反馈"
        enriched["score"] = max(int(enriched.get("score", 40)), min(88, 72 + positive * 6 + limited * 2))
        basis = f"{basis}｜近期用户验证：{positive} 条正向反馈。"
        enriched["evidence_items"].append(make_evidence_item(
            "recent_positive_user_feedback",
            "user_feedback",
            "近期用户到店反馈",
            f"{positive} 条正向反馈支持当前携宠判断。",
            "strong",
            min(88, 72 + positive * 6),
            "recent_runtime",
            "review_recommended",
        ))
        if limited:
            basis = f"{basis} 另有 {limited} 条限制条件反馈，建议展示限制说明。"
            enriched["evidence_items"].append(make_evidence_item(
                "recent_limited_user_feedback",
                "user_feedback",
                "近期用户限制反馈",
                f"{limited} 条反馈提示存在外摆、犬型或时段限制。",
                "medium",
                62,
                "recent_runtime",
                "review_recommended",
            ))
    elif negative > 0 and negative >= positive:
        enriched["layer"] = "L6"
        enriched["label"] = "近期负反馈待复核"
        enriched["evidence_level"] = "负反馈"
        enriched["score"] = max(30, int(enriched.get("score", 40)) - 18)
        basis = f"{basis}｜近期存在 {negative} 条负向反馈，需降权并进入人工复核。"
        enriched["evidence_items"].append(make_evidence_item(
            "recent_negative_user_feedback",
            "user_feedback",
            "近期用户负反馈",
            f"{negative} 条负反馈提示当前点位可能不可携宠。",
            "strong_negative",
            -90,
            "recent_runtime",
            "manual_review_required",
        ))
    elif limited > 0:
        enriched["label"] = "有条件宠物友好"
        enriched["evidence_level"] = "用户限制反馈"
        enriched["score"] = max(int(enriched.get("score", 40)), 62)
        basis = f"{basis}｜近期用户反馈存在限制条件：{limited} 条。"
        enriched["evidence_items"].append(make_evidence_item(
            "recent_limited_user_feedback",
            "user_feedback",
            "近期用户限制反馈",
            f"{limited} 条反馈提示存在外摆、犬型或时段限制。",
            "medium",
            62,
            "recent_runtime",
            "review_recommended",
        ))

    enriched["basis"] = basis
    enriched["user_feedback"] = feedback
    enriched["evidence_gaps"] = evidence_gaps_for_policy(enriched)
    enriched["review_status"] = review_status_for_policy(enriched)
    enriched["trust_explanation"] = trust_explanation_for_policy(enriched)
    return enriched


def poi_feedback_stats(poi: Dict[str, Any], feedback_stats: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    stats = feedback_stats if feedback_stats is not None else feedback_by_poi()
    return stats.get(clean_text(poi.get("poi_id")), empty_feedback_summary())


def feedback_ranking_delta(poi: Dict[str, Any], route_type: str, feedback_stats: Optional[Dict[str, Dict[str, Any]]] = None) -> int:
    feedback = poi_feedback_stats(poi, feedback_stats)
    positive = int(feedback.get("positive", 0))
    limited = int(feedback.get("limited", 0))
    negative = int(feedback.get("negative", 0))
    total = int(feedback.get("total", 0))
    if total <= 0:
        return 0

    delta = positive * 32 + limited * 8 - negative * 120
    latest_text = " ".join(clean_text(item.get("vote")) + " " + clean_text(item.get("note")) for item in feedback.get("latest", []))
    if limited and has_any(latest_text, ["外摆", "露台", "户外"]) and route_type == "rainy_day":
        delta -= 35
    if limited and has_any(latest_text, ["小型犬"]) and has_any(poi_search_text(poi), ["中型犬", "大型犬"]):
        delta -= 18
    return delta


def keyword_is_negated(message: str, keywords: List[str]) -> bool:
    for keyword in keywords:
        patterns = [
            rf"不想.{{0,8}}{keyword}",
            rf"不要.{{0,8}}{keyword}",
            rf"不去.{{0,8}}{keyword}",
            rf"别.{{0,8}}{keyword}",
            rf"不考虑.{{0,8}}{keyword}",
            rf"不需要.{{0,8}}{keyword}",
            rf"不.{{0,4}}{keyword}",
        ]
        if any(re.search(pattern, message) for pattern in patterns):
            return True
    return False


def keyword_is_requested(message: str, keywords: List[str]) -> bool:
    return any(keyword in message for keyword in keywords) and not keyword_is_negated(message, keywords)


def parse_budget(message: str, default: int = 100) -> int:
    patterns = [
        r"预算\s*(?:只有|大概|约|在)?\s*(\d+)",
        r"(\d+)\s*(?:元|块|rmb|RMB)\s*(?:以内|以下|左右)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return default


def parse_available_time(message: str, default: str = "2.5小时") -> str:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(小时|h|H)", message)
    if match:
        return f"{match.group(1)}小时"
    return default


def parse_location(message: str, default: str = "南京新街口") -> str:
    known_locations = ["南京新街口", "新街口", "德基", "玄武湖", "夫子庙", "老门东", "鼓楼区", "秦淮区", "玄武区"]
    for location in known_locations:
        if location in message:
            return "南京新街口" if location == "新街口" else location
    return default


LOCATION_POINTS: Dict[str, Dict[str, Any]] = {
    "南京新街口": {"name": "南京新街口", "lat": 32.0415, "lng": 118.7841},
    "德基": {"name": "德基广场", "lat": 32.0445, "lng": 118.7855},
    "玄武湖": {"name": "玄武湖", "lat": 32.0712, "lng": 118.7994},
    "夫子庙": {"name": "夫子庙", "lat": 32.0205, "lng": 118.7882},
    "老门东": {"name": "老门东", "lat": 32.0138, "lng": 118.7937},
    "鼓楼区": {"name": "鼓楼区", "lat": 32.0664, "lng": 118.7697},
    "秦淮区": {"name": "秦淮区", "lat": 32.0187, "lng": 118.7947},
    "玄武区": {"name": "玄武区", "lat": 32.0504, "lng": 118.8489},
}

AREA_PROFILES: Dict[str, Dict[str, Any]] = {
    "xinjiekou": {
        "label": "新街口",
        "location": "南京新街口",
        "district": "秦淮区/鼓楼区交界",
        "center": {"lat": 32.0415, "lng": 118.7841},
        "radius": 3000,
        "positioning": "核心商圈短时带宠消费",
    },
    "gulou": {
        "label": "鼓楼区",
        "location": "鼓楼区",
        "district": "鼓楼区",
        "center": {"lat": 32.0664, "lng": 118.7697},
        "radius": 6500,
        "positioning": "高校/公园/社区型低压力路线",
    },
    "qinhuai": {
        "label": "秦淮区",
        "location": "秦淮区",
        "district": "秦淮区",
        "center": {"lat": 32.0187, "lng": 118.7947},
        "radius": 6500,
        "positioning": "夫子庙/老门东文旅消费路线",
    },
    "xuanwu": {
        "label": "玄武区",
        "location": "玄武区",
        "district": "玄武区",
        "center": {"lat": 32.0504, "lng": 118.8489},
        "radius": 7000,
        "positioning": "玄武湖/紫金山周边活动路线",
    },
}

LIVE_QUERY_GROUPS: Dict[str, List[str]] = {
    "activity_spaces": ["公园", "绿地", "广场", "步行街"],
    "consumption_points": ["咖啡", "宠物友好咖啡", "餐饮", "轻食"],
    "pet_services": ["宠物店", "宠物洗护", "宠物用品", "宠物医院"],
    "rainy_day_backups": ["商场", "购物中心", "商业街", "宠物用品"],
}

LIVE_POI_CACHE: Dict[str, Dict[str, Any]] = {}


def route_origin_from_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    location = clean_text(intent.get("location"), "南京新街口")
    point = LOCATION_POINTS.get(location) or LOCATION_POINTS["南京新街口"]
    return {
        "name": point["name"],
        "lat": point["lat"],
        "lng": point["lng"],
        "role": "集合点",
        "source": "parsed_user_location" if location in LOCATION_POINTS else "fallback_demo_origin",
    }


def route_endpoint_from_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    origin = route_origin_from_intent(intent)
    return {
        "name": f"{origin['name']}返程点",
        "lat": origin["lat"],
        "lng": origin["lng"],
        "role": "返程点",
        "source": origin["source"],
        "guide_note": "按旅游攻略式闭环表达，路线结束后回到起点附近，方便打车、步行返程或继续自由活动。",
    }


def area_profile(area_id: str) -> Dict[str, Any]:
    profile = dict(AREA_PROFILES.get(area_id, AREA_PROFILES["xinjiekou"]))
    profile["area_id"] = area_id if area_id in AREA_PROFILES else "xinjiekou"
    return profile


def area_for_request(request: PlanRouteRequest, intent: Dict[str, Any]) -> Dict[str, Any]:
    if request.area_id and request.area_id in AREA_PROFILES:
        return area_profile(request.area_id)
    location = clean_text(intent.get("location"), "南京新街口")
    for area_id, area in AREA_PROFILES.items():
        if location == area["location"] or location == area["label"]:
            return area_profile(area_id)
    if location == "玄武湖":
        return area_profile("xuanwu")
    if location in {"夫子庙", "老门东"}:
        return area_profile("qinhuai")
    if location == "德基":
        return area_profile("xinjiekou")
    return area_profile("xinjiekou")


def area_location_name(area: Dict[str, Any]) -> str:
    return clean_text(area.get("location"), "南京新街口")


def parse_intent(message: str, base: Dict[str, Any]) -> Dict[str, Any]:
    budget = parse_budget(message, int(base.get("budget", 100)))
    preferences: List[str] = []
    avoid: List[str] = []
    commercial_intent: List[str] = []

    if any(word in message for word in ["散步", "走走", "遛", "短逛"]):
        preferences.append("短时散步")
    if any(word in message for word in ["公园", "绿地", "草坪", "广场"]):
        preferences.append("公园/绿地活动")
    if any(word in message for word in ["只想去公园", "只去公园", "只想公园", "只想逛公园", "公园散步"]):
        preferences.append("短时散步")
        preferences.append("免费/低预算")
        avoid.append("消费点")
    if keyword_is_negated(message, ["咖啡", "咖啡店"]):
        avoid.append("咖啡店")
    if keyword_is_negated(message, ["消费", "花钱", "买东西", "吃饭", "餐饮"]):
        preferences.append("免费/低预算")
        avoid.append("消费点")
    if keyword_is_requested(message, ["咖啡", "咖啡店", "坐一会", "坐会"]):
        preferences.append("宠物友好咖啡")
        commercial_intent.append("咖啡")
    if any(word in message for word in ["轻食", "简餐"]):
        commercial_intent.append("轻食")
    if any(word in message for word in ["餐饮", "吃饭", "饭", "餐"]):
        commercial_intent.append("餐饮")
    if any(word in message for word in ["洗护", "洗澡", "美容", "护理"]):
        commercial_intent.append("洗护预约")
    if any(word in message for word in ["用品", "补给", "零食", "水碗"]):
        commercial_intent.append("用品补给")
    if any(word in message for word in ["雨", "下雨", "室内", "半室内"]):
        preferences.append("雨天备选")
    if any(word in message for word in ["太挤", "不想去太挤", "低拥挤", "安静", "避峰"]):
        preferences.append("低拥挤度")
        avoid.append("太拥挤")
    if any(word in message for word in ["太远", "近一点", "别太远", "少走路"]):
        avoid.append("太远")
    if any(word in message for word in ["免费", "不花钱", "零预算", "只散步", "纯散步", "不消费", "不想消费", "不用消费", "只走走"]):
        preferences.append("免费/低预算")
        avoid.append("消费点")
    if budget <= 30:
        preferences.append("免费/低预算")
        avoid.append("消费点")
    if budget <= 60:
        avoid.append("高消费服务点")

    pet_type = "猫" if "猫" in message else "狗"
    if "大型" in message:
        pet_size = "大型犬"
    elif "小型" in message:
        pet_size = "小型犬"
    elif "猫" in message:
        pet_size = "猫"
    else:
        pet_size = "中型犬"

    return {
        "location": parse_location(message, clean_text(base.get("location"), "南京新街口")),
        "available_time": parse_available_time(message, clean_text(base.get("available_time"), "2.5小时")),
        "pet_type": pet_type,
        "pet_size": pet_size,
        "budget": budget,
        "preferences": unique(preferences),
        "avoid": unique(avoid),
        "commercial_intent": unique(commercial_intent),
    }


def select_route_type(intent: Dict[str, Any], force_route_type: Optional[str] = None) -> str:
    if force_route_type in SUPPORTED_ROUTE_TYPES:
        return force_route_type

    preferences = " ".join(intent.get("preferences", []))
    avoid = " ".join(intent.get("avoid", []))
    budget = int(intent.get("budget", 100))
    hours = parse_available_hours(intent.get("available_time"))

    if "雨天" in preferences:
        return "rainy_day"
    if hours <= 1.5:
        return "quick_walk"
    if wants_activity_without_commerce(intent) or "消费点" in avoid or budget <= 30:
        return "quick_walk"
    if budget <= 60:
        return "budget_saver"
    if "太拥挤" in avoid or "低拥挤度" in preferences:
        return "low_stress"
    if intent_contains(intent, ["洗护", "用品", "补给", "宠物服务"]):
        return "service_supply"
    return "balanced"


def get_route(data: Dict[str, Any], route_type: str) -> Dict[str, Any]:
    base_route_type = BASE_ROUTE_TYPE.get(route_type, route_type)
    routes = data.get("route_templates", [])
    for route in routes:
        if route.get("route_type") == base_route_type:
            return route

    for route in routes:
        if route.get("route_type") == "main":
            return route

    raise HTTPException(status_code=500, detail="No usable route template found.")


def all_pois(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pois = data.get("pois", {})
    output: List[Dict[str, Any]] = []
    if not isinstance(pois, dict):
        return output
    for group in pois.values():
        if isinstance(group, list):
            output.extend(item for item in group if isinstance(item, dict))
    return output


def baidu_place_search(keyword: str, area: Dict[str, Any], page_size: int = 10) -> List[Dict[str, Any]]:
    ak = os.getenv("BAIDU_MAP_AK")
    if not ak:
        return []
    cache_key = f"{area.get('area_id', area.get('label', 'xinjiekou'))}:{keyword}:{page_size}"
    cached = LIVE_POI_CACHE.get(cache_key)
    now = time.time()
    if cached and now - float(cached.get("created_at", 0)) < 900:
        return cached.get("results", [])

    center = area.get("center", AREA_PROFILES["xinjiekou"]["center"])
    params = {
        "query": keyword,
        "location": f"{center['lat']},{center['lng']}",
        "radius": int(area.get("radius", 5000)),
        "region": "南京",
        "city_limit": "true",
        "output": "json",
        "scope": 2,
        "page_size": page_size,
        "ak": ak,
    }
    try:
        response = requests.get("https://api.map.baidu.com/place/v2/search", params=params, timeout=5)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 0:
            return []
        results = payload.get("results", [])
        output = results if isinstance(results, list) else []
        LIVE_POI_CACHE[cache_key] = {"created_at": now, "results": output}
        return output
    except Exception:
        return []


def live_result_to_poi(result: Dict[str, Any], group_name: str, keyword: str, index: int, area: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    location = result.get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    detail = result.get("detail_info") or {}
    name = clean_text(result.get("name"))
    category = clean_text(detail.get("tag") or result.get("tag") or result.get("type"))
    address = clean_text(result.get("address"))
    text_value = " ".join([name, category, keyword, address])

    status = "待确认"
    confidence = "低"
    if has_any(text_value, ["宠物", "宠物店", "宠物洗护", "宠物用品", "宠物医院"]):
        status = "宠物服务相关"
        confidence = "高"
    elif has_any(text_value, ["外摆", "露台", "户外", "宠物友好", "可带狗"]):
        status = "可能宠物友好"
        confidence = "中"

    space_type = "开放空间" if group_name == "activity_spaces" else ("室内/半室内" if group_name == "rainy_day_backups" else "商业消费空间")
    stress = "低" if group_name == "pet_services" else ("中" if group_name != "rainy_day_backups" else "高")
    crowd = "中" if area.get("label") != "新街口" else "高"
    cost = "0-20元" if group_name == "activity_spaces" else ("60-150元" if group_name == "pet_services" else "30-100元")

    risk_notes = ["携宠规则需以商户/现场为准"]
    if group_name == "rainy_day_backups":
        risk_notes.append("室内或商场区域是否允许携宠需确认")
    if group_name == "consumption_points":
        risk_notes.append("建议确认外摆/户外座位是否开放")
    if crowd == "高":
        risk_notes.append("高峰期人流较大，建议全程牵引")

    return {
        "poi_id": f"live_{group_name}_{index:03d}",
        "name": name,
        "category": category,
        "address": address,
        "distance_m": detail.get("distance"),
        "location": {"lat": lat, "lng": lng},
        "pet_friendly": {
            "status": status,
            "confidence_level": confidence,
            "evidence_source": "百度地图 Place API 实时检索 + FluffyGo 轻量规则",
            "evidence_text": f"来自 {area.get('label')} / {keyword} 实时检索结果，需用户反馈或商户规则补强",
            "suitable_pet_size": "小型犬/中型犬",
        },
        "experience": {
            "space_type": space_type,
            "crowd_level": crowd,
            "pet_stress_level": stress,
            "tags": unique([category, keyword, area.get("label", ""), status, cost]),
        },
        "business": {
            "transaction_action": "预约洗护/电话咨询" if group_name == "pet_services" else ("查看备选详情" if group_name == "rainy_day_backups" else "查看门店详情/到店咨询"),
            "estimated_cost": cost,
        },
        "risk_note": "；".join(risk_notes),
        "manual_review_required": True,
        "demo_selected_reason": f"{area.get('label')} 实时 POI：{keyword}",
        "source_area": area.get("label"),
        "source_keyword": keyword,
        "source_api": "baidu_place_v2",
    }


def build_live_pois(area: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {group: [] for group in LIVE_QUERY_GROUPS}
    for group_name, keywords in LIVE_QUERY_GROUPS.items():
        scoped_keywords = keywords[:]
        if intent_contains(intent, ["咖啡"]):
            scoped_keywords = ["咖啡", "宠物友好咖啡", "外摆咖啡"] if group_name == "consumption_points" else scoped_keywords
        if intent_contains(intent, ["洗护", "用品", "补给"]):
            scoped_keywords = ["宠物洗护", "宠物用品", "宠物店"] if group_name == "pet_services" else scoped_keywords
        index = 1
        seen_names = set()
        for keyword in scoped_keywords[:2]:
            for result in baidu_place_search(keyword, area, page_size=5):
                name = clean_text(result.get("name"))
                if not name or name in seen_names:
                    continue
                poi = live_result_to_poi(result, group_name, keyword, index, area)
                if not poi:
                    continue
                seen_names.add(name)
                grouped[group_name].append(poi)
                index += 1
                if len(grouped[group_name]) >= 8:
                    break
            if len(grouped[group_name]) >= 8:
                break
    return grouped


def merge_live_data(data: Dict[str, Any], live_pois: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    if not any(live_pois.values()):
        return data
    merged = json.loads(json.dumps(data, ensure_ascii=False))
    pois = merged.setdefault("pois", {})
    for group_name, items in live_pois.items():
        if items:
            pois[group_name] = items + pois.get(group_name, [])
    return merged


def find_poi(data: Dict[str, Any], poi_id: str) -> Optional[Dict[str, Any]]:
    return next((poi for poi in all_pois(data) if poi.get("poi_id") == poi_id), None)


def confidence_score(value: str) -> int:
    return {"高": 3, "中": 2, "低": 1}.get(value, 0)


def stress_score(value: str) -> int:
    return {"低": 3, "中": 2, "高": 1}.get(value, 0)


def crowd_score(value: str) -> int:
    return {"低": 3, "中": 2, "高": 1}.get(value, 0)


def parse_available_hours(value: Any, default: float = 2.5) -> float:
    text_value = clean_text(value)
    match = re.search(r"(\d+(?:\.\d+)?)", text_value)
    if not match:
        return default
    try:
        return float(match.group(1))
    except ValueError:
        return default


def cost_bounds(value: Any) -> tuple:
    text = clean_text(value)
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return 0, 999


def poi_cost_bounds(poi: Dict[str, Any]) -> tuple:
    business = poi.get("business", {})
    return cost_bounds(business.get("estimated_cost") or business.get("cost_tier") or "")


def route_cost_bounds(stops: List[Dict[str, Any]]) -> tuple:
    mins: List[int] = []
    maxes: List[int] = []
    for stop in stops:
        role = clean_text(stop.get("role"))
        if role in {"短时活动空间", "雨天备选点"}:
            mins.append(0)
            maxes.append(0)
            continue
        low, high = poi_cost_bounds(stop.get("poi", {}))
        mins.append(low)
        maxes.append(high)
    if not mins:
        return 0, 0
    return sum(mins), sum(maxes)


def route_budget_label(stops: List[Dict[str, Any]], fallback: str) -> str:
    low, high = route_cost_bounds(stops)
    if high <= 0:
        return "0元"
    if low == high:
        return f"{low}元"
    return f"{low}-{high}元"


def has_any(text_value: str, keywords: List[str]) -> bool:
    return any(keyword.lower() in text_value.lower() for keyword in keywords)


def poi_search_text(poi: Dict[str, Any]) -> str:
    exp = poi.get("experience", {})
    pet = poi.get("pet_friendly", {})
    parts = [
        poi.get("name"),
        poi.get("category"),
        poi.get("address"),
        exp.get("space_type"),
        exp.get("crowd_level"),
        exp.get("pet_stress_level"),
        pet.get("status"),
        pet.get("confidence_level"),
        pet.get("evidence_text"),
        poi.get("risk_note"),
    ]
    tags = exp.get("tags", [])
    if isinstance(tags, list):
        parts.extend(tags)
    return " ".join(clean_text(part) for part in parts if part is not None)


def poi_primary_text(poi: Dict[str, Any]) -> str:
    return " ".join([clean_text(poi.get("name")), clean_text(poi.get("category"))])


def evidence_level_score(level: str) -> int:
    return {
        "官方确认": 96,
        "近期用户验证": 88,
        "强证据": 76,
        "场景证据": 66,
        "场景适配": 58,
        "待补充": 42,
    }.get(level, 40)


def make_evidence_item(
    evidence_id: str,
    source_type: str,
    source_name: str,
    signal: str,
    strength: str,
    weight: int,
    freshness: str,
    review_status: str,
) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "source_name": source_name,
        "signal": signal,
        "strength": strength,
        "weight": weight,
        "freshness": freshness,
        "review_status": review_status,
    }


def base_evidence_items_for_poi(poi: Dict[str, Any]) -> List[Dict[str, Any]]:
    text_value = poi_search_text(poi)
    primary_text = poi_primary_text(poi)
    exp = poi.get("experience", {})
    pet = poi.get("pet_friendly", {})
    space_type = clean_text(exp.get("space_type"))
    status = clean_text(pet.get("status"), "待确认")
    items: List[Dict[str, Any]] = []

    if has_any(primary_text, ["宠物", "宠物服务", "宠物店", "洗护", "宠物用品", "宠物医院"]):
        items.append(make_evidence_item(
            "poi_category_pet_service",
            "poi_category",
            "百度地图 POI 类目/商户名称",
            "名称或类目命中宠物服务，适合作为服务/补给节点。",
            "strong",
            76,
            "static_poi",
            "candidate_pool",
        ))
    if status == "可能宠物友好" or has_any(text_value, ["外摆", "露台", "户外", "宠物友好", "可带狗"]):
        items.append(make_evidence_item(
            "keyword_open_air_pet_signal",
            "keyword_rule",
            "外摆/露台/户外关键词",
            "命中开放消费场景线索，可进入宠物友好候选池。",
            "medium",
            66,
            "static_poi",
            "review_recommended",
        ))
    if has_any(primary_text + " " + space_type, ["公园", "绿地", "广场", "商业街", "步行街", "街区", "开放空间"]):
        items.append(make_evidence_item(
            "open_space_context",
            "space_context",
            "开放空间/街区场景",
            "开放空间更适合作为牵引散步和短暂停留节点。",
            "medium",
            58,
            "static_poi",
            "candidate_pool",
        ))
    if has_any(primary_text + " " + space_type, ["商场", "购物中心", "商业综合体", "室内"]):
        items.append(make_evidence_item(
            "indoor_access_uncertainty",
            "risk_rule",
            "室内/商场空间判断",
            "室内准入规则敏感，当前只适合作为备选或待核验候选。",
            "weak",
            42,
            "static_poi",
            "manual_review_required",
        ))

    if not items:
        items.append(make_evidence_item(
            "generic_poi_candidate",
            "poi_category",
            "百度地图 POI 基础信息",
            "仅有基础 POI 信息，尚未形成明确携宠证据。",
            "weak",
            40,
            "static_poi",
            "manual_review_required",
        ))
    return items


def evidence_gaps_for_policy(policy: Dict[str, Any]) -> List[str]:
    layer = clean_text(policy.get("layer"), "L6")
    gaps = list(policy.get("missing_sources", []))
    if layer != "L1" and "商户后台携宠规则" not in gaps:
        gaps.append("商户后台携宠规则")
    if layer not in {"L1", "L2"} and "近期用户到店验证" not in gaps:
        gaps.append("近期用户到店验证")
    if layer in {"L5", "L6"} and "人工/运营复核" not in gaps:
        gaps.append("人工/运营复核")
    return unique(gaps)


def review_status_for_policy(policy: Dict[str, Any]) -> str:
    layer = clean_text(policy.get("layer"), "L6")
    if layer == "L1":
        return "verified"
    if layer in {"L2", "L3", "L4"}:
        return "review_recommended"
    if layer == "L5":
        return "candidate_pool"
    return "manual_review_required"


def trust_explanation_for_policy(policy: Dict[str, Any]) -> str:
    layer = clean_text(policy.get("layer"), "L6")
    return {
        "L1": "商户已确认携宠规则，可作为最高优先级推荐。",
        "L2": "近期用户反馈支持该判断，但仍建议持续观察负反馈。",
        "L3": "宠物服务类目是强场景证据，但不等同于普通消费空间可携宠。",
        "L4": "外摆/户外线索适合进入候选池，需商户或用户反馈补强。",
        "L5": "开放空间适合散步停留，但不是商户携宠承诺。",
        "L6": "证据不足或室内规则敏感，应降级为备选或人工复核。",
    }.get(layer, "当前证据不足，需要补充商户、用户或运营复核信息。")


def assess_pet_policy(poi: Dict[str, Any]) -> Dict[str, Any]:
    text_value = poi_search_text(poi)
    primary_text = poi_primary_text(poi)
    exp = poi.get("experience", {})
    pet = poi.get("pet_friendly", {})
    space_type = clean_text(exp.get("space_type"))
    status = clean_text(pet.get("status"), "待确认")

    def finalize(policy: Dict[str, Any]) -> Dict[str, Any]:
        policy["evidence_items"] = base_evidence_items_for_poi(poi)
        policy["evidence_gaps"] = evidence_gaps_for_policy(policy)
        policy["review_status"] = review_status_for_policy(policy)
        policy["trust_explanation"] = trust_explanation_for_policy(policy)
        return policy

    if has_any(primary_text, ["宠物", "宠物服务", "宠物店", "洗护", "宠物用品", "宠物医院"]):
        return finalize({
            "layer": "L3",
            "label": "宠物服务门店",
            "evidence_level": "强证据",
            "score": evidence_level_score("强证据"),
            "basis": "商户名称或百度地图类目直接命中宠物服务，适合承接洗护、用品、咨询等明确交易动作。",
            "review_hint": "核验营业时间、服务项目和是否接待当前犬型。",
            "recommended_action": "可进入服务/补给路线，并连接美团预约或咨询动作。",
            "data_sources": ["百度地图 POI 类目", "商户名称关键词"],
            "missing_sources": ["商户后台携宠规则", "近期用户到店验证"],
        })

    if status == "可能宠物友好" or has_any(text_value, ["外摆", "露台", "户外", "宠物友好", "可带狗"]):
        return finalize({
            "layer": "L4",
            "label": "外摆/户外线索",
            "evidence_level": "场景证据",
            "score": evidence_level_score("场景证据"),
            "basis": "POI 名称、关键词或标签命中外摆、露台、户外等开放消费场景，适合进入候选池。",
            "review_hint": "建议接入商户侧携宠标签或用户到店反馈后提升为已核验。",
            "recommended_action": "可作为消费候选点，推荐前优先展示外摆/户外场景依据。",
            "data_sources": ["百度地图 POI", "外摆/露台/户外关键词"],
            "missing_sources": ["商户确认", "近期用户验证"],
        })

    if has_any(primary_text + " " + space_type, ["公园", "绿地", "广场", "商业街", "步行街", "街区", "开放空间"]):
        return finalize({
            "layer": "L5",
            "label": "开放空间适配",
            "evidence_level": "场景适配",
            "score": evidence_level_score("场景适配"),
            "basis": "点位属于公园、绿地、广场或街区类开放空间，更适合作为牵引散步和短暂停留节点。",
            "review_hint": "后续可接入城市管理规则、用户反馈和现场标识完善禁入边界。",
            "recommended_action": "适合作为散步或低消费路线节点，不直接承诺店内可携宠。",
            "data_sources": ["百度地图 POI 类目", "开放空间关键词"],
            "missing_sources": ["城市管理规则", "现场标识/用户反馈"],
        })

    if has_any(primary_text + " " + space_type, ["商场", "购物中心", "商业综合体", "室内"]):
        return finalize({
            "layer": "L6",
            "label": "室内场景待核验",
            "evidence_level": "待补充",
            "score": evidence_level_score("待补充"),
            "basis": "室内或商场类点位对携宠规则更敏感，当前只作为雨天/备选候选，不直接声明可带宠。",
            "review_hint": "需要商户后台标签、电话确认或用户反馈后再推荐为可带宠点。",
            "recommended_action": "仅作雨天备选或低优先级候选，等待更强证据再升级。",
            "data_sources": ["百度地图 POI 类目", "室内/商场空间判断"],
            "missing_sources": ["商户后台携宠规则", "用户到店反馈"],
        })

    return finalize({
        "layer": "L6",
        "label": "场景待核验",
        "evidence_level": "待补充",
        "score": evidence_level_score("待补充"),
        "basis": "当前基于 POI 类目、关键词和空间类型做初筛，尚未形成强携宠证据。",
        "review_hint": "需要接入商户侧标签、用户反馈或人工抽检提升判断质量。",
        "recommended_action": "保留在候选池，暂不作为高优推荐点。",
        "data_sources": ["百度地图 POI"],
        "missing_sources": ["商户确认", "用户验证", "人工核验"],
    })


def get_poi_group(data: Dict[str, Any], group_name: str) -> List[Dict[str, Any]]:
    pois = data.get("pois", {})
    if not isinstance(pois, dict):
        return []
    group = pois.get(group_name, [])
    return [poi for poi in group if isinstance(poi, dict)]


def intent_contains(intent: Dict[str, Any], keywords: List[str]) -> bool:
    text_value = " ".join(
        [
            " ".join(intent.get("preferences", [])),
            " ".join(intent.get("avoid", [])),
            " ".join(intent.get("commercial_intent", [])),
            clean_text(intent.get("pet_size")),
            clean_text(intent.get("location")),
        ]
    )
    return has_any(text_value, keywords)


def wants_activity_without_commerce(intent: Dict[str, Any]) -> bool:
    return (
        intent_contains(intent, ["公园/绿地活动", "公园", "绿地", "散步"])
        and intent_contains(intent, ["咖啡店", "消费点", "免费/低预算"])
        and not intent.get("commercial_intent")
    )


def score_poi_for_intent(
    poi: Dict[str, Any],
    group_name: str,
    intent: Dict[str, Any],
    route_type: str,
    feedback_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    text_value = poi_search_text(poi)
    primary_text = poi_primary_text(poi)
    pet = poi.get("pet_friendly", {})
    exp = poi.get("experience", {})
    distance = poi.get("distance_m")
    distance_value = int(distance) if isinstance(distance, (int, float)) else 1500
    budget = int(intent.get("budget", 100))
    cost_low, cost_high = poi_cost_bounds(poi)
    policy = assess_pet_policy(poi)

    score = 0
    score += confidence_score(clean_text(pet.get("confidence_level"), "低")) * 9
    score += int(policy.get("score", 40)) // 8
    score += feedback_ranking_delta(poi, route_type, feedback_stats)
    score += stress_score(clean_text(exp.get("pet_stress_level"), "中")) * 8
    score += crowd_score(clean_text(exp.get("crowd_level"), "中")) * 5
    score += max(0, 14 - int(distance_value / 150))

    if clean_text(poi.get("source_api")) == "baidu_place_v2":
        score += 18
    location_text = clean_text(intent.get("location"))
    if location_text and has_any(clean_text(poi.get("source_area")) + " " + text_value, [location_text.replace("南京", "")]):
        score += 12

    if group_name == "activity_spaces":
        if has_any(primary_text, ["湖心亭", "码头", "母婴室", "书画馆", "美术馆", "馆", "亭"]):
            score -= 55
        if has_any(primary_text, ["公园", "绿地", "广场"]) and not has_any(primary_text, ["-", "码头", "馆", "亭"]):
            score += 24

    if route_type == "rainy_day":
        if group_name == "rainy_day_backups":
            score += 30
        if has_any(text_value, ["商场", "购物中心", "室内", "半室内"]):
            score += 18
    if route_type == "low_stress":
        if clean_text(exp.get("crowd_level")) == "高":
            score -= 16
        if clean_text(exp.get("pet_stress_level")) == "低":
            score += 18
        if distance_value <= 800:
            score += 8

    if intent_contains(intent, ["咖啡"]):
        score += 42 if has_any(primary_text, ["咖啡"]) else 0
        score += 18 if has_any(primary_text, ["茶", "饮品"]) else 0
        score += 8 if has_any(text_value, ["咖啡", "茶", "饮品"]) else 0
    if intent_contains(intent, ["餐饮", "轻食", "吃饭"]):
        score += 38 if has_any(primary_text, ["餐厅", "菜馆", "料理", "轻食"]) else 0
        score += 10 if has_any(primary_text, ["美食"]) else 0
        if has_any(primary_text, ["咖啡", "茶", "饮品"]) and not intent_contains(intent, ["咖啡"]):
            score -= 18
    if intent_contains(intent, ["洗护", "洗澡", "美容", "护理"]):
        score += 32 if has_any(primary_text, ["洗护", "自助浴", "宠物服务", "美容"]) else 0
    if intent_contains(intent, ["用品", "补给", "零食"]):
        score += 32 if has_any(primary_text, ["用品", "补给", "公司", "宠物服务"]) else 0
    if intent_contains(intent, ["散步", "短时散步"]):
        score += 12 if group_name == "activity_spaces" else 0

    if budget <= 60:
        if group_name == "pet_services":
            score -= 65
        if distance_value > 1000:
            score -= 8
        if group_name == "consumption_points":
            if cost_high <= budget:
                score += 36
            elif cost_low <= budget:
                score += 8
            if cost_high > budget:
                score -= min(55, 20 + int((cost_high - budget) / 2))
            if route_type == "budget_saver" and cost_high <= budget:
                score += 18
    elif budget >= 100:
        if group_name == "pet_services":
            score += 12

    if budget <= 30:
        if group_name != "activity_spaces":
            score -= 90
    elif cost_low > budget:
        score -= min(80, int((cost_low - budget) / 2))

    if intent_contains(intent, ["太远"]):
        score -= 14 if distance_value > 1000 else 0

    if intent.get("pet_size") in {"中型犬", "大型犬"}:
        if has_any(text_value, ["商场", "购物中心", "室内"]):
            score -= 8
        if has_any(text_value, ["商业街", "道路", "开放空间", "街区"]):
            score += 8

    return score


def select_best_poi(
    data: Dict[str, Any],
    group_name: str,
    intent: Dict[str, Any],
    route_type: str,
    used_ids: set,
    feedback_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    slot_index: int = 1,
) -> Optional[Dict[str, Any]]:
    candidates = [poi for poi in get_poi_group(data, group_name) if poi.get("poi_id") not in used_ids]
    if not candidates:
        return None
    budget = int(intent.get("budget", 100))
    if group_name == "consumption_points" and budget <= 60:
        affordable = [poi for poi in candidates if poi_cost_bounds(poi)[1] <= budget]
        if affordable:
            candidates = affordable
    if group_name == "pet_services" and budget <= 60:
        affordable = [poi for poi in candidates if poi_cost_bounds(poi)[0] <= budget]
        if affordable:
            candidates = affordable
    ranked = sorted(
        [
            {
                "poi": poi,
                "score": score_poi_for_intent(poi, group_name, intent, route_type, feedback_stats),
            }
            for poi in candidates
        ],
        key=lambda item: item["score"],
        reverse=True,
    )
    if not ranked:
        return None

    top_score = ranked[0]["score"]
    near_top = [item for item in ranked if item["score"] >= top_score - 12][:5]
    seed_text = json.dumps(
        {
            "location": intent.get("location"),
            "budget": intent.get("budget"),
            "preferences": intent.get("preferences", []),
            "avoid": intent.get("avoid", []),
            "commercial_intent": intent.get("commercial_intent", []),
            "route_type": route_type,
            "group_name": group_name,
            "slot_index": slot_index,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    choice = near_top[seed % len(near_top)]
    poi = dict(choice["poi"])
    poi["_selection_meta"] = {
        "candidate_count": len(ranked),
        "near_top_count": len(near_top),
        "ranked_position": ranked.index(choice) + 1,
        "score": choice["score"],
        "selection_mode": "dynamic_ranked_pool",
    }
    return poi


def suggested_stay_time(role: str, route_type: str) -> str:
    if role == "短时活动空间":
        return "20-35分钟" if route_type == "low_stress" else "30-45分钟"
    if role == "宠物友好消费点":
        return "40-60分钟"
    if role == "雨天备选点":
        return "35-50分钟"
    return "15-25分钟"


GENERIC_TRANSACTION_ACTIONS = {"", "加入路线", "出发前确认", "电话咨询/到店服务"}


def infer_pet_access_policy(poi: Dict[str, Any], role: str = "", route_type: str = "") -> Dict[str, Any]:
    text_value = poi_search_text(poi)
    primary_text = poi_primary_text(poi)
    policy = assess_pet_policy(poi)
    layer = clean_text(policy.get("layer"), "L6")
    score = int(policy.get("score", 40))

    access_type = "规则待核验"
    allowed_scope = "需到店/现场确认"
    pet_size_limit = "建议小型犬/中型犬牵引"
    time_note = "高峰期建议避开 16:00-18:00"
    commerce_readiness = "candidate"
    confirmation_question = "是否允许当前犬型进入或停留？"
    action_hint = "出发前电话确认"
    sources = list(policy.get("data_sources", []))

    if has_any(primary_text, ["宠物", "宠物店", "洗护", "宠物用品", "宠物医院"]):
        access_type = "宠物服务场所"
        allowed_scope = "服务区/门店接待，按项目预约"
        pet_size_limit = "按门店服务能力确认犬型"
        commerce_readiness = "transaction_ready"
        confirmation_question = "是否可接待当前犬型、当前时段是否可约？"
        action_hint = "预约洗护/电话咨询"
    elif has_any(text_value, ["外摆", "露台", "户外", "宠物友好", "可带狗"]):
        access_type = "条件友好消费点"
        allowed_scope = "优先外摆/户外座位，不默认进入室内"
        pet_size_limit = "中型犬需确认外摆空间"
        commerce_readiness = "confirm_then_transact"
        confirmation_question = "外摆是否开放、是否允许中型犬停留？"
        action_hint = "电话确认后查看团购/门店"
    elif has_any(primary_text + " " + clean_text(poi.get("experience", {}).get("space_type")), ["公园", "绿地", "广场", "街区", "商业街", "步行街", "开放空间"]):
        access_type = "开放空间适配"
        allowed_scope = "开放空间牵引散步，不代表店内可携宠"
        pet_size_limit = "中大型犬建议短牵引"
        commerce_readiness = "route_ready"
        confirmation_question = "是否存在禁犬区域、临时活动或人流高峰？"
        action_hint = "加入散步路线"
    elif has_any(primary_text, ["商场", "购物中心", "商业综合体", "室内"]):
        access_type = "雨天备选待核验"
        allowed_scope = "仅作为避雨/集合备选，不默认允许携宠进入"
        pet_size_limit = "通常需确认犬型和入场方式"
        commerce_readiness = "backup_only"
        confirmation_question = "室内区域是否允许携宠，是否仅限宠物推车/小型犬？"
        action_hint = "查看规则/电话确认"

    if layer in {"L1", "L2"}:
        verification_status = "已验证"
        confidence_percent = max(82, min(96, score + 8))
    elif layer in {"L3", "L4"}:
        verification_status = "强候选"
        confidence_percent = max(62, min(82, score))
    elif layer == "L5":
        verification_status = "场景适配"
        confidence_percent = max(52, min(72, score))
    else:
        verification_status = "待核验"
        confidence_percent = max(35, min(58, score))

    if clean_text(poi.get("source_api")) == "baidu_place_v2":
        sources.append("百度地图实时 POI")

    return {
        "access_type": access_type,
        "allowed_scope": allowed_scope,
        "pet_size_limit": pet_size_limit,
        "time_note": time_note,
        "verification_status": verification_status,
        "confidence_percent": confidence_percent,
        "commerce_readiness": commerce_readiness,
        "confirmation_question": confirmation_question,
        "action_hint": action_hint,
        "evidence_sources": unique(sources),
        "policy_layer": layer,
        "policy_score": score,
    }


def contextualize_poi_for_route(poi: Dict[str, Any], role: str, route_type: str) -> Dict[str, Any]:
    poi_copy = json.loads(json.dumps(poi, ensure_ascii=False))
    business = poi_copy.setdefault("business", {})
    action = clean_text(business.get("transaction_action"))

    if role == "宠物服务/补给点" and action in GENERIC_TRANSACTION_ACTIONS:
        business["transaction_action"] = "预约洗护/电话咨询"
    elif role == "短时活动空间" and action in GENERIC_TRANSACTION_ACTIONS:
        business["transaction_action"] = "加入散步路线"
    elif role == "雨天备选点" and action in GENERIC_TRANSACTION_ACTIONS:
        business["transaction_action"] = "查看备选详情"
    elif role == "宠物友好消费点" and action in GENERIC_TRANSACTION_ACTIONS:
        business["transaction_action"] = "查看门店详情/到店咨询"

    poi_copy["pet_access_policy"] = infer_pet_access_policy(poi_copy, role, route_type)
    return poi_copy


def build_selection_reason(
    poi: Dict[str, Any],
    role: str,
    intent: Dict[str, Any],
    route_type: str,
) -> str:
    exp = poi.get("experience", {})
    policy = assess_pet_policy(poi)
    reason_parts = [f"匹配{role}"]

    if route_type == "rainy_day":
        reason_parts.append("适合作为雨天或半室内备选")
    elif route_type == "low_stress":
        reason_parts.append("优先降低拥挤和宠物压力")

    if intent_contains(intent, ["咖啡"]) and has_any(poi_search_text(poi), ["咖啡", "茶", "饮品"]):
        reason_parts.append("符合咖啡消费意图")
    if intent_contains(intent, ["洗护", "用品", "补给"]) and role == "宠物服务/补给点":
        reason_parts.append("可承接洗护或用品补给交易")

    reason_parts.append(policy["label"])
    reason_parts.append(f"宠物压力{clean_text(exp.get('pet_stress_level'), '中')}")
    return "，".join(unique(reason_parts)) + "。"


def build_dynamic_stops(
    data: Dict[str, Any],
    route: Dict[str, Any],
    intent: Dict[str, Any],
    route_type: str,
) -> List[Dict[str, Any]]:
    budget = int(intent.get("budget", 100))
    hours = parse_available_hours(intent.get("available_time"))
    used_ids: set = set()
    feedback_stats = feedback_by_poi()
    desired_groups: List[tuple] = []
    activity_only = wants_activity_without_commerce(intent) or route_type == "quick_walk" or budget <= 30

    if route_type == "balanced":
        route_type = "main"

    if route_type == "rainy_day":
        desired_groups = [
            ("rainy_day_backups", "雨天备选点"),
        ]
        if budget > 30 and not intent_contains(intent, ["消费点"]):
            desired_groups.append(("consumption_points", "宠物友好消费点"))
        if hours >= 2 and (budget >= 150 or intent_contains(intent, ["洗护", "用品", "补给", "宠物服务"])):
            desired_groups.append(("pet_services", "宠物服务/补给点"))
    elif route_type == "budget_saver":
        desired_groups = [("activity_spaces", "短时活动空间")]
        if budget > 30:
            desired_groups.append(("consumption_points", "宠物友好消费点"))
    elif route_type == "service_supply":
        desired_groups = [
            ("activity_spaces", "短时活动空间"),
            ("pet_services", "宠物服务/补给点"),
        ]
        if budget >= 100 and hours >= 2:
            desired_groups.append(("consumption_points", "宠物友好消费点"))
    else:
        if activity_only:
            desired_groups = [
                ("activity_spaces", "短时活动空间"),
                ("activity_spaces", "短时活动空间"),
            ]
        else:
            desired_groups = [
                ("activity_spaces", "短时活动空间"),
            ]
            if budget > 30:
                desired_groups.append(("consumption_points", "宠物友好消费点"))
        service_intent = intent_contains(intent, ["洗护", "用品", "补给", "宠物服务"])
        needs_service = hours >= 2 and not activity_only and (
            (budget >= 150 or service_intent) and (route_type != "low_stress" or service_intent)
        )
        if needs_service:
            desired_groups.append(("pet_services", "宠物服务/补给点"))

    if hours <= 1.5:
        desired_groups = desired_groups[:2]

    stops: List[Dict[str, Any]] = []
    for index, (group_name, role) in enumerate(desired_groups, start=1):
        poi = select_best_poi(data, group_name, intent, route_type, used_ids, feedback_stats, index)
        if not poi:
            continue
        selection_meta = poi.get("_selection_meta", {})
        used_ids.add(clean_text(poi.get("poi_id")))
        poi = contextualize_poi_for_route(poi, role, route_type)
        reason = build_selection_reason(poi, role, intent, route_type)
        if route_type == "rainy_day":
            reason = f"{reason.rstrip('。')}，雨天场景下仅作为备选点，室内/商场规则不默认承诺。"
        stops.append(
            {
                "order": index,
                "poi_id": poi.get("poi_id"),
                "role": role,
                "suggested_stay_time": suggested_stay_time(role, route_type),
                "reason": reason,
                "poi": poi,
                "ui_highlights": build_stop_highlights(poi),
                "pet_policy_assessment": assess_pet_policy(poi),
                "pet_access_policy": poi.get("pet_access_policy") or infer_pet_access_policy(poi, role, route_type),
                "selection_score": selection_meta.get("score") or score_poi_for_intent(poi, group_name, intent, route_type, feedback_stats),
                "selection_meta": selection_meta,
            }
        )

    if not stops:
        # Fallback to the curated template if future data is incomplete.
        for stop in route.get("stops", []):
            poi = find_poi(data, stop.get("poi_id", ""))
            if poi:
                stops.append({
                    **stop,
                    "poi": poi,
                    "ui_highlights": build_stop_highlights(poi),
                    "pet_policy_assessment": assess_pet_policy(poi),
                    "pet_access_policy": infer_pet_access_policy(poi, clean_text(stop.get("role")), route_type),
                })
    return stops


def enhance_route_with_business_logic(
    data: Dict[str, Any],
    route: Dict[str, Any],
    intent: Dict[str, Any],
    route_type: str,
) -> Dict[str, Any]:
    route_copy = json.loads(json.dumps(route, ensure_ascii=False))
    budget = int(intent.get("budget", 100))
    activity_only = wants_activity_without_commerce(intent)
    stops = build_dynamic_stops(data, route_copy, intent, route_type)

    route_copy["stops"] = stops
    route_copy["route_type"] = route_type

    if activity_only:
        if route_type == "low_stress":
            route_copy["route_name"] = "新街口低压力街区散步线"
            route_copy["summary"] = "适合明确不想进入咖啡店、只想带狗短时散步的低压力路线。"
        else:
            route_copy["route_name"] = "新街口公园街区散步线"
            route_copy["summary"] = "适合带大型犬在新街口周边进行短时牵引散步，不强制安排室内消费点。"
        route_copy["planner_reason"] = "识别到用户明确排除室内消费点并偏好公园散步，优先保留活动空间。"
    elif route_type == "quick_walk":
        route_copy["route_name"] = "新街口纯散步快线"
        route_copy["summary"] = "适合预算很低、时间较短或只想遛狗的用户，仅保留免费/低成本活动空间。"
        route_copy["planner_reason"] = "识别到短时或低预算约束，把预算作为硬约束，不安排消费和服务点。"
    elif route_type == "budget_saver":
        route_copy["route_name"] = "新街口省钱短逛线"
        route_copy["summary"] = "适合 30-60 元预算，保留免费活动空间和低客单消费点。"
        route_copy["planner_reason"] = "识别到预算较低，优先免费活动空间和低客单消费，移除洗护等高消费服务。"
    elif route_type == "service_supply":
        route_copy["route_name"] = "新街口宠物补给服务线"
        route_copy["summary"] = "适合需要洗护、用品补给或宠物服务咨询的出行。"
        route_copy["planner_reason"] = "识别到宠物服务/补给意图，优先安排宠物服务节点，并根据预算搭配消费点。"
    elif route_type == "balanced":
        route_copy["route_name"] = "新街口均衡短逛线"
        route_copy["summary"] = "适合 2-2.5 小时带宠出行，兼顾活动空间、消费和可选补给。"
        route_copy["planner_reason"] = "根据预算、时间和消费意图，生成活动、消费和补给均衡的路线。"
    elif route_type == "rainy_day":
        route_copy["summary"] = "适合下雨或天气不稳定时使用，优先给出可避雨停靠点；室内/商场点位只作为备选，不默认承诺可携宠。"
        route_copy["planner_reason"] = "识别到雨天/室内需求，优先选择雨天备选点，并减少露天步行。"
    elif route_type == "low_stress":
        route_copy["planner_reason"] = "识别到低拥挤/避峰需求，优先选择宠物压力较低、停留点更少的路线。"
    elif budget <= 60:
        route_copy["planner_reason"] = "识别到预算降低，保留免费街区活动空间，优先低客单消费，并移除高消费洗护节点。"
    else:
        route_copy["planner_reason"] = "根据时间、宠物体型、预算和咖啡消费意图，推荐主路线。"

    route_copy["estimated_budget"] = route_budget_label(stops, route_copy.get("estimated_budget", "60-100元"))
    route_copy["pet_friendly_score"] = calculate_pet_friendly_score(stops)
    route_copy["pet_stress_level"] = calculate_route_stress(stops)
    route_copy["risk_summary"] = build_route_risk_summary(stops, route_copy.get("risk_summary", ""))
    return route_copy


def build_stop_highlights(poi: Dict[str, Any]) -> List[str]:
    exp = poi.get("experience", {})
    policy = assess_pet_policy(poi)
    highlights = [
        f"携宠判断：{policy['label']}",
        f"证据层级：{policy['evidence_level']}",
        f"宠物压力：{clean_text(exp.get('pet_stress_level'), '中')}",
    ]
    distance = poi.get("distance_m")
    if distance is not None:
        highlights.append(f"距离约 {distance}m")
    return highlights


def calculate_pet_friendly_score(stops: List[Dict[str, Any]]) -> float:
    if not stops:
        return 3.0

    total = 0
    for stop in stops:
        policy = stop.get("pet_policy_assessment") or assess_pet_policy(stop.get("poi", {}))
        total += int(policy.get("score", 40))
    avg = total / max(len(stops), 1)
    return round(max(2.5, min(5.0, avg / 20)), 1)


def build_pet_label_summary(route: Dict[str, Any]) -> Dict[str, Any]:
    stops = route.get("stops", [])
    poi_feedback = feedback_by_poi()
    policies = []
    for stop in stops:
        poi = stop.get("poi", {})
        poi_id = clean_text(poi.get("poi_id") or stop.get("poi_id"))
        policy = stop.get("pet_policy_assessment") or assess_pet_policy(poi)
        policies.append(enrich_policy_with_feedback(policy, poi_feedback.get(poi_id, empty_feedback_summary())))
    if not policies:
        policies = []

    avg_score = round(sum(int(policy.get("score", 40)) for policy in policies) / max(len(policies), 1))
    layer_counts: Dict[str, int] = {}
    for policy in policies:
        key = clean_text(policy.get("layer"), "L6")
        layer_counts[key] = layer_counts.get(key, 0) + 1

    if avg_score >= 80:
        grade = "高可信"
        summary = "路线包含强证据或已验证点位，可作为优先推荐。"
    elif avg_score >= 60:
        grade = "可推荐"
        summary = "路线以强证据、场景证据和开放空间为主，适合 Demo 推荐。"
    elif avg_score >= 45:
        grade = "候选推荐"
        summary = "路线可作为候选方案，室内或低证据点需要降级展示。"
    else:
        grade = "谨慎推荐"
        summary = "证据不足，建议只保留在备选池，不主动声明宠物友好。"

    return {
        "score": avg_score,
        "grade": grade,
        "summary": summary,
        "layer_counts": layer_counts,
        "policy_cards": [
            {
                "layer": policy.get("layer"),
                "label": policy.get("label"),
                "evidence_level": policy.get("evidence_level"),
                "score": policy.get("score"),
                "poi_name": stop.get("poi", {}).get("name"),
                "basis": policy.get("basis"),
                "recommended_action": policy.get("recommended_action"),
                "access_policy": stop.get("pet_access_policy") or infer_pet_access_policy(stop.get("poi", {}), clean_text(stop.get("role")), clean_text(route.get("route_type"))),
                "user_feedback": policy.get("user_feedback", empty_feedback_summary()),
                "evidence_items": policy.get("evidence_items", []),
                "evidence_gaps": policy.get("evidence_gaps", []),
                "review_status": policy.get("review_status", "manual_review_required"),
                "trust_explanation": policy.get("trust_explanation", ""),
            }
            for stop, policy in zip(stops, policies)
        ],
        "feedback_summary": summarize_feedback(load_feedback_log()),
        "evidence_system": {
            "version": "pet_label_evidence_v1",
            "principle": "只把有证据支撑的点位标为高可信；证据不足时降级为候选或备选，不直接承诺宠物友好。",
            "source_layers": [
                {"source_type": "merchant_policy", "name": "商户后台确认", "priority": 1, "effect": "可升级 L1"},
                {"source_type": "user_feedback", "name": "近期用户到店反馈", "priority": 2, "effect": "可升级 L2 或触发负反馈降权"},
                {"source_type": "poi_category", "name": "POI 类目/商户名称", "priority": 3, "effect": "识别宠物服务强场景"},
                {"source_type": "keyword_rule", "name": "外摆/露台/户外关键词", "priority": 4, "effect": "进入开放消费候选池"},
                {"source_type": "space_context", "name": "开放空间/街区场景", "priority": 5, "effect": "适合作为散步节点"},
                {"source_type": "risk_rule", "name": "室内/商场规则风险", "priority": 6, "effect": "降级为备选或人工复核"},
            ],
            "review_status_meaning": {
                "verified": "强确认，可优先推荐",
                "review_recommended": "可推荐但需要持续补证",
                "candidate_pool": "适合作为候选，不直接承诺携宠规则",
                "manual_review_required": "证据不足或有争议，需人工复核",
            },
        },
        "framework": [
            {"layer": "L1", "label": "商户已确认", "source": "商户后台规则", "usage": "最高优先级推荐"},
            {"layer": "L2", "label": "近期用户验证", "source": "近 7-30 天到店反馈", "usage": "主路线优先展示"},
            {"layer": "L3", "label": "宠物服务门店", "source": "POI 类目/名称强命中", "usage": "服务/补给交易节点"},
            {"layer": "L4", "label": "外摆/户外线索", "source": "外摆、露台、户外关键词", "usage": "消费候选点"},
            {"layer": "L5", "label": "开放空间适配", "source": "公园、绿地、广场、街区", "usage": "散步/短暂停留节点"},
            {"layer": "L6", "label": "室内场景待核验", "source": "商场、室内、规则缺失", "usage": "雨天备选或低优先级"},
        ],
        "improvement_loop": [
            "商户后台填写携宠规则，生成 L1 官方确认标签",
            "用户到店后反馈是否可携宠、是否只限外摆、是否限制犬型",
            "近期负反馈触发降权和人工复核，高一致性反馈可升级到 L2",
        ],
    }


def calculate_route_stress(stops: List[Dict[str, Any]]) -> str:
    if not stops:
        return "中"
    score = 0
    for stop in stops:
        exp = stop.get("poi", {}).get("experience", {})
        score += stress_score(clean_text(exp.get("pet_stress_level"), "中"))
    avg = score / len(stops)
    if avg >= 2.7:
        return "低"
    if avg >= 1.8:
        return "中"
    return "高"


def build_route_risk_summary(stops: List[Dict[str, Any]], fallback: str) -> str:
    notes: List[str] = []
    for stop in stops:
        note = clean_text(stop.get("poi", {}).get("risk_note"))
        if note:
            notes.extend([part.strip() for part in re.split(r"[；;]", note) if part.strip()])
    return "；".join(unique(notes[:4])) or fallback or "携宠规则以商户实际要求为准。"


def build_risk_radar(route: Dict[str, Any], intent: Dict[str, Any]) -> List[Dict[str, Any]]:
    stops = route.get("stops", [])
    notes = "；".join(clean_text(stop.get("poi", {}).get("risk_note")) for stop in stops)
    spaces = " ".join(clean_text(stop.get("poi", {}).get("experience", {}).get("space_type")) for stop in stops)
    stress_values = [clean_text(stop.get("poi", {}).get("experience", {}).get("pet_stress_level"), "中") for stop in stops]
    policy_scores = [
        int((stop.get("pet_policy_assessment") or assess_pet_policy(stop.get("poi", {}))).get("score", 40))
        for stop in stops
    ]

    crowd_level = "高" if "人流较大" in notes or "高" in [
        clean_text(stop.get("poi", {}).get("experience", {}).get("crowd_level")) for stop in stops
    ] else "中"
    indoor_level = "高" if "室内" in spaces or "商场" in spaces else "低"
    pet_size_level = "中" if intent.get("pet_size") in {"中型犬", "大型犬"} else "低"
    weather_level = "低" if "雨天备选" in intent.get("preferences", []) else "中"
    avg_policy_score = sum(policy_scores) / max(len(policy_scores), 1) if policy_scores else 40
    uncertainty_level = "高" if avg_policy_score < 50 else ("中" if avg_policy_score < 70 else "低")
    stress_level = "高" if "高" in stress_values else ("中" if "中" in stress_values else "低")

    return [
        {
            "risk_id": "crowd",
            "label": "人流拥挤",
            "level": crowd_level,
            "score": {"低": 28, "中": 58, "高": 82}[crowd_level],
            "advice": "建议避开 16:00-18:00，并选择商圈边缘停留点。",
        },
        {
            "risk_id": "indoor_access",
            "label": "室内准入",
            "level": indoor_level,
            "score": {"低": 24, "中": 55, "高": 78}[indoor_level],
            "advice": "进入商场或室内店铺前，建议先电话确认携宠规则。",
        },
        {
            "risk_id": "pet_size",
            "label": "犬型适配",
            "level": pet_size_level,
            "score": {"低": 30, "中": 56, "高": 80}[pet_size_level],
            "advice": "中大型犬优先选择外摆、街区和开放空间，全程牵引。",
        },
        {
            "risk_id": "weather",
            "label": "天气变化",
            "level": weather_level,
            "score": {"低": 25, "中": 52, "高": 76}[weather_level],
            "advice": "如遇降雨，切换雨天备选路线并减少露天步行。",
        },
        {
            "risk_id": "rule_uncertainty",
            "label": "证据完整度",
            "level": uncertainty_level,
            "score": {"低": 34, "中": 60, "高": 86}[uncertainty_level],
            "advice": "优先使用商户确认、近期用户验证和强场景证据，低证据点降级为备选。",
        },
        {
            "risk_id": "pet_stress",
            "label": "宠物压力",
            "level": stress_level,
            "score": {"低": 26, "中": 57, "高": 82}[stress_level],
            "advice": "如宠物对噪声敏感，可缩短停留点并切换低压力路线。",
        },
    ]


def build_feasibility(route: Dict[str, Any], intent: Dict[str, Any], risk_radar: List[Dict[str, Any]]) -> Dict[str, Any]:
    budget = int(intent.get("budget", 100))
    risk_penalty = sum(item["score"] for item in risk_radar) / max(len(risk_radar), 1) * 0.28
    stop_bonus = min(len(route.get("stops", [])), 3) * 5
    budget_bonus = 8 if budget >= 100 else (4 if budget >= 60 else 0)
    score = round(max(45, min(94, 88 + stop_bonus + budget_bonus - risk_penalty)))

    if score >= 80:
        label = "适合出发"
    elif score >= 65:
        label = "谨慎出发"
    else:
        label = "建议调整"

    reasons = [
        f"当前路线包含 {len(route.get('stops', []))} 个可执行停靠点",
        f"预算 {budget} 元可覆盖主要消费动作" if budget >= 60 else "预算偏低，建议保留免费活动空间",
        "新街口核心商圈人流波动较大，需要避峰和牵引",
        "室内/商场类点位需要商户标签或用户反馈继续核验",
    ]
    return {
        "score": score,
        "label": label,
        "summary": f"今日带宠出行可行性 {score}/100：{label}",
        "reasons": reasons,
        "primary_suggestion": "优先按推荐路线出发，到店前确认室内/外摆携宠规则。",
    }


def route_reference_distance(route: Dict[str, Any]) -> int:
    distances = []
    for stop in route.get("stops", []):
        distance = stop.get("poi", {}).get("distance_m")
        if isinstance(distance, (int, float)):
            distances.append(int(distance))
    if not distances:
        return 0
    return max(distances) + int(sum(distances) / max(len(distances), 1) * 0.35)


def route_preview_points(route: Dict[str, Any], intent: Dict[str, Any]) -> List[Dict[str, Any]]:
    origin = route_origin_from_intent(intent)
    points = [
        {
            "role": "集合点",
            "name": origin["name"],
            "lat": origin["lat"],
            "lng": origin["lng"],
        }
    ]
    for stop in route.get("stops", []):
        poi = stop.get("poi", {})
        location = poi.get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            points.append({
                "role": clean_text(stop.get("role"), "途经点"),
                "name": clean_text(poi.get("name"), clean_text(stop.get("poi_id"), "POI")),
                "lat": lat,
                "lng": lng,
            })
    if len(points) > 1:
        endpoint = route_endpoint_from_intent(intent)
        points.append({
            "role": endpoint["role"],
            "name": endpoint["name"],
            "lat": endpoint["lat"],
            "lng": endpoint["lng"],
        })
    return points


def format_delta(value: int, unit: str = "") -> str:
    if value > 0:
        return f"+{value}{unit}"
    if value < 0:
        return f"{value}{unit}"
    return f"0{unit}"


def comparison_route_types(intent: Dict[str, Any], selected_route_type: str) -> List[str]:
    route_types = [selected_route_type]
    budget = int(intent.get("budget", 100))
    hours = parse_available_hours(intent.get("available_time"))

    if wants_activity_without_commerce(intent):
        route_types.extend(["low_stress", "balanced"])
    elif budget <= 30 or hours <= 1.5:
        route_types.extend(["quick_walk", "budget_saver", "low_stress"])
    elif budget <= 60:
        route_types.extend(["quick_walk", "low_stress", "balanced"])
    elif selected_route_type == "rainy_day":
        route_types.extend(["low_stress", "balanced", "budget_saver"])
    elif selected_route_type == "low_stress":
        route_types.append("budget_saver" if budget <= 80 else "balanced")
        route_types.append("rainy_day")
        if budget > 80:
            route_types.append("budget_saver")
    elif selected_route_type == "service_supply":
        route_types.extend(["balanced", "low_stress", "budget_saver"])
    else:
        if intent_contains(intent, ["室内", "雨天", "雨"]):
            route_types.append("rainy_day")
            route_types.append("low_stress")
        else:
            route_types.extend(["low_stress", "budget_saver", "rainy_day"])

    return unique(route_types)[:4]


def localized_route_name(route_name: Any, intent: Dict[str, Any]) -> str:
    name = clean_text(route_name, "推荐路线")
    location = clean_text(intent.get("location"), "南京新街口")
    area_label = location.replace("南京", "")
    if area_label in {"新街口", ""}:
        return name
    if "新街口" in name:
        return name.replace("新街口", area_label)
    return f"{area_label}{name}"


def build_route_comparisons(data: Dict[str, Any], intent: Dict[str, Any], selected_route_type: str) -> List[Dict[str, Any]]:
    raw_comparisons = []
    for route_type in comparison_route_types(intent, selected_route_type):
        route = enhance_route_with_business_logic(data, get_route(data, route_type), intent, route_type)
        risk_radar = build_risk_radar(route, intent)
        feasibility = build_feasibility(route, intent, risk_radar)
        cost_low, cost_high = route_cost_bounds(route.get("stops", []))
        distance_m = route_reference_distance(route)
        max_risk = max(risk_radar, key=lambda item: item["score"])
        raw_comparisons.append(
            {
                "route_type": route_type,
                "route_name": localized_route_name(route.get("route_name"), intent),
                "selected": route_type == selected_route_type,
                "estimated_time": route.get("estimated_time"),
                "estimated_budget": route.get("estimated_budget"),
                "budget_low": cost_low,
                "budget_high": cost_high,
                "walking_distance_m": distance_m,
                "preview_points": route_preview_points(route, intent),
                "pet_friendly_score": route.get("pet_friendly_score"),
                "pet_stress_level": route.get("pet_stress_level"),
                "feasibility_score": feasibility["score"],
                "risk_level": max_risk["level"],
                "primary_risk": max_risk["label"],
                "trade_opportunities": len(extract_commercial_actions(route)),
                "best_for": comparison_best_for(route_type, intent),
            }
        )

    selected = next((item for item in raw_comparisons if item["selected"]), raw_comparisons[0] if raw_comparisons else {})
    for item in raw_comparisons:
        item["difference_from_selected"] = {
            "budget_high_delta": item.get("budget_high", 0) - selected.get("budget_high", 0),
            "walking_distance_delta_m": item.get("walking_distance_m", 0) - selected.get("walking_distance_m", 0),
            "feasibility_delta": item.get("feasibility_score", 0) - selected.get("feasibility_score", 0),
            "trade_opportunity_delta": item.get("trade_opportunities", 0) - selected.get("trade_opportunities", 0),
        }
        item["tradeoff_summary"] = build_tradeoff_summary(item, selected)
    return raw_comparisons


def build_tradeoff_summary(item: Dict[str, Any], selected: Dict[str, Any]) -> str:
    if item.get("selected"):
        return "当前最匹配输入约束，作为默认推荐。"

    diff = item.get("difference_from_selected", {})
    parts = []
    budget_delta = int(diff.get("budget_high_delta", 0))
    walk_delta = int(diff.get("walking_distance_delta_m", 0))
    feasibility_delta = int(diff.get("feasibility_delta", 0))
    trade_delta = int(diff.get("trade_opportunity_delta", 0))

    if budget_delta:
        parts.append(f"预算上限{format_delta(budget_delta, '元')}")
    if walk_delta:
        parts.append(f"参考步行距离{format_delta(walk_delta, 'm')}")
    if feasibility_delta:
        parts.append(f"可行性{format_delta(feasibility_delta)}")
    if trade_delta:
        parts.append(f"交易点{format_delta(trade_delta)}")
    if item.get("primary_risk"):
        parts.append(f"主要风险：{item['primary_risk']}")
    return "；".join(parts) or "与默认路线差异较小，可作为同级备选。"


def comparison_best_for(route_type: str, intent: Dict[str, Any]) -> str:
    if wants_activity_without_commerce(intent):
        return {
            "main": "纯散步需求，优先公园/街区活动空间",
            "balanced": "纯散步需求，优先公园/街区活动空间",
            "budget_saver": "少消费、保留免费活动空间",
            "low_stress": "减少人流刺激，适合大型犬牵引慢走",
            "rainy_day": "天气变化时的保守备选",
            "service_supply": "需要补给时再加入服务点",
            "quick_walk": "只保留短时散步停留点",
        }[route_type]
    return {
        "main": "均衡短逛和本地生活消费",
        "balanced": "预算、时间、消费机会较均衡",
        "budget_saver": "预算有限，保留免费空间和低客单点",
        "low_stress": "怕拥挤、需要避峰的宠物",
        "rainy_day": "下雨或需要室内/半室内备选",
        "service_supply": "需要洗护、用品或宠物服务补给",
        "quick_walk": "时间短或只想散步",
    }[route_type]


def build_community_modules(intent: Dict[str, Any]) -> Dict[str, Any]:
    location = clean_text(intent.get("location"), "南京新街口")
    pet_size = clean_text(intent.get("pet_size"), "中型犬")
    return {
        "forum": {
            "title": "新街口带宠互助圈",
            "description": "让 C 端用户分享实时携宠体验，补足平台规则不确定的信息缺口。",
            "posts": [
                {"user": "今天也遛狗", "tag": "实时反馈", "content": "德基附近 16:30 后人流偏高，中型犬建议走外围路线。", "likes": 128, "comments": 24, "image_style": "route"},
                {"user": "咖啡和狗", "tag": "外摆情报", "content": "外摆下午更友好，店员说牵引绳和不进室内是关键。", "likes": 96, "comments": 18, "image_style": "cafe"},
                {"user": "玄武湖边走走", "tag": "低压路线", "content": "玄武湖边晚风舒服，但周末儿童车多，建议靠湖边慢走。", "likes": 88, "comments": 12, "image_style": "park"},
                {"user": "小狗不社恐", "tag": "求助", "content": "临时加班，想找今晚 7 点鼓楼附近 40 分钟代溜。", "likes": 43, "comments": 9, "image_style": "walker"},
                {"user": "雨天也要出门", "tag": "雨天备选", "content": "商场不是都能进，雨天最好只把商场当集合/避雨备选。", "likes": 57, "comments": 11, "image_style": "rainy"},
                {"user": "老门东散步员", "tag": "避坑", "content": "秦淮游客区拍照点多，牵引距离要短，别让狗靠近小吃摊。", "likes": 64, "comments": 15, "image_style": "street"},
            ],
            "feedback_actions": ["可以带狗", "只限小型犬", "外摆关闭", "人太多", "店员友好", "求代溜", "发布避坑"],
        },
        "dog_walking_service": {
            "title": "C 端代溜服务",
            "description": "当用户没时间或不适合亲自出门时，匹配附近认证代溜员，形成服务交易闭环。",
            "recommended_package": f"{location} {pet_size} 45 分钟低压力代溜",
            "price_range": "39-69元",
            "service_promises": ["实名认证", "路线轨迹回传", "宠物状态照片", "异常情况即时联系"],
            "available_walkers": [
                {"name": "阿南", "distance": "0.8km", "rating": "4.9", "tags": ["中型犬经验", "可拍照回传"], "price": "49元/45分钟"},
                {"name": "小周", "distance": "1.4km", "rating": "4.8", "tags": ["晚间可约", "低压力路线"], "price": "59元/60分钟"},
            ],
            "cta": "发布代溜需求",
        },
    }


def build_decision_trace(
    intent: Dict[str, Any],
    route_type: str,
    route: Dict[str, Any],
    risk_radar: List[Dict[str, Any]],
) -> Dict[str, Any]:
    strongest_risk = max(risk_radar, key=lambda item: item["score"]) if risk_radar else {}
    data_gap_notes: List[str] = []
    if intent_contains(intent, ["公园/绿地活动", "公园", "绿地"]):
        has_park_stop = any(
            has_any(poi_primary_text(stop.get("poi", {})), ["公园", "绿地"])
            for stop in route.get("stops", [])
        )
        if not has_park_stop:
            data_gap_notes.append("当前 shortlist 中缺少真实公园/绿地 POI，已用街区活动空间兜底。")
    return {
        "selected_route_type": route_type,
        "intent_signals": {
            "budget": intent.get("budget"),
            "available_time": intent.get("available_time"),
            "pet_size": intent.get("pet_size"),
            "preferences": intent.get("preferences", []),
            "avoid": intent.get("avoid", []),
            "commercial_intent": intent.get("commercial_intent", []),
        },
        "poi_selection_policy": "按携宠标签、宠物压力、人流、距离、商业意图和场景约束综合打分选点",
        "stop_selection": [
            {
                "order": stop.get("order"),
                "role": stop.get("role"),
                "poi_id": stop.get("poi_id"),
                "poi_name": stop.get("poi", {}).get("name"),
                "selection_score": stop.get("selection_score"),
                "selection_meta": stop.get("selection_meta", {}),
                "reason": stop.get("reason"),
            }
            for stop in route.get("stops", [])
        ],
        "strongest_risk": {
            "risk_id": strongest_risk.get("risk_id"),
            "label": strongest_risk.get("label"),
            "level": strongest_risk.get("level"),
            "advice": strongest_risk.get("advice"),
        },
        "data_gap_notes": data_gap_notes,
    }


def build_candidate_pool_summary(data: Dict[str, Any], intent: Dict[str, Any], route_type: str) -> Dict[str, Any]:
    feedback_stats = feedback_by_poi()
    groups = {}
    for group_name in LIVE_QUERY_GROUPS:
        candidates = get_poi_group(data, group_name)
        scored = sorted(
            [
                {
                    "poi_id": clean_text(poi.get("poi_id")),
                    "name": clean_text(poi.get("name")),
                    "score": score_poi_for_intent(poi, group_name, intent, route_type, feedback_stats),
                    "source": clean_text(poi.get("source_api"), "local_demo_json"),
                }
                for poi in candidates
            ],
            key=lambda item: item["score"],
            reverse=True,
        )
        groups[group_name] = {
            "candidate_count": len(scored),
            "live_count": sum(1 for item in scored if item["source"] == "baidu_place_v2"),
            "top_candidates": scored[:5],
        }
    return {
        "selection_mode": "dynamic_ranked_pool",
        "explanation": "每次先按用户预算、区域、宠物压力、人流、消费意图和实时 POI 来源打分，再从接近最高分的候选池中确定路线站点。",
        "groups": groups,
    }


def build_rule_response(
    data: Dict[str, Any],
    request: PlanRouteRequest,
    source: str = "rule_engine",
) -> Dict[str, Any]:
    base = data.get("user_input_example", {})
    intent = parse_intent(request.user_message, base)
    area = area_for_request(request, intent)
    if request.area_id and request.area_id in AREA_PROFILES:
        intent["location"] = area_location_name(area)
    live_pois = build_live_pois(area, intent) if request.use_live_data else {group: [] for group in LIVE_QUERY_GROUPS}
    live_poi_count = sum(len(items) for items in live_pois.values())
    planning_data = merge_live_data(data, live_pois) if live_poi_count else data
    route_type = select_route_type(intent, request.force_route_type)
    route = get_route(planning_data, route_type)
    enhanced_route = enhance_route_with_business_logic(planning_data, route, intent, route_type)
    enhanced_route["route_name"] = localized_route_name(enhanced_route.get("route_name"), intent)
    risk_radar = build_risk_radar(enhanced_route, intent)
    feasibility = build_feasibility(enhanced_route, intent, risk_radar)
    route_comparisons = build_route_comparisons(planning_data, intent, route_type)

    if route_type == "rainy_day":
        response_summary = "已为你切换到新街口雨天备选线，优先选择可避雨停靠点；室内/商场点会明确按备选展示，不直接承诺可携宠。"
    elif route_type == "low_stress":
        response_summary = "已为你切换到新街口低压力避峰线，减少非必要停留点，并优先选择宠物压力较低的 POI。"
    elif route_type == "quick_walk":
        response_summary = "已按短时/低预算或不消费约束生成纯散步快线，不安排咖啡、餐饮或洗护等额外消费点。"
    elif route_type == "budget_saver":
        response_summary = "已按预算优先生成省钱短逛线，保留免费活动空间和低客单停靠点，暂不安排洗护服务。"
    elif route_type == "service_supply":
        response_summary = "已按宠物服务/补给意图生成服务线，优先安排洗护或用品补给节点。"
    elif wants_activity_without_commerce(intent):
        response_summary = "已识别你更想去公园/街区散步，当前路线会优先安排开放活动空间，不强制加入消费点。"
    else:
        response_summary = "已为你生成新街口均衡短逛线，兼顾短时散步、本地生活消费和可选补给。"

    return {
        "source": source,
        "llm_used": False,
        "parsed_input": intent,
        "route_origin": route_origin_from_intent(intent),
        "route_endpoint": route_endpoint_from_intent(intent),
        "route_itinerary_semantics": {
            "start_role": "集合点",
            "via_role": "途经站点",
            "end_role": "返程点",
            "description": "参考旅游攻略的起终点表达：从用户所在位置或商圈入口集合，按推荐站点游览，最后回到便于返程的位置。",
        },
        "area": {
            "area_id": area.get("area_id", "xinjiekou"),
            "label": area.get("label"),
            "district": area.get("district"),
            "positioning": area.get("positioning"),
            "center": area.get("center"),
            "radius_m": area.get("radius"),
        },
        "selected_area": {
            "area_id": area.get("area_id", "xinjiekou"),
            "label": area.get("label"),
            "district": area.get("district"),
            "positioning": area.get("positioning"),
            "center": area.get("center"),
            "radius_m": area.get("radius"),
        },
        "live_data": {
            "enabled": request.use_live_data,
            "used": bool(live_poi_count),
            "poi_count": live_poi_count,
            "group_counts": {group: len(items) for group, items in live_pois.items()},
            "source": "baidu_place_v2" if live_poi_count else "local_demo_json",
        },
        "live_data_used": bool(live_poi_count),
        "live_poi_count": live_poi_count,
        "selected_route_type": route_type,
        "response_summary": response_summary,
        "route": enhanced_route,
        "pet_label_summary": build_pet_label_summary(enhanced_route),
        "feasibility": feasibility,
        "risk_radar": risk_radar,
        "route_comparisons": route_comparisons,
        "community_modules": build_community_modules(intent),
        "commercial_actions": extract_commercial_actions(enhanced_route),
        "decision_trace": build_decision_trace(intent, route_type, enhanced_route, risk_radar),
        "candidate_pool_summary": build_candidate_pool_summary(planning_data, intent, route_type),
        "feedback_summary": summarize_feedback(load_feedback_log()),
        "backend_capabilities": [
            "intent_parse",
            "dynamic_poi_scoring",
            "route_replanning",
            "risk_radar",
            "commerce_action_mapping",
            "community_feedback_modules",
            "pet_label_evidence_layering",
            "user_feedback_loop",
            "feedback_aware_ranking",
            "route_tradeoff_comparison",
            "structured_evidence_system",
            "manual_review_workflow",
            "multi_district_live_poi",
            "baidu_place_api_live_search",
        ],
        "manual_review_required": True,
        "data_version": "local_demo_json",
        "generated_at": int(time.time()),
    }


def extract_commercial_actions(route: Dict[str, Any]) -> List[Dict[str, str]]:
    actions = []
    for stop in route.get("stops", []):
        poi = stop.get("poi", {})
        business = poi.get("business", {})
        action = clean_text(business.get("transaction_action"), "加入路线")
        if stop.get("role") == "宠物服务/补给点" and action in {"加入路线", "出发前确认", "电话咨询/到店服务"}:
            action = "预约洗护/电话咨询"
        if any(word in action for word in ["洗护", "服务", "预约"]):
            label = f"美团预约：{action}"
        elif any(word in action for word in ["加入", "路线"]):
            label = f"美团路线：{action}"
        elif any(word in action for word in ["备选", "详情"]):
            label = f"美团查看：{action}"
        elif any(word in action for word in ["电话", "确认", "咨询"]):
            label = f"美团咨询：{action}"
        elif any(word in action for word in ["团购", "咖啡", "餐饮"]):
            label = f"美团查看：{action}"
        else:
            label = f"美团动作：{action}"
        actions.append({"poi_id": clean_text(poi.get("poi_id")), "poi_name": clean_text(poi.get("name")), "action": label})
    return actions


def llm_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def call_llm_for_summary(rule_response: Dict[str, Any], user_message: str) -> Optional[Dict[str, str]]:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    api_url = os.getenv("LLM_API_URL") or os.getenv("OPENAI_API_URL") or DEFAULT_LLM_URL
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    route = rule_response["route"]
    compact_context = {
        "user_message": user_message,
        "parsed_input": rule_response["parsed_input"],
        "selected_route_type": rule_response["selected_route_type"],
        "route_name": route.get("route_name"),
        "stops": [
            {
                "role": stop.get("role"),
                "poi_name": stop.get("poi", {}).get("name"),
                "pet_status": stop.get("poi", {}).get("pet_friendly", {}).get("status"),
                "confidence": stop.get("poi", {}).get("pet_friendly", {}).get("confidence_level"),
                "risk_note": stop.get("poi", {}).get("risk_note"),
            }
            for stop in route.get("stops", [])
        ],
    }

    system_prompt = (
        "你是 FluffyGo 的带宠本地生活路线规划助手。"
        "只能基于给定 POI 和路线信息解释推荐理由，不要编造商家。"
        "返回严格 JSON，字段为 response_summary, planner_reason, risk_summary。"
        "语气专业、简洁、适合产品 Demo。"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(compact_context, ensure_ascii=False)},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=12)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return {key: clean_text(value) for key, value in parsed.items()}
    except Exception:
        return None

    return None


def infer_live_group_from_keyword(keyword: str) -> str:
    if has_any(keyword, ["宠物店", "宠物洗护", "宠物用品", "宠物医院", "洗护", "补给"]):
        return "pet_services"
    if has_any(keyword, ["商场", "购物中心", "商业街", "室内", "雨天"]):
        return "rainy_day_backups"
    if has_any(keyword, ["咖啡", "餐饮", "轻食", "饭"]):
        return "consumption_points"
    return "activity_spaces"


@app.get("/api/areas")
def list_areas() -> Dict[str, Any]:
    return {
        "ok": True,
        "areas": [area_profile(area_id) for area_id in AREA_PROFILES],
        "default_area_id": "xinjiekou",
        "coverage_note": "当前 Demo 支持新街口、鼓楼区、秦淮区、玄武区，可用百度 Place API 动态补充 POI。",
    }


@app.get("/api/live-pois")
def live_pois(
    area_id: str = Query("xinjiekou"),
    keyword: str = Query("咖啡", min_length=1),
) -> Dict[str, Any]:
    if area_id not in AREA_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unsupported area_id: {area_id}")

    area = area_profile(area_id)
    group_name = infer_live_group_from_keyword(keyword)
    raw_results = baidu_place_search(keyword, area, page_size=12)
    pois: List[Dict[str, Any]] = []
    seen_names = set()
    for index, result in enumerate(raw_results, start=1):
        name = clean_text(result.get("name"))
        if not name or name in seen_names:
            continue
        poi = live_result_to_poi(result, group_name, keyword, index, area)
        if poi:
            seen_names.add(name)
            pois.append(poi)

    return {
        "ok": True,
        "area": area,
        "keyword": keyword,
        "source": "baidu_place_v2" if pois else "none_or_unavailable",
        "count": len(pois),
        "pois": pois,
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "fluffygo-route-api",
        "data_exists": DATA_PATH.exists(),
        "llm_configured": llm_configured(),
    }


@app.get("/api/config")
def frontend_config() -> Dict[str, Any]:
    baidu_map_ak = os.getenv("BAIDU_MAP_WEB_AK") or os.getenv("BAIDU_MAP_AK") or ""
    return {
        "baidu_map_enabled": bool(baidu_map_ak),
        "baidu_map_ak": baidu_map_ak,
        "map_provider": "baidu",
        "areas": [area_profile(area_id) for area_id in AREA_PROFILES],
        "default_area_id": "xinjiekou",
    }


@app.get("/api/demo-data")
def demo_data() -> Dict[str, Any]:
    return load_demo_data()


@app.get("/api/demo-readiness")
def demo_readiness() -> Dict[str, Any]:
    data = load_demo_data()
    pois = all_pois(data)
    routes = data.get("route_templates", [])
    feedback_items = load_feedback_log()
    baidu_map_ak = os.getenv("BAIDU_MAP_WEB_AK") or os.getenv("BAIDU_MAP_AK") or ""
    checks = [
        {"check": "demo_json", "ok": DATA_PATH.exists(), "detail": str(DATA_PATH)},
        {"check": "poi_pool", "ok": len(pois) >= 20, "detail": f"{len(pois)} POIs"},
        {"check": "route_templates", "ok": len(routes) >= 3, "detail": f"{len(routes)} templates"},
        {"check": "baidu_map_browser_ak", "ok": bool(baidu_map_ak), "detail": "configured" if baidu_map_ak else "missing"},
        {"check": "multi_district_coverage", "ok": len(AREA_PROFILES) >= 4, "detail": f"{len(AREA_PROFILES)} areas"},
        {"check": "baidu_place_api_live_search", "ok": bool(os.getenv("BAIDU_MAP_AK")), "detail": "configured" if os.getenv("BAIDU_MAP_AK") else "missing server AK"},
        {"check": "feedback_loop", "ok": True, "detail": f"{len(feedback_items)} runtime feedback records"},
        {"check": "llm_optional", "ok": True, "detail": "configured" if llm_configured() else "rule engine fallback"},
    ]
    return {
        "ok": all(item["ok"] for item in checks if item["check"] not in {"llm_optional", "baidu_map_browser_ak"}),
        "project": "FluffyGo",
        "demo_area": data.get("project", {}).get("demo_area", "南京新街口"),
        "checks": checks,
        "poi_count": len(pois),
        "route_template_count": len(routes),
        "feedback_count": len(feedback_items),
        "backend_capabilities": [
            "intent_parse",
            "dynamic_poi_scoring",
            "feedback_aware_ranking",
            "structured_evidence_system",
            "real_baidu_walking_map",
            "route_tradeoff_comparison",
            "multi_district_area_api",
            "baidu_place_api_live_search",
            "community_and_walker_service_concepts",
        ],
    }


@app.get("/api/feedback-summary")
def feedback_summary() -> Dict[str, Any]:
    items = load_feedback_log()
    return {
        "ok": True,
        "summary": summarize_feedback(items),
        "by_poi": feedback_by_poi(),
        "storage": str(FEEDBACK_PATH),
    }


@app.post("/api/poi-feedback")
def submit_poi_feedback(feedback: PoiFeedbackRequest) -> Dict[str, Any]:
    item = {
        "feedback_id": f"fb_{int(time.time() * 1000)}",
        "poi_id": clean_text(feedback.poi_id),
        "poi_name": clean_text(feedback.poi_name),
        "vote": clean_text(feedback.vote),
        "note": clean_text(feedback.note),
        "source": clean_text(feedback.source, "demo_user"),
        "sentiment": feedback_sentiment(feedback.vote),
        "created_at": int(time.time()),
    }

    items = load_feedback_log()
    items.append(item)
    save_feedback_log(items)
    poi_items = [entry for entry in items if entry.get("poi_id") == item["poi_id"]]
    return {
        "ok": True,
        "feedback": item,
        "summary": summarize_feedback(poi_items),
    }


@app.post("/api/plan-route")
def plan_route(request: PlanRouteRequest) -> Dict[str, Any]:
    data = load_demo_data()
    response = build_rule_response(data, request)

    if request.use_llm and llm_configured():
        llm_result = call_llm_for_summary(response, request.user_message)
        if llm_result:
            response["source"] = "llm_enhanced"
            response["llm_used"] = True
            response["response_summary"] = llm_result.get("response_summary") or response["response_summary"]
            response["route"]["planner_reason"] = llm_result.get("planner_reason") or response["route"].get("planner_reason")
            response["route"]["risk_summary"] = llm_result.get("risk_summary") or response["route"].get("risk_summary")

    return response


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)
