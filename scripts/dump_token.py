"""dump_token.py - print the Trae CN / SOLO CN credentials stored on this machine.

Reads (and decrypts) the local Trae client's storage.json, so the same values
can be pasted into the console's "手动填写凭证添加账号" form.

WARNING: the output is a live credential. Do not paste it into chats, tickets
or screenshots.
"""

import json
import sys
from pathlib import Path

# The relay sources live next to this script; make ``src`` importable no matter
# which directory the caller used.
_APP = Path(__file__).resolve().parent / "Trae2api-cn" / "Trae2api-cn-main"
if _APP.is_dir():
    sys.path.insert(0, str(_APP))

from src.trae_decrypt import try_auto_discover


def main() -> int:
    auth, edition = try_auto_discover()
    if not auth:
        print("未找到可用的 Trae 登录态。")
        print("请在 Trae CN 客户端里登录一次，然后再运行本脚本。")
        return 1

    payload = {
        "edition": edition,
        "userId": auth.get("userId") or auth.get("UserID") or "",
        "token": auth.get("token") or "",
        "refreshToken": auth.get("refreshToken") or "",
        "expiredAt": auth.get("expiredAt") or auth.get("TokenExpireAt") or "",
        "refreshExpiredAt": auth.get("refreshExpiredAt") or "",
        "clientId": auth.get("clientID") or auth.get("ClientID") or "",
        "host": auth.get("host") or "",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("把 token 粘到控制台「手动填写凭证添加账号」的 Token 框；")
    print("refreshToken / userId 可选但建议一起填。")
    print("注意：以上是明文凭据，不要发给任何人或截图外传。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
