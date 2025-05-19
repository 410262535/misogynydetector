from app.database.db import connect_to_db, test_db_connection
from playwright.sync_api import sync_playwright
from nested_lookup import nested_lookup
from parsel import Selector
from typing import Dict
import jmespath
import pymysql
import json
import os


# 將資料儲存到資料庫
def save_to_db(user_data: dict, threads_data: list, replies_data: list):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        user_query = """
            INSERT INTO profiles (username, full_name, bio, followers, url)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(
            user_query, (
                user_data["username"], 
                user_data["full_name"], 
                user_data["bio"], 
                user_data["followers"], 
                user_data["url"]
            )
        )
    except pymysql.MySQLError as e:
        if e.args[0] != 1062:
            raise

    for thread in threads_data:
        try:
            post_query = """
                INSERT INTO posts (username, post_id, post_text, post_url, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """
            cursor.execute(
                post_query, (
                    thread["username"], 
                    thread["code"], 
                    thread["text"], 
                    thread["url"]
                )
            )
        except pymysql.MySQLError as e:
            if e.args[0] != 1062:
                raise

    for reply in replies_data:
        try:
            reply_query = """
                INSERT INTO replies (post_id, username, reply_id, reply_text, reply_url, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """
            cursor.execute(
                reply_query, (
                    reply.get("post_id", reply["code"]),
                    reply["username"], 
                    reply["code"],
                    reply["text"], 
                    reply["url"]
                )
            )
        except pymysql.MySQLError as e:
            if e.args[0] != 1062:
                raise

    conn.commit()
    cursor.close()
    conn.close()


def parse_profile(data: Dict) -> Dict:
    result = jmespath.search(
        """{
        is_private: text_post_app_is_private,
        is_verified: is_verified,
        profile_pic: hd_profile_pic_versions[-1].url,
        username: username,
        full_name: full_name,
        bio: biography,
        bio_links: bio_links[].url,
        followers: follower_count
    }""",
        data,
    )
    result["url"] = f"https://www.threads.net/@{result['username']}"
    return result


def parse_thread(data: Dict) -> Dict:
    result = jmespath.search(
        """{
        text: post.caption.text,
        published_on: post.taken_at,
        id: post.id,
        pk: post.pk,
        code: post.code,
        username: post.user.username,
        user_pic: post.user.profile_pic_url,
        user_verified: post.user.is_verified,
        user_pk: post.user.pk,
        user_id: post.user.id,
        has_audio: post.has_audio,
        reply_count: view_replies_cta_string,
        like_count: post.like_count,
        images: post.carousel_media[].image_versions2.candidates[1].url,
        image_count: post.carousel_media_count,
        videos: post.video_versions[].url
    }""",
        data,
    )
    result["videos"] = list(set(result["videos"] or []))
    if result["reply_count"] and type(result["reply_count"]) != int:
        result["reply_count"] = int(result["reply_count"].split(" ")[0])
    result["url"] = f"https://www.threads.net/@{result['username']}/post/{result['code']}"
    keys_to_keep = ["text", "code", "username", "url"]
    return {k: result[k] for k in keys_to_keep if k in result}




def scrape_profile(username: str) -> dict:
    parsed = {
        "user": {},
        "threads": [],
        "replies": []
    }

    # Proxy 設定
    proxy_server = os.getenv("PROXY_SERVER")
    proxy_username = os.getenv("PROXY_USERNAME")
    proxy_password = os.getenv("PROXY_PASSWORD")

    proxy_config = None
    if proxy_server and proxy_username and proxy_password:
        proxy_config = {
            "server": proxy_server,
            "username": proxy_username,
            "password": proxy_password
        }
        print(f"🔐 使用 Proxy：{proxy_server}")
    else:
        print("🚫 未使用 Proxy")

    with sync_playwright() as pw:
        try:
            print("🧪 啟動 Chromium 瀏覽器")
            # ✅ Proxy 要設在 launch()，不是 new_context()
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox"],
                proxy=proxy_config  # ✅ 正確位置
            )
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            # Profile 主頁
            profile_url = f"https://www.threads.net/@{username}"
            print(f"🌐 訪問個人頁面: {profile_url}")
            page.goto(profile_url, timeout=30000)
            page.wait_for_load_state("networkidle")

            try:
                print("⌛ 等待 Threads 元素出現...")
                page.wait_for_selector("[data-pressable-container=true]", timeout=8000)
                print("✅ 成功找到 Threads 元素")
            except Exception as se:
                html = page.content()
                print(f"❌ Threads 元素載入失敗：{se}")
                print("🔍 HTML 頁面摘要：", html[:1000])
                return {"status": "selector_timeout", "error": str(se), "html": html[:1000]}

            # 解析 JSON 結構
            selector = Selector(page.content())
            hidden_datasets = selector.css('script[type="application/json"][data-sjs]::text').getall()
            for hidden_dataset in hidden_datasets:
                if 'ScheduledServerJS' not in hidden_dataset:
                    continue
                data = json.loads(hidden_dataset)
                if 'follower_count' in hidden_dataset:
                    user_data = nested_lookup('user', data)
                    if user_data:
                        parsed['user'] = parse_profile(user_data[0])
                if 'thread_items' in hidden_dataset:
                    thread_items = nested_lookup('thread_items', data)
                    threads = [parse_thread(t) for thread in thread_items for t in thread]
                    parsed['threads'].extend(threads)

            if not parsed['threads']:
                print(f"⚠️ 使用者 {username} 沒有任何 Threads 貼文。")
                return {"status": "no_posts"}

            # 回覆頁面
            replies_url = f"https://www.threads.net/@{username}/replies"
            print(f"🌐 訪問回覆頁面: {replies_url}")
            try:
                page.goto(replies_url, timeout=30000)
                page.wait_for_selector("[data-pressable-container=true]", timeout=8000)
                selector = Selector(page.content())
                hidden_datasets = selector.css('script[type="application/json"][data-sjs]::text').getall()
                for hidden_dataset in hidden_datasets:
                    if 'ScheduledServerJS' not in hidden_dataset or 'thread_items' not in hidden_dataset:
                        continue
                    data = json.loads(hidden_dataset)
                    thread_items = nested_lookup('thread_items', data)
                    if thread_items:
                        replies = [parse_thread(t) for thread in thread_items for t in thread]
                        own_replies = [r for r in replies if r["username"] == username]
                        for r in own_replies:
                            r['post_id'] = r['code']
                        parsed['replies'].extend(own_replies)
            except Exception as e:
                print(f"⚠️ 回覆頁載入失敗：{e}")

            browser.close()

        except Exception as e:
            print(f"❌ Playwright 啟動或瀏覽器錯誤：{e}")
            return {"status": "browser_failed", "error": str(e)}

    # 寫入資料庫
    save_to_db(parsed["user"], parsed["threads"], parsed["replies"])
    return parsed
