# Health Check API

## GET /health

Endpoint public dùng cho load balancer và hệ thống giám sát. Endpoint nằm dưới
`API_PREFIX`; với `API_PREFIX=/api`, URL đầy đủ là `GET /api/health`.

Response `200`:

```json
{
  "data": {
    "status": "healthy"
  }
}
```

Health check không yêu cầu Bearer token và được loại khỏi rate limiting.
