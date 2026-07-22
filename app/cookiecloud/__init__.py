"""CookieCloud control plane (not a Provider).

Upstream attribution:
- https://github.com/easychen/CookieCloud
"""

from app.cookiecloud.client import (
    CookieCloudConfig,
    CookieCloudError,
    CookieCloudImporter,
    decrypt_cookiecloud,
    filter_cookies_for_hosts,
    save_cookie_header,
)

__all__ = [
    "CookieCloudConfig",
    "CookieCloudError",
    "CookieCloudImporter",
    "decrypt_cookiecloud",
    "filter_cookies_for_hosts",
    "save_cookie_header",
]
