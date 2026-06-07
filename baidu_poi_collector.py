import os
import time
from typing import Dict, List, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv


API_URL = "https://api.map.baidu.com/place/v2/search"
OUTPUT_CSV = "fluffygo_xinjiekou_poi_raw.csv"
SHORTLIST_CSV = "fluffygo_xinjiekou_poi_shortlist.csv"

LOCATION = "32.0415,118.7841"
RADIUS = 5000
CITY = "南京"
PAGE_SIZE = 20
PAGE_NUMS = 2

KEYWORDS = [
    "新街口 咖啡",
    "新街口 外摆 咖啡",
    "新街口 露台 咖啡",
    "新街口 茶饮",
    "新街口 轻食",
    "新街口 餐厅",
    "新街口 小吃",
    "新街口 宠物店",
    "新街口 宠物洗护",
    "新街口 宠物用品",
    "新街口 宠物医院",
    "新街口 宠物美容",
    "新街口 公园",
    "新街口 城市公园",
    "新街口 社区公园",
    "新街口 绿地",
    "新街口 广场",
    "新街口 步行街",
    "新街口 商场",
    "新街口 购物中心",
    "新街口 商业街",
    "玄武湖 公园",
    "莫愁湖 公园",
    "夫子庙 步行街",
]

CSV_COLUMNS = [
    "poi_name",
    "category",
    "source_keyword",
    "address",
    "distance",
    "lat",
    "lng",
    "telephone",
    "pet_friendly_status",
    "confidence_level",
    "evidence_source",
    "evidence_text",
    "suitable_pet_size",
    "space_type",
    "crowd_level",
    "pet_stress_level",
    "risk_note",
    "transaction_action",
    "route_role",
]

SHORTLIST_COLUMNS = CSV_COLUMNS + [
    "demo_selected_reason",
    "manual_review_required",
]

CONFIDENCE_RANK = {"高": 0, "中": 1, "低": 2}
PET_STRESS_RANK = {"低": 0, "中": 1, "高": 2}

SHORTLIST_GROUPS = [
    {
        "route_role": "短时活动空间",
        "limit": 3,
        "keywords": ("公园", "绿地", "广场", "商业街", "街区", "步行街"),
        "reason": "适合作为遛宠路线中的短时活动和停留空间",
    },
    {
        "route_role": "宠物友好消费点",
        "limit": 4,
        "keywords": ("咖啡", "外摆", "轻食", "餐饮", "露台", "户外"),
        "reason": "适合作为路线中的消费停靠点，优先保留非待确认携宠状态",
    },
    {
        "route_role": "宠物服务/补给点",
        "limit": 3,
        "keywords": ("宠物店", "宠物洗护", "宠物用品", "宠物医院", "宠物"),
        "reason": "适合作为宠物服务、护理或补给节点",
    },
    {
        "route_role": "雨天备选点",
        "limit": 2,
        "keywords": ("商场", "商业街", "半室内", "宠物用品", "咖啡", "购物中心", "商城"),
        "reason": "适合作为雨天或天气不佳时的备选停靠点",
    },
]


