import datetime
import json
import os
import sqlite3

class Task:
    def __init__(self, title, description, assignee, due_date, status="ToDo", 
                 priority="Medium", progress=0, watchers=None, 
                 created_at=None, updated_at=None, **kwargs):
        self.title = title
        self.description = description
        self.status = status
        self.assignee = assignee
        self.due_date = due_date
        self.priority = priority
        self.progress = int(progress)
        self.watchers = watchers if watchers else [] # 通知を受け取る人
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.created_at = created_at if created_at else now
        self.updated_at = updated_at if updated_at else now

    def notify(self, message):
        """ウォッチ通知のシミュレーション"""
        if self.watchers:
            print(f"\n🔔 [通知送信] 宛先: {', '.join(self.watchers)}")
            print(f"   内容: {message}")

    def to_dict(self):
        return self.__dict__

# --- 保存・読み込み ---
DB_FILE = "tasks.db"
LEGACY_DATA_FILE = "tasks.json"


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                assignee TEXT NOT NULL DEFAULT '',
                due_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ToDo',
                priority TEXT NOT NULL DEFAULT 'Medium',
                progress INTEGER NOT NULL DEFAULT 0,
                watchers TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def load_legacy_tasks():
    if not os.path.exists(LEGACY_DATA_FILE):
        return []
    with open(LEGACY_DATA_FILE, "r", encoding="utf-8") as f:
        return [Task(**t) for t in json.load(f)]


def migrate_legacy_json_if_needed():
    init_db()
    with get_connection() as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if row_count > 0:
        return

    legacy_tasks = load_legacy_tasks()
    if legacy_tasks:
        save_tasks(legacy_tasks)


def save_tasks(tasks):
    init_db()
    task_rows = [
        (
            t.title,
            t.description,
            t.assignee,
            t.due_date,
            t.status,
            t.priority,
            int(t.progress),
            json.dumps(t.watchers, ensure_ascii=False),
            t.created_at,
            t.updated_at,
        )
        for t in tasks
    ]

    with get_connection() as conn:
        conn.execute("DELETE FROM tasks")
        conn.executemany(
            """
            INSERT INTO tasks (
                title, description, assignee, due_date, status,
                priority, progress, watchers, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            task_rows,
        )


def load_tasks():
    migrate_legacy_json_if_needed()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                title, description, assignee, due_date, status,
                priority, progress, watchers, created_at, updated_at
            FROM tasks
            ORDER BY id
            """
        ).fetchall()

    tasks = []
    for row in rows:
        tasks.append(
            Task(
                title=row[0],
                description=row[1],
                assignee=row[2],
                due_date=row[3],
                status=row[4],
                priority=row[5],
                progress=row[6],
                watchers=json.loads(row[7]) if row[7] else [],
                created_at=row[8],
                updated_at=row[9],
            )
        )
    return tasks

# --- メイン処理 ---
def main():
    tasks = load_tasks()
    
    while True:
        print(f"\n===== TEAM TASK MANAGER (Total: {len(tasks)}) =====")
        print("1:一覧 / 2:登録 / 3:編集・通知 / 4:高度な検索 / 5:削除 / 6:保存終了")
        choice = input("メニューを選択: ")

        if choice == "1":
            print("\n" + "="*70)
            for i, t in enumerate(tasks):
                print(f"{i}: [{t.status}] {t.title} (担当:{t.assignee} / 期限:{t.due_date} / 進捗:{t.progress}%)")
            print("="*70)

        elif choice == "2":
            print("\n--- 新規登録 ---")
            title = input("タスク名: ")
            assignee = input("担当者: ")
            due = input("期限: ")
            watcher_input = input("ウォッチャー(通知先をカンマ区切りで入力): ")
            watchers = [w.strip() for w in watcher_input.split(",")] if watcher_input else []
            
            tasks.append(Task(title, "", assignee, due, watchers=watchers))
            print(">> 登録しました！")

        elif choice == "3":
            if not tasks: continue
            idx = int(input("編集するタスク番号を選択: "))
            t = tasks[idx]
            print(f"\n--- 編集: {t.title} ---")
            print("1:ステータス変更 / 2:進捗更新 / 3:ウォッチャー追加")
            e_choice = input("選択: ")
            
            old_status = t.status
            if e_choice == "1":
                t.status = input("新しいステータス: ")
                t.notify(f"タスク『{t.title}』のステータスが {old_status} -> {t.status} に変更されました。")
            elif e_choice == "2":
                t.progress = int(input("進捗率(0-100): "))
                t.notify(f"タスク『{t.title}』の進捗が {t.progress}% に更新されました。")
            elif e_choice == "3":
                new_watcher = input("追加するウォッチャー名: ")
                t.watchers.append(new_watcher)
                print(f">> {new_watcher} を通知リストに追加しました。")
            
            t.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        elif choice == "4":
            print("\n--- 検索オプション ---")
            print("1:担当者名で検索 / 2:ステータスで検索 / 3:キーワードで検索")
            s_choice = input("選択: ")
            word = input("検索ワード: ")
            
            if s_choice == "1": results = [t for t in tasks if word in t.assignee]
            elif s_choice == "2": results = [t for t in tasks if word.lower() == t.status.lower()]
            else: results = [t for t in tasks if word in t.title or word in t.description]
            
            print(f"\n--- 検索結果 ({len(results)}件) ---")
            for r in results: print(f"[{r.status}] {r.title} (担当:{r.assignee})")

        elif choice == "5":
            idx = int(input("削除する番号: "))
            tasks.pop(idx)
            print(">> 削除しました。")

        elif choice == "6":
            save_tasks(tasks)
            print("保存しました。プログラムを終了します。")
            break
if __name__ == "__main__":
    main()