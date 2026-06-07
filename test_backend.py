import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import api_server
from api_server import app


def assert_no_coffee(payload: dict) -> None:
    route_text = payload["route"]["route_name"] + payload["route"].get("summary", "")
    assert "咖啡" not in route_text
    assert "咖啡" not in "".join(item["route_name"] for item in payload["route_comparisons"])
    for stop in payload["route"]["stops"]:
        assert "咖啡" not in stop["poi"]["name"]


def main() -> None:
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    readiness = client.get("/api/demo-readiness")
    assert readiness.status_code == 200
    readiness_payload = readiness.json()
    assert readiness_payload["ok"] is True
    assert readiness_payload["poi_count"] >= 20
    assert "structured_evidence_system" in readiness_payload["backend_capabilities"]
    assert "multi_district_area_api" in readiness_payload["backend_capabilities"]

    areas_response = client.get("/api/areas")
    assert areas_response.status_code == 200
    areas_payload = areas_response.json()
    area_ids = {area["area_id"] for area in areas_payload["areas"]}
    assert {"xinjiekou", "gulou", "qinhuai", "xuanwu"}.issubset(area_ids)
    print("OK multi-area API: xinjiekou/gulou/qinhuai/xuanwu available")

    xuanwu_response = client.post(
        "/api/plan-route",
        json={"user_message": "我在玄武区，带中型犬散步，不想消费", "use_llm": False, "use_live_data": False, "area_id": "xuanwu"},
    )
    assert xuanwu_response.status_code == 200
    xuanwu_payload = xuanwu_response.json()
    assert xuanwu_payload["selected_area"]["area_id"] == "xuanwu"
    assert xuanwu_payload["route_origin"]["name"] == "玄武区"
    assert "玄武" in xuanwu_payload["route"]["route_name"]
    print("OK area-aware planning: xuanwu origin and route naming")

    cases = [
        (
            "我在南京新街口，带中型犬出门2.5小时，想喝咖啡，不想太挤，预算100",
            "low_stress",
        ),
        (
            "如果下雨怎么办，最好室内一点，预算100",
            "rainy_day",
        ),
        (
            "我预算只有60，想短时散步和咖啡",
            "budget_saver",
        ),
        (
            "我预算只有30，想短时散步和咖啡",
            "quick_walk",
        ),
        (
            "我在南京新街口，想给狗洗护补给，预算120",
            "service_supply",
        ),
    ]

    for message, expected_route_type in cases:
        response = client.post(
            "/api/plan-route",
            json={"user_message": message, "use_llm": False},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["selected_route_type"] == expected_route_type
        assert payload["parsed_input"]["location"]
        assert payload["route_origin"]["lat"]
        assert payload["route_origin"]["lng"]
        assert payload["route_origin"]["source"] in {"parsed_user_location", "fallback_demo_origin"}
        assert payload["route"]["stops"]
        assert payload["commercial_actions"]
        assert payload["feasibility"]["score"] > 0
        assert payload["risk_radar"]
        assert 3 <= len(payload["route_comparisons"]) <= 4
        assert payload["route_comparisons"][0]["route_type"] == expected_route_type
        assert len(payload["route_comparisons"][0]["preview_points"]) >= 2
        assert payload["route_comparisons"][0]["preview_points"][0]["role"] == "集合点"
        assert payload["route_comparisons"][0]["preview_points"][-1]["role"] == "返程点"
        assert payload["route_endpoint"]["role"] == "返程点"
        assert payload["community_modules"]["forum"]["posts"]
        assert payload["community_modules"]["dog_walking_service"]["cta"]
        assert payload["decision_trace"]["stop_selection"]
        first_stop = payload["route"]["stops"][0]
        assert first_stop["pet_access_policy"]["access_type"]
        assert first_stop["pet_access_policy"]["verification_status"]
        assert first_stop["pet_access_policy"]["confirmation_question"]
        assert first_stop["pet_access_policy"]["commerce_readiness"]
        assert payload["candidate_pool_summary"]["selection_mode"] == "dynamic_ranked_pool"
        assert "dynamic_poi_scoring" in payload["backend_capabilities"]
        assert payload["pet_label_summary"]["evidence_system"]["version"]
        assert payload["pet_label_summary"]["evidence_system"]["source_layers"]
        first_policy_card = payload["pet_label_summary"]["policy_cards"][0]
        assert first_policy_card["evidence_items"]
        assert first_policy_card["evidence_gaps"]
        assert first_policy_card["access_policy"]["access_type"]
        assert first_policy_card["review_status"] in {"verified", "review_recommended", "manual_review_required", "candidate_pool"}
        print(
            f"OK {expected_route_type}: "
            f"{payload['route']['route_name']} / "
            f"{payload['route']['estimated_budget']} / "
            f"{len(payload['route']['stops'])} stops"
        )

    budget_response = client.post(
        "/api/plan-route",
        json={"user_message": "我预算只有60，想短时散步和咖啡", "use_llm": False},
    )
    budget_payload = budget_response.json()
    assert budget_payload["selected_route_type"] == "budget_saver"
    assert budget_payload["route"]["estimated_budget"] == "20-60元"
    assert all(stop["role"] != "宠物服务/补给点" for stop in budget_payload["route"]["stops"])
    print("OK budget constraint: recommendation stays within 60 yuan and removes service stops")

    origin_response = client.post(
        "/api/plan-route",
        json={"user_message": "我在德基，带中型犬出门2.5小时，想喝咖啡，预算100", "use_llm": False},
    )
    origin_payload = origin_response.json()
    assert origin_payload["route_origin"]["name"] == "德基广场"
    assert origin_payload["route_origin"]["source"] == "parsed_user_location"
    print("OK route origin: map starts from parsed user location")

    park_response = client.post(
        "/api/plan-route",
        json={
            "user_message": "我现在在南京新街口，想带一只大型犬去公园散散步，不想去什么咖啡店",
            "use_llm": False,
        },
    )
    park_payload = park_response.json()
    assert park_payload["selected_route_type"] == "quick_walk"
    assert "公园/绿地活动" in park_payload["parsed_input"]["preferences"]
    assert "咖啡店" in park_payload["parsed_input"]["avoid"]
    assert "咖啡" not in park_payload["parsed_input"]["commercial_intent"]
    assert all(stop["role"] == "短时活动空间" for stop in park_payload["route"]["stops"])
    assert park_payload["route"]["estimated_budget"] == "0元"
    assert_no_coffee(park_payload)
    print("OK negation intent: coffee avoided and park/activity route kept")

    eating_response = client.post(
        "/api/plan-route",
        json={"user_message": "我在南京新街口，带中型犬出门2.5小时，想吃饭，预算100", "use_llm": False},
    )
    eating_payload = eating_response.json()
    assert any("餐" in stop["poi"]["category"] or "菜馆" in stop["poi"]["name"] for stop in eating_payload["route"]["stops"])
    print("OK dining intent: restaurant-like POI selected")

    migration_scenarios = [
        (
            "park_only",
            {"user_message": "我在玄武区，只想带狗去公园散步，不想消费，不要咖啡", "use_llm": False, "use_live_data": False, "area_id": "xuanwu"},
            lambda payload: payload["selected_route_type"] == "quick_walk"
            and all(stop["role"] == "短时活动空间" for stop in payload["route"]["stops"])
            and not any("咖啡" in stop["poi"]["name"] for stop in payload["route"]["stops"]),
        ),
        (
            "budget_30",
            {"user_message": "我在秦淮区，预算只有30，想带狗短暂散步", "use_llm": False, "use_live_data": False, "area_id": "qinhuai"},
            lambda payload: payload["route"]["estimated_budget"] == "0元"
            and all(stop["role"] == "短时活动空间" for stop in payload["route"]["stops"]),
        ),
        (
            "rainy_day",
            {"user_message": "我在鼓楼区，下雨了，想找雨天备选点", "use_llm": False, "use_live_data": False, "area_id": "gulou"},
            lambda payload: payload["selected_route_type"] == "rainy_day"
            and any(stop["role"] == "雨天备选点" for stop in payload["route"]["stops"]),
        ),
        (
            "grooming",
            {"user_message": "我在新街口，想顺路给狗洗护，再买点宠物用品", "use_llm": False, "use_live_data": False, "area_id": "xinjiekou"},
            lambda payload: payload["selected_route_type"] == "service_supply"
            and any(stop["role"] == "宠物服务/补给点" for stop in payload["route"]["stops"]),
        ),
    ]

    for name, request_body, predicate in migration_scenarios:
        scenario_response = client.post("/api/plan-route", json=request_body)
        assert scenario_response.status_code == 200
        scenario_payload = scenario_response.json()
        assert predicate(scenario_payload)
        assert scenario_payload["candidate_pool_summary"]["groups"]
        print(f"OK migration scenario: {name}")

    with tempfile.TemporaryDirectory() as tmpdir:
        original_feedback_path = api_server.FEEDBACK_PATH
        api_server.FEEDBACK_PATH = Path(tmpdir) / "user_feedback.json"
        try:
            baseline = client.post(
                "/api/plan-route",
                json={"user_message": "我在南京新街口，带中型犬出门2.5小时，想喝咖啡，预算100", "use_llm": False},
            ).json()
            target_stop = baseline["route"]["stops"][0]
            target_poi = target_stop["poi"]

            feedback_response = client.post(
                "/api/poi-feedback",
                json={
                    "poi_id": target_poi["poi_id"],
                    "poi_name": target_poi["name"],
                    "vote": "可以带狗",
                    "note": "周末下午到店，店员确认牵引即可。",
                    "source": "test_user",
                },
            )
            assert feedback_response.status_code == 200
            feedback_payload = feedback_response.json()
            assert feedback_payload["ok"] is True
            assert feedback_payload["summary"]["positive"] == 1
            assert os.path.exists(api_server.FEEDBACK_PATH)

            updated = client.post(
                "/api/plan-route",
                json={"user_message": "我在南京新街口，带中型犬出门2.5小时，想喝咖啡，预算100", "use_llm": False},
            ).json()
            target_cards = [
                card
                for card in updated["pet_label_summary"]["policy_cards"]
                if card["poi_name"] == target_poi["name"]
            ]
            assert target_cards
            assert target_cards[0]["layer"] == "L2"
            assert target_cards[0]["user_feedback"]["positive"] == 1
            assert "近期用户验证" in target_cards[0]["basis"]
            assert any(item["source_type"] == "user_feedback" for item in target_cards[0]["evidence_items"])
            assert target_cards[0]["review_status"] == "review_recommended"
            print("OK feedback loop: POI feedback persists and upgrades label evidence")

            coffee_baseline = client.post(
                "/api/plan-route",
                json={"user_message": "我在南京新街口，带中型犬出门2.5小时，想喝咖啡，预算100", "use_llm": False},
            ).json()
            consumption_stop = next(
                stop for stop in coffee_baseline["route"]["stops"] if stop["role"] == "宠物友好消费点"
            )
            blocked_poi = consumption_stop["poi"]
            negative_response = client.post(
                "/api/poi-feedback",
                json={
                    "poi_id": blocked_poi["poi_id"],
                    "poi_name": blocked_poi["name"],
                    "vote": "不可带宠",
                    "note": "到店后店员明确说不接待带宠。",
                    "source": "test_user",
                },
            )
            assert negative_response.status_code == 200

            reranked = client.post(
                "/api/plan-route",
                json={"user_message": "我在南京新街口，带中型犬出门2.5小时，想喝咖啡，预算100", "use_llm": False},
            ).json()
            reranked_ids = {stop["poi"]["poi_id"] for stop in reranked["route"]["stops"]}
            assert blocked_poi["poi_id"] not in reranked_ids
            assert any(
                item["difference_from_selected"] and item["tradeoff_summary"]
                for item in reranked["route_comparisons"]
                if not item["selected"]
            )
            assert "feedback_aware_ranking" in reranked["backend_capabilities"]
            print("OK feedback-aware ranking: negative feedback removes POI and route comparisons explain tradeoffs")
        finally:
            api_server.FEEDBACK_PATH = original_feedback_path


if __name__ == "__main__":
    main()
