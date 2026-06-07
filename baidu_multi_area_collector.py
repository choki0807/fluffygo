import os
import time
from typing import Any, Dict, List

import pandas as pd
import requests
from dotenv import load_dotenv


load_dotenv()

OUTPUT_CSV = "fluffygo_nanjing_core_poi_raw.csv"
PLACE_API = "https://api.map.baidu.com/place/v2/search"

AREAS: Dict[str, Dict[str, Any]] = {
    "xinjiekou": {"area_name": "南京新街口", "district": "核心商圈", "lat": 32.0415, "lng": 118.7841, "radius": 3000},
    "gulou": {"area_name": "鼓楼区", "district": "鼓楼区", "lat": 32.0664, "lng": 118.7697, "radius": 6500},
    "qinhuai": {"area_name": "秦淮区", "district": "秦淮区", "lat": 32.0187, "lng": 118.7947, "radius": 6500},
    "xuanwu": {"area_name": "玄武区", "district": "玄武区", "lat": 32.0504, "lng": 118.8489, "radius": 7000},
}

KEYWORDS = [
    "公园",
    "绿地",
    "广场",
    "商业街",
    "咖啡",
    "外摆咖啡",
    "宠物友好咖啡",
    "餐饮",
    "轻食",
    "宠物店",
    "宠物洗护",
    "宠物用品",
    "宠物医院",
    "商场",
    "购物中心",
]


def classify_pet_friendly(text: str) -> Dict[str, str]:
    if any(word in text for word in ["宠物店", "宠物洗护", "宠物用品", "宠物医院", "宠物"]):
        return {"pet_friendly_status": "宠物服务相关", "confidence_level": "高"}
    if any(word in text for word in ["外摆", "露台", "户外", "宠物友好", "可带狗"]):
        return {"pet_friendly_status": "可能宠物友好", "confidence_level": "中"}
    return {"pet_friendly_status": "待确认", "confidence_level": "低"}


def infer_route_role(keyword: str, category: str) -> str:
    text = f"{keyword} {category}"
    if any(word in text for word in ["宠物店", "宠物洗护", "宠物用品", "宠物医院"]):
        return "宠物服务/补给点"
    if any(word in text for word in ["商场", "购物中心"]):
        return "雨天备选点"
    if any(word in text for word in ["公园", "绿地", "广场", "商业街"]):
        return "短时活动空间"
    return "宠物友好消费点"


def search_area_keyword(ak: str, area_id: str, area: Dict[str, Any], keyword: str) -> List[Dict[str, Any]]:
    params = {
        "query": keyword,
        "location": f"{area['lat']},{area['lng']}",
        "radius": area["radius"],
        "region": "南京",
        "city_limit": "true",
        "output": "json",
        "scope": 2,
        "page_size": 20,
        "ak": ak,
    }
    response = requests.get(PLACE_API, params=params, timeout=8)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != 0:
        print(f"Skip {area['area_name']} / {keyword}: {payload.get('message') or payload.get('status')}")
        return []

    rows = []
    for item in payload.get("results", []):
        detail = item.get("detail_info") or {}
        location = item.get("location") or {}
        name = str(item.get("name") or "").strip()
        category = str(detail.get("tag") or item.get("tag") or item.get("type") or "").strip()
        address = str(item.get("address") or "").strip()
        evidence_text = f"{name} {category} {keyword} {address}"
        label = classify_pet_friendly(evidence_text)
        role = infer_route_role(keyword, category)
        rows.append({
            "area_id": area_id,
            "area_name": area["area_name"],
            "district": area["district"],
            "poi_name": name,
            "category": category,
            "source_keyword": keyword,
            "address": address,
            "distance": detail.get("distance"),
            "lat": location.get("lat"),
            "lng": location.get("lng"),
            "telephone": item.get("telephone") or detail.get("telephone") or "",
            "pet_friendly_status": label["pet_friendly_status"],
            "confidence_level": label["confidence_level"],
            "evidence_source": "百度地图 Place API + FluffyGo 轻量规则",
            "evidence_text": evidence_text,
            "suitable_pet_size": "小型犬/中型犬",
            "space_type": "开放空间" if role == "短时活动空间" else "本地生活空间",
            "crowd_level": "中",
            "pet_stress_level": "中",
            "risk_note": "携宠规则需以商户/现场为准",
            "transaction_action": "预约洗护/电话咨询" if role == "宠物服务/补给点" else "查看门店/加入路线",
            "route_role": role,
        })
    return rows


def main() -> None:
    ak = os.getenv("BAIDU_MAP_AK")
    if not ak:
        raise SystemExit("Missing BAIDU_MAP_AK. Please create .env and fill your Baidu Map server AK.")

    all_rows: List[Dict[str, Any]] = []
    seen = set()
    for area_id, area in AREAS.items():
        for keyword in KEYWORDS:
            rows = search_area_keyword(ak, area_id, area, keyword)
            for row in rows:
                key = (row["area_id"], row["poi_name"], row["address"])
                if row["poi_name"] and key not in seen:
                    seen.add(key)
                    all_rows.append(row)
            time.sleep(0.15)

    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Output: {OUTPUT_CSV}")
    print(f"Rows: {len(df)}")
    print(f"Areas: {', '.join(area['area_name'] for area in AREAS.values())}")


if __name__ == "__main__":
    main()