def text_contains(text: str, words: Tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def combined_search_text(row: pd.Series) -> str:
    return " ".join(
        str(row.get(field, ""))
        for field in ("poi_name", "category", "source_keyword", "space_type", "pet_friendly_status")
    )


def poi_search_text(row: pd.Series) -> str:
    return " ".join(
        str(row.get(field, ""))
        for field in ("poi_name", "category", "space_type")
    )


def distance_to_number(value) -> int:
    try:
        if pd.isna(value) or value == "":
            return 999999
        return int(float(value))
    except (TypeError, ValueError):
        return 999999


def shortlist_sort_columns(df: pd.DataFrame) -> pd.DataFrame:
    sorted_df = df.copy()
    sorted_df["_confidence_rank"] = sorted_df["confidence_level"].map(CONFIDENCE_RANK).fillna(9)
    sorted_df["_distance_rank"] = sorted_df["distance"].apply(distance_to_number)
    sorted_df["_stress_rank"] = sorted_df["pet_stress_level"].map(PET_STRESS_RANK).fillna(9)
    return sorted_df.sort_values(
        by=["_confidence_rank", "_distance_rank", "_stress_rank", "poi_name"],
        ascending=[True, True, True, True],
    )


def match_group_candidates(df: pd.DataFrame, keywords: Tuple[str, ...], route_role: str) -> pd.DataFrame:
    def is_match(row: pd.Series) -> bool:
        name_category_text = f"{row.get('poi_name', '')} {row.get('category', '')}"
        full_text = combined_search_text(row)

        if route_role == "短时活动空间":
            excluded = ("美食", "酒店", "出入口", "交通设施", "房地产", "政府机构", "购物")
            if text_contains(str(row.get("category", "")), excluded):
                return False
            return text_contains(
                name_category_text,
                ("公园", "绿地", "广场", "商业街", "街区", "步行街"),
            )

        if route_role == "宠物友好消费点":
            is_consumption = text_contains(name_category_text, keywords)
            is_food_with_outdoor_intent = (
                text_contains(str(row.get("category", "")), ("美食", "餐饮", "咖啡"))
                and text_contains(full_text, ("外摆", "露台", "户外", "宠物友好"))
            )
            return is_consumption or is_food_with_outdoor_intent

        if route_role == "宠物服务/补给点":
            return text_contains(
                f"{row.get('poi_name', '')} {row.get('category', '')}",
                ("宠物", "宠物店", "宠物洗护", "宠物用品", "宠物医院"),
            )

        if route_role == "雨天备选点":
            indoor_text = f"{row.get('poi_name', '')} {row.get('category', '')} {row.get('space_type', '')}"
            return text_contains(indoor_text, ("商场", "购物中心", "商城", "百货", "半室内", "宠物用品"))

        return text_contains(poi_search_text(row), keywords)

    mask = df.apply(is_match, axis=1)
    candidates = df[mask].copy()

    if route_role == "宠物友好消费点":
        candidates["_status_priority"] = candidates["pet_friendly_status"].eq("待确认").astype(int)
        candidates = candidates.sort_values(
            by=["_status_priority", "distance"],
            key=lambda column: column.apply(distance_to_number) if column.name == "distance" else column,
        ).drop(columns=["_status_priority"])

    return candidates


def build_shortlist(raw_df: pd.DataFrame) -> pd.DataFrame:
    selected_rows = []
    selected_names = set()

    source_df = raw_df.drop_duplicates(subset=["poi_name"], keep="first").copy()

    for group in SHORTLIST_GROUPS:
        candidates = match_group_candidates(source_df, group["keywords"], group["route_role"])
        candidates = shortlist_sort_columns(candidates)

        picked_count = 0
        for _, row in candidates.iterrows():
            poi_name = row["poi_name"]
            if poi_name in selected_names:
                continue

            selected = row[CSV_COLUMNS].to_dict()
            selected["route_role"] = group["route_role"]
            selected["demo_selected_reason"] = group["reason"]
            selected["manual_review_required"] = "是"

            selected_rows.append(selected)
            selected_names.add(poi_name)
            picked_count += 1

            if picked_count >= group["limit"]:
                break

    shortlist_df = pd.DataFrame(selected_rows, columns=SHORTLIST_COLUMNS)
    return shortlist_df


def classify_pet_friendly(name: str, category: str, keyword: str) -> Tuple[str, str, str]:
    combined = f"{name} {category} {keyword}"

    if text_contains(combined, ("宠物", "宠物店", "宠物洗护", "宠物用品")):
        return "宠物服务相关", "高", "命中宠物服务关键词"

    if text_contains(combined, ("外摆", "露台", "户外", "可带狗", "宠物友好")):
        return "可能宠物友好", "中", "命中外摆/户外/宠物友好关键词"

    if text_contains(combined, ("公园", "绿地", "广场", "商业街")):
        return "待确认", "低", "开放空间或街区类 POI，需人工确认携宠规则"

    return "待确认", "低", "未命中明确宠物友好证据"


def infer_space_type(name: str, category: str, keyword: str) -> str:
    poi_text = f"{name} {category}"
    combined = f"{poi_text} {keyword}"

    if text_contains(poi_text, ("商场", "购物中心", "百货", "商城")):
        return "室内/商场"
    if text_contains(poi_text, ("外摆", "露台", "户外")) or (
        text_contains(category, ("美食", "餐饮", "咖啡"))
        and text_contains(keyword, ("外摆", "露台", "户外"))
    ):
        return "外摆/户外"
    if text_contains(poi_text, ("公园", "绿地", "广场")):
        return "开放空间"
    if text_contains(poi_text, ("商业街", "步行街", "街区")):
        return "商业街区"
    if text_contains(poi_text, ("宠物店", "宠物洗护", "宠物用品", "宠物")):
        return "宠物服务门店"
    return "待确认"


def build_risk_note(confidence_level: str, space_type: str, keyword: str) -> str:
    notes = []

    if confidence_level == "低":
        notes.append("携宠规则需出发前确认")

    notes.append("高峰期人流较大，建议全程牵引并避开 16:00-18:00")

    if space_type == "室内/商场":
        notes.append("室内区域是否允许携宠需确认")

    if space_type == "外摆/户外" or text_contains(keyword, ("外摆", "露台", "户外")):
        notes.append("建议确认外摆是否开放及是否允许中型犬")

    return "；".join(dict.fromkeys(notes))


def infer_demo_fields(
    pet_friendly_status: str,
    confidence_level: str,
    space_type: str,
) -> Dict[str, str]:
    if pet_friendly_status == "宠物服务相关":
        return {
            "suitable_pet_size": "小型犬/中型犬/猫",
            "crowd_level": "中",
            "pet_stress_level": "低",
            "transaction_action": "电话咨询/到店服务",
            "route_role": "补给/护理节点",
        }

    if space_type in ("开放空间", "商业街区", "外摆/户外"):
        return {
            "suitable_pet_size": "小型犬/中型犬",
            "crowd_level": "高" if space_type == "商业街区" else "中",
            "pet_stress_level": "中",
            "transaction_action": "出发前确认",
            "route_role": "散步/休息节点",
        }

    return {
        "suitable_pet_size": "待确认",
        "crowd_level": "高",
        "pet_stress_level": "中",
        "transaction_action": "出发前确认",
        "route_role": "候选节点",
    }


def collect_pois_for_keyword(ak: str, keyword: str) -> List[Dict]:
    results: List[Dict] = []

    for page_num in range(PAGE_NUMS):
        params = {
            "query": keyword,
            "location": LOCATION,
            "radius": RADIUS,
            "region": CITY,
            "city_limit": "true",
            "output": "json",
            "scope": 2,
            "page_size": PAGE_SIZE,
            "page_num": page_num,
            "ak": ak,
        }

        for attempt in range(1, 4):
            response = requests.get(API_URL, params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()

            message = payload.get("message", "unknown error")
            if payload.get("status") == 0:
                page_results = payload.get("results", [])
                results.extend(page_results)
                if len(page_results) < PAGE_SIZE:
                    return results
                break

            if any(word in message for word in ("并发", "配额", "限制")) and attempt < 3:
                time.sleep(attempt * 2)
                continue

            raise RuntimeError(f"Baidu Place API error for '{keyword}': {message}")

        time.sleep(0.2)

    return results


def normalize_poi(raw_poi: Dict, keyword: str) -> Dict[str, str]:
    name = raw_poi.get("name", "")
    category = raw_poi.get("detail_info", {}).get("tag") or raw_poi.get("tag", "")
    address = raw_poi.get("address", "")
    distance = raw_poi.get("detail_info", {}).get("distance", "")
    location = raw_poi.get("location", {}) or {}
    telephone = raw_poi.get("telephone", "")

    pet_status, confidence, evidence_text = classify_pet_friendly(name, category, keyword)
    space_type = infer_space_type(name, category, keyword)
    demo_fields = infer_demo_fields(pet_status, confidence, space_type)

    row = {
        "poi_name": name,
        "category": category,
        "source_keyword": keyword,
        "address": address,
        "distance": distance,
        "lat": location.get("lat", ""),
        "lng": location.get("lng", ""),
        "telephone": telephone,
        "pet_friendly_status": pet_status,
        "confidence_level": confidence,
        "evidence_source": "百度地图 Place API + 轻量关键词规则",
        "evidence_text": evidence_text,
        "space_type": space_type,
        "risk_note": build_risk_note(confidence, space_type, keyword),
    }
    row.update(demo_fields)

    return row


def main() -> None:
    load_dotenv()
    ak = os.getenv("BAIDU_MAP_AK")

    if not ak:
        raise SystemExit("Missing BAIDU_MAP_AK. Please create a .env file from .env.example.")

    rows = []
    seen = set()

    for keyword in KEYWORDS:
        pois = collect_pois_for_keyword(ak, keyword)
        time.sleep(0.5)
        for poi in pois:
            row = normalize_poi(poi, keyword)
            dedupe_key = (row["poi_name"], row["address"], row["lat"], row["lng"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(row)

    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    shortlist_df = build_shortlist(df)
    shortlist_df.to_csv(SHORTLIST_CSV, index=False, encoding="utf-8-sig")

    print(f"Saved {len(df)} POIs to {OUTPUT_CSV}")
    print(f"Saved {len(shortlist_df)} demo shortlist POIs to {SHORTLIST_CSV}")


if __name__ == "__main__":
    main()
