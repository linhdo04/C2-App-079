"""Analysis tool for agricultural data."""

from typing import Any, cast

from langchain_core.tools import tool


@tool
async def analyze_crop_data(data: dict[str, Any]) -> str:
    """Phân tích dữ liệu mùa vụ và đưa ra khuyến nghị.

    Args:
        data: Dictionary chứa thông tin về:
            - crop_name: Tên cây trồng
            - area: Diện tích (ha)
            - yield_per_ha: Năng suất (tấn/ha)
            - season: Vụ (xuân/hè/thu/đông)

    Returns:
        Chuỗi phân tích và khuyến nghị
    """
    crop = data.get("crop_name", "không xác định")
    area = data.get("area")
    yield_val = data.get("yield_per_ha")
    season = data.get("season", "không xác định")

    missing_fields: list[str] = []
    if not isinstance(area, (int, float)) or isinstance(area, bool) or area <= 0:
        missing_fields.append("diện tích hợp lệ (ha)")
    if (
        not isinstance(yield_val, (int, float))
        or isinstance(yield_val, bool)
        or yield_val <= 0
    ):
        missing_fields.append("năng suất hợp lệ (tấn/ha)")
    if missing_fields:
        return "Chưa đủ dữ liệu để phân tích: cần " + " và ".join(missing_fields) + "."

    valid_area = float(cast(int | float, area))
    valid_yield = float(cast(int | float, yield_val))
    total = valid_area * valid_yield

    analysis = f"""Phân tích dữ liệu canh tác:
- Cây trồng: {crop}
- Vụ: {season}
- Diện tích: {valid_area} ha
- Năng suất: {valid_yield} tấn/ha
- Tổng sản lượng ước tính: {total} tấn

Khuyến nghị:
- {
        "Năng suất cao, tiếp tục duy trì phương pháp canh tác"
        if valid_yield > 5
        else "Năng suất thấp, cần cải thiện kỹ thuật"
    }
"""
    return analysis


__all__ = ["analyze_crop_data"]
