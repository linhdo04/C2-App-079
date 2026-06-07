"""Analysis tool for agricultural data."""

from typing import Any


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
    area = data.get("area", 0)
    yield_val = data.get("yield_per_ha", 0)
    season = data.get("season", "không xác định")

    total = area * yield_val

    analysis = f"""Phân tích dữ liệu canh tác:
- Cây trồng: {crop}
- Vụ: {season}
- Diện tích: {area} ha
- Năng suất: {yield_val} tấn/ha
- Tổng sản lượng ước tính: {total} tấn

Khuyến nghị:
- {
        "Năng suất cao, tiếp tục duy trì phương pháp canh tác"
        if yield_val > 5
        else "Năng suất thấp, cần cải thiện kỹ thuật"
    }
"""
    return analysis


__all__ = ["analyze_crop_data"]
