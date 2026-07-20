"""密码哈希工具

使用 bcrypt 算法对用户密码进行单向哈希。
直接使用 pyca/bcrypt 库以避免 passlib 与 bcrypt 5.x 的兼容性问题。
"""
import bcrypt as _bcrypt


def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希

    Args:
        password: 明文密码

    Returns:
        哈希后的字符串（以 $2b$ 开头的 bcrypt hash）
    """
    return _bcrypt.hashpw(
        password.encode("utf-8"),
        _bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        密码匹配返回 True
    """
    try:
        return _bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False
