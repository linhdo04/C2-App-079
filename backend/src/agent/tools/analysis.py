"""Crop analysis production tool."""

import re

from pydantic import BaseModel, Field

from ..react import Tool, ToolContext


class AnalysisInput(BaseModel):
    crop_name: str = "không xác định"
    area: float | None = Field(default=None, gt=0)
    yield_per_ha: float | None = Field(default=None, gt=0)
    season: str = "không xác định"


class AnalysisTool(Tool):
    name = "analysis"
    description = "Estimate crop production from crop, area, yield, and season."
    input_model = AnalysisInput

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = AnalysisInput.model_validate(tool_input)
        if data.area is None or data.yield_per_ha is None:
            return "Chưa đủ dữ liệu: cần diện tích và năng suất hợp lệ."
        total = data.area * data.yield_per_ha
        return (
            f"Cây trồng: {data.crop_name}; vụ: {data.season}; "
            f"diện tích: {data.area} ha; năng suất: {data.yield_per_ha} tấn/ha; "
            f"tổng sản lượng ước tính: {total} tấn."
        )


def extract_crop_input(question: str) -> dict[str, object]:
    normalized = " ".join(question.lower().replace(",", ".").split())
    area_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ha|hecta(?:re)?)\b", normalized)
    yield_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:tấn/ha|tan/ha|tấn trên ha)", normalized
    )
    crop = next(
        (
            name
            for name in ("lúa", "cà phê", "tiêu", "ngô", "sắn", "cao su")
            if name in normalized
        ),
        "không xác định",
    )
    return {
        "crop_name": crop,
        "area": float(area_match.group(1)) if area_match else None,
        "yield_per_ha": float(yield_match.group(1)) if yield_match else None,
        "season": "không xác định",
    }


__all__ = ["AnalysisInput", "AnalysisTool", "extract_crop_input"]
