"""安全认证模块 —— JWT 令牌、密码哈希、OAuth2 依赖注入。

第二阶段接入真实用户系统时，需补充:
  - pip install python-jose[cryptography] passlib[bcrypt]
  - 替换 create_access_token / verify_token 中的占位实现
  - 替换 hash_password / verify_password 中的占位实现
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


# ---------- JWT ----------

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """生成 JWT 访问令牌（当前为占位实现）。

    TODO: 安装 python-jose 后替换为:
        from jose import jwt
        payload = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
        payload.update({"exp": expire})
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=30)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {**data, "exp": expire.isoformat()}
    # 占位：真实环境务必替换为 JWT 签名
    return f"placeholder_token::{payload}"


def verify_token(token: str) -> dict:
    """验证 JWT 令牌并返回 payload（当前为占位实现）。

    TODO: 安装 python-jose 后替换为:
        from jose import jwt, JWTError
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    """
    if not token or not token.startswith("placeholder_token::"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 占位：真实环境务必替换为 JWT 解码
    return {"sub": "placeholder_user"}


# ---------- 密码 ----------

def hash_password(password: str) -> str:
    """对明文密码做哈希（当前为占位实现）。

    TODO: 安装 passlib 后替换为:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
    """
    import hashlib

    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配（当前为占位实现）。

    TODO: 安装 passlib 后替换为:
        return pwd_context.verify(plain_password, hashed_password)
    """
    import hashlib

    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password


# ---------- 当前用户依赖 ----------

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """从请求中解析当前登录用户信息。

    在路由中使用: current_user: dict = Depends(get_current_user)
    """
    payload = verify_token(token)
    return payload
