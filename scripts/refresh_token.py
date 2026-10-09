#!/usr/bin/env python3
"""long-lived Instagram 토큰을 갱신해 stdout으로 출력한다 (60일 유효, 발급 24시간 후부터 갱신 가능).

  IG_ACCESS_TOKEN=... python3 scripts/refresh_token.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

token = os.environ.get("IG_ACCESS_TOKEN")
if not token:
    sys.exit("IG_ACCESS_TOKEN 환경변수가 필요합니다")

qs = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": token})
try:
    with urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?{qs}", timeout=60) as r:
        data = json.load(r)
except urllib.error.HTTPError as e:
    sys.exit(f"갱신 실패 {e.code}: {e.read().decode(errors='replace')}")

print(f"갱신 완료, 만료까지 {data.get('expires_in', 0) // 86400}일", file=sys.stderr)
print(data["access_token"])
