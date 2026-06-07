from langchain_core.tools import tool
from sqlmodel import select

from infrastructure.database.postgres import db_session
from models import UserModel


@tool
async def query_crop_database(query: str) -> str:
    """
    Truy vấn cơ sở dữ liệu nội bộ.

    Hiện tại schema demo chỉ có bảng `user`. Hàm này xử lý một số
    truy vấn đơn giản liên quan đến người dùng và trả về thông tin
    ở dạng chuỗi để LLM có thể sử dụng.

    Lưu ý: Đây là implementation đơn giản. Sau này có thể mở rộng
    bằng text-to-SQL hoặc cơ chế an toàn để dịch NL->SQL.
    """
    ql = (query or "").strip().lower()

    # Trả về danh sách người dùng nếu câu hỏi liên quan đến 'user'/'người dùng'
    if any(
        k in ql for k in ("user", "users", "người dùng", "người-dùng", "email", "tên")
    ):
        async with db_session() as session:
            result = await session.execute(select(UserModel).limit(100))
            users = result.all()
            if not users:
                return "Không tìm thấy bản ghi người dùng trong hệ thống."

            lines = [f"- id={u.id}, name={u.name}, email={u.email}" for u in users]
            return "Danh sách người dùng:\n" + "\n".join(lines)

    # Fallback: trả schema sẵn có để LLM biết dữ liệu nội bộ
    return "Chưa có dữ liệu mùa vụ trong schema này."
