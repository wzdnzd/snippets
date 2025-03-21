import base64
import random
import string
import time


def get_key(n: int = 32) -> str:
    def random_chars(length: int) -> str:
        length = max(length, 1)
        return "".join(random.sample(string.ascii_lowercase + string.digits, length))

    def get_timestamp() -> int:
        return int(time.time() * 1000)

    prefix = random_chars(length=n)
    timestamp = get_timestamp()

    key = f"{prefix}@{timestamp}"
    return base64.b64encode(key.encode(encoding="utf8")).decode(encoding="utf8")
