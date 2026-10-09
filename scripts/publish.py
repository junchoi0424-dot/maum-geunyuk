#!/usr/bin/env python3
"""posts.json의 다음 미게시 글을 Instagram에 올린다 (Instagram API with Instagram Login).

환경변수
  IG_ACCESS_TOKEN  long-lived 토큰 (graph.instagram.com)
  IMAGE_BASE_URL   이미지 공개 URL 접두사. 예: https://raw.githubusercontent.com/<user>/<repo>/main
  GRAPH_VERSION    기본 v23.0

사용
  python3 scripts/publish.py              다음 글 게시
  python3 scripts/publish.py --dry-run    API 호출 없이 무엇을 올릴지 출력
  python3 scripts/publish.py --id 004     특정 글 게시 (이미 게시된 글은 --force 필요)
  python3 scripts/publish.py --check-urls dry-run + 이미지 URL 접근 확인
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts.json"
PUBLISHED = ROOT / "published.json"
GRAPH = "https://graph.instagram.com/" + os.environ.get("GRAPH_VERSION", "v23.0")


def api(method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"API 오류 {e.code} {method} {path}: {body}")


def wait_finished(container_id, token, timeout=300):
    deadline = time.time() + timeout
    while True:
        st = api("GET", container_id, token, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise SystemExit(f"컨테이너 {container_id} 실패: {st}")
        if time.time() > deadline:
            raise SystemExit(f"컨테이너 {container_id} 대기 시간 초과: {st}")
        time.sleep(5)


def load_published():
    if PUBLISHED.exists():
        return json.loads(PUBLISHED.read_text())
    return []


def build_caption(post):
    tags = " ".join("#" + t for t in post.get("hashtags", []))
    return post["caption"] + ("\n\n" + tags if tags else "")


def image_paths(post):
    return [f"out/{post['id']}/{n}.jpg" for n in range(1, len(post["slides"]) + 1)]


def pick(posts, published, want_id, force):
    done = {p["id"] for p in published}
    if want_id:
        post = next((p for p in posts if p["id"] == want_id), None)
        if not post:
            raise SystemExit(f"posts.json에 {want_id} 없음")
        if want_id in done and not force:
            raise SystemExit(f"{want_id}는 이미 게시됨 (--force로 재게시)")
        return post
    return next((p for p in posts if p["id"] not in done), None)


def check_url(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-urls", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run or args.check_urls

    posts = json.loads(POSTS.read_text())
    published = load_published()
    post = pick(posts, published, args.id, args.force)
    if not post:
        print("게시할 글이 없습니다. posts.json에 새 원고를 추가하세요.")
        return

    files = image_paths(post)
    missing = [f for f in files if not (ROOT / f).exists()]
    if missing:
        raise SystemExit(f"이미지 없음: {missing} → node scripts/render.mjs {post['id']}")

    base = os.environ.get("IMAGE_BASE_URL", "").rstrip("/")
    if not base and not dry:
        raise SystemExit("IMAGE_BASE_URL 환경변수가 필요합니다")
    urls = [f"{base or '<IMAGE_BASE_URL>'}/{f}" for f in files]
    caption = build_caption(post)

    if dry:
        print(f"[dry-run] {post['id']} · {len(urls)}장 · {'CAROUSEL' if len(urls) > 1 else 'IMAGE'}")
        for u in urls:
            if args.check_urls and base:
                status, ctype = check_url(u)
                print(f"  {status} {ctype} {u}")
            else:
                print(f"  {u}")
        print("--- caption ---\n" + caption)
        return

    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        raise SystemExit("IG_ACCESS_TOKEN 환경변수가 필요합니다")

    me = api("GET", "me", token, fields="user_id,username")
    ig_id = me["user_id"]
    print(f"계정 @{me.get('username')} ({ig_id}) · 글 {post['id']} · {len(urls)}장")

    if len(urls) == 1:
        creation = api("POST", f"{ig_id}/media", token, image_url=urls[0], caption=caption)["id"]
    else:
        children = []
        for u in urls:
            cid = api("POST", f"{ig_id}/media", token, image_url=u, is_carousel_item="true")["id"]
            children.append(cid)
            print(f"  슬라이드 컨테이너 {cid}")
        for cid in children:
            wait_finished(cid, token)
        creation = api(
            "POST", f"{ig_id}/media", token,
            media_type="CAROUSEL", children=",".join(children), caption=caption,
        )["id"]
    wait_finished(creation, token)
    media_id = api("POST", f"{ig_id}/media_publish", token, creation_id=creation)["id"]
    print(f"게시 완료: media {media_id}")

    published.append({
        "id": post["id"],
        "media_id": media_id,
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    PUBLISHED.write_text(json.dumps(published, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
