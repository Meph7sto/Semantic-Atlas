"""
FastAPI 认证与错误语义测试。
"""

import pytest

from backend_business.main import app
from backend_business.services.auth_service import get_auth_service


@pytest.fixture
async def client():
    async with async_client(app) as c:
        yield c


async def test_health_check(client):
    """测试健康检查接口"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "business_backend_ok"
    assert "inference_url" in data
    assert "classification_url" in data


async def test_missing_auth_header(client):
    """测试缺少认证 header 时的错误响应"""
    response = await client.get("/api/v2/auth/verify")
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "未提供认证 Token"


async def test_invalid_token(client):
    """测试无效 Token 时的错误响应"""
    response = await client.get(
        "/api/v2/auth/verify",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Token 无效或已过期"


async def test_auth_service_verify_token():
    """测试 auth_service 的 token 验证功能"""
    auth_service = get_auth_service()

    # 生成一个测试 token
    token = auth_service.generate_token(
        user_id="test-user-123",
        username="test",
        role="member",
        external_type=None
    )

    # 验证 token
    payload = auth_service.verify_token(token)
    assert payload is not None
    assert payload["user_id"] == "test-user-123"
    assert payload["username"] == "test"
    assert payload["role"] == "member"


async def test_auth_service_verify_invalid_token():
    """测试无效 token 验证"""
    auth_service = get_auth_service()

    # 验证无效 token
    payload = auth_service.verify_token("invalid_token")
    assert payload is None


async def test_sse_format():
    """测试 SSE 事件格式化"""
    from backend_business.api.http.sse import format_sse_event

    result = format_sse_event("message", {"text": "测试"})
    assert result == "event: message\ndata: {\"text\": \"测试\"}\n\n"


async def test_error_response():
    """测试错误响应格式"""
    from backend_business.api.http.errors import error_response, ErrorResponse

    response_dict = error_response("参数错误", 400)
    assert response_dict == {"detail": "参数错误"}

    # 测试 ErrorResponse 异常
    exc = ErrorResponse("测试错误", 403)
    assert exc.message == "测试错误"
    assert exc.status_code == 403


async def test_create_success_response():
    """测试成功响应格式"""
    from backend_business.api.http.errors import create_success_response

    response_dict = create_success_response({"user_id": "123"})
    assert response_dict == {"user_id": "123"}
