# Auth API

Backend dùng JWT Bearer access token cho các API không public. Login cấp thêm
rotating refresh token qua HttpOnly cookie để lấy access token mới mà không cần
gửi lại mật khẩu.

## Public Endpoints

### POST /auth/register

Request:

```json
{
  "name": "Nguyen Van A",
  "email": "user@example.com",
  "password": "password123"
}
```

Response `201` trả user public:

```json
{
  "id": 1,
  "name": "Nguyen Van A",
  "email": "user@example.com"
}
```

Email được trim và lowercase. Email trùng trả `409`.

### POST /auth/login

Request JSON:

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

Response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_expires_in": 2592000
}
```

Response cũng set cookie `refresh_token=<jwt>` với `HttpOnly`,
`SameSite=Lax`, `Path=/auth` và `Max-Age` bằng `refresh_expires_in`.

### POST /auth/token

OAuth2 password form endpoint. Dùng `username` làm email và `password` làm mật
khẩu. Response giống `/auth/login`.

### POST /auth/refresh

Đọc refresh token từ HttpOnly cookie `refresh_token`; request body không được
dùng. Response giống `/auth/login` và `/auth/token` và set refresh cookie mới.
Refresh token là rotating token: mỗi lần refresh thành công sẽ revoke refresh
token cũ trong Redis. Refresh token cũ, hết hạn, sai chữ ký, sai loại token,
hoặc thuộc user đã bị xóa/legacy đều bị từ chối.

## Protected Endpoints

### GET /auth/me

Yêu cầu header:

```text
Authorization: Bearer <access_token>
```

Trả user hiện tại.

### POST /auth/logout

Yêu cầu Bearer access token. Endpoint đọc refresh token từ HttpOnly cookie nếu
có, revoke `jti` của access token và refresh token trong Redis tới khi token hết
hạn, clear refresh cookie, rồi trả `204`.

## Authentication Scope

Các endpoint sau là public:

- `/auth/register`
- `/auth/login`
- `/auth/token`
- `/docs`
- `/redoc`
- `/openapi.json`

Các endpoint còn lại, bao gồm `/` và `/agent/ask`, yêu cầu Bearer token.
