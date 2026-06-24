"""Seed test data into the database for UI preview."""

import json
import sys
import os
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.database import Database
from src.data.repository import Repository
from src.utils.csv_parser import parse_file, parse_keyword_file
from config import DB_PATH


def main():
    db = Database(DB_PATH)
    db.initialize()
    repo = Repository(db)

    # 1. Import keywords
    kw_path = os.path.join(os.path.dirname(__file__), "keywords_sample.csv")
    entries, err = parse_keyword_file(kw_path)
    if err:
        print(f"Keywords import error: {err}")
    else:
        for e in entries:
            repo.upsert_keyword(e["keyword"], e["category"], e["weight"])
        print(f"Imported {len(entries)} keywords")

    # 2. Import templates
    tpl_path = os.path.join(os.path.dirname(__file__), "templates_sample.csv")
    from src.core.template_manager import TemplateManager
    tm = TemplateManager(repo)
    imported, skipped, err = tm.import_from_file(tpl_path)
    if err:
        print(f"Templates import error: {err}")
    else:
        print(f"Imported {imported} templates (skipped {skipped})")

    # 3. Seed fake detected posts + reply logs (last 30 days)
    templates = repo.get_all_templates()
    if not templates:
        print("No templates found, skipping reply seed")
        db.close()
        return

    platforms = ["threads", "facebook", "instagram"]
    usernames = ["user_a", "investor_tw", "stock_fan", "newbie123", "etf_lover",
                 "money_talk", "taipei_girl", "save_money", "young_trader", "fintech_guy"]

    now = datetime.now()
    total_replies = 0

    for day_offset in range(30, 0, -1):
        date = now - timedelta(days=day_offset)
        # Random number of replies per day (0~8)
        n_replies = random.randint(0, 8)

        for _ in range(n_replies):
            platform = random.choice(platforms)
            template = random.choice(templates)
            username = random.choice(usernames)
            hour = random.randint(9, 17)
            minute = random.randint(0, 59)
            sent_time = date.replace(hour=hour, minute=minute, second=random.randint(0, 59))
            sent_at = sent_time.strftime("%Y-%m-%d %H:%M:%S")
            detected_at = (sent_time - timedelta(minutes=random.randint(5, 30))).strftime("%Y-%m-%d %H:%M:%S")

            fake_post_id = f"fake_{platform}_{day_offset}_{_}_{random.randint(1000,9999)}"

            # Insert detected post
            db.execute(
                """INSERT OR IGNORE INTO detected_posts
                   (platform, platform_post_id, post_url, author_username, post_content,
                    matched_keywords, relevance_score, recommended_template_id, status, detected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'replied', ?)""",
                (platform, fake_post_id, f"https://example.com/{fake_post_id}",
                 username, f"這是一則關於{template.category}的測試貼文內容",
                 '["測試關鍵字"]', round(random.uniform(3.0, 5.0), 1),
                 template.id, detected_at),
            )
            db.commit()

            # Get the post id
            row = db.execute(
                "SELECT id FROM detected_posts WHERE platform_post_id = ?", (fake_post_id,)
            ).fetchone()
            if not row:
                continue
            post_id = row["id"]

            # Insert reply log
            db.execute(
                """INSERT INTO reply_log
                   (detected_post_id, template_id, platform, reply_content, reply_mode,
                    platform_reply_id, status, retry_count, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'sent', 0, ?)""",
                (post_id, template.id, platform, template.content,
                 random.choice(["semi_auto", "full_auto"]),
                 f"reply_{fake_post_id}", sent_at),
            )
            db.commit()
            total_replies += 1

    print(f"Seeded {total_replies} fake reply logs over 30 days")

    # 4. Seed pending posts for review queue
    pending_contents = [
        ("想開證券戶，不知道哪家比較好？有沒有推薦的券商？", '["證券", "開戶", "券商"]', 4.5),
        ("最近在研究股票，新手入門手續費大概多少啊", '["股票", "新手", "手續費"]', 3.8),
        ("有人用過永豐的豐存股嗎？定期定額好用嗎", '["永豐", "豐存股", "定期定額"]', 5.0),
        ("想問一下現在開戶需要多久？線上可以辦嗎", '["開戶", "線上"]', 4.0),
        ("ETF 定期定額哪家券商手續費最低？", '["ETF", "定期定額", "手續費", "券商"]', 4.2),
        ("剛出社會想學投資，有什麼適合小白的方式嗎", '["投資", "小白"]', 3.2),
        ("比較了幾家券商，手續費差好多欸", '["券商", "手續費"]', 3.5),
        ("朋友推薦我買零股，但不知道怎麼開始", '["零股"]', 3.0),
    ]
    pending_usernames = ["小白兔", "stock_newbie", "投資小菜鳥", "etf_fan_tw", "money_seeker",
                         "taipei_investor", "young_saver", "新手上路"]
    total_pending = 0

    for idx, (content, keywords_json, score) in enumerate(pending_contents):
        platform = random.choice(platforms)
        template = random.choice(templates)
        username = random.choice(pending_usernames)
        detected_at = (now - timedelta(minutes=random.randint(10, 120))).strftime("%Y-%m-%d %H:%M:%S")
        fake_post_id = f"pending_{platform}_{idx}_{random.randint(1000,9999)}"

        db.execute(
            """INSERT OR IGNORE INTO detected_posts
               (platform, platform_post_id, post_url, author_username, post_content,
                matched_keywords, relevance_score, recommended_template_id, status, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (platform, fake_post_id, f"https://example.com/{fake_post_id}",
             username, content, keywords_json, score, template.id, detected_at),
        )
        db.commit()
        total_pending += 1

    print(f"Seeded {total_pending} pending posts for review queue")

    # 5. Seed patrol sessions
    session_data = [
        (8, ["threads", "facebook", "instagram"], 45, 32, 5, 3.5),
        (5, ["threads", "facebook"], 28, 18, 3, 2.0),
        (3, ["threads"], 15, 12, 2, 1.5),
        (2, ["threads", "instagram"], 22, 14, 4, 4.0),
        (1, ["threads", "facebook", "instagram"], 38, 25, 6, 5.5),
    ]
    for day_offset, plats, detected, replied, skipped, hours in session_data:
        start = (now - timedelta(days=day_offset, hours=random.randint(0, 3))).replace(
            hour=9, minute=random.randint(0, 30),
        )
        end = start + timedelta(hours=hours)
        db.execute(
            """INSERT INTO patrol_sessions
               (started_at, stopped_at, platforms, total_detected, total_replied, total_skipped, status)
               VALUES (?, ?, ?, ?, ?, ?, 'stopped')""",
            (start.strftime("%Y-%m-%d %H:%M:%S"),
             end.strftime("%Y-%m-%d %H:%M:%S"),
             json.dumps(plats), detected, replied, skipped),
        )
    db.commit()
    print(f"Seeded {len(session_data)} patrol sessions")

    # 6. Seed some audit logs
    repo.log_audit("SEED_TEST_DATA", {"replies": total_replies, "pending": total_pending})
    print("Done! Restart the app to see the data.")
    db.close()


if __name__ == "__main__":
    main()
