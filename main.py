import datetime
import json
import os

class Task:
    def __init__(self, title, description, assignee, due_date, status="ToDo", priority="Medium", created_at=None):
        self.title = title
        self.description = description
        self.status = status
        self.assignee = assignee
        self.due_date = due_date
        # 保存から読み込んだ場合は既存の日時を使い、新規作成なら現在時刻を入れる
        self.created_at = created_at if created_at else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.priority = priority

    def to_dict(self):
        """保存用に辞書形式に変換する"""
        return self.__dict__

    def __str__(self):
        return f"[{self.status}] {self.title} (担当: {self.assignee}, 期限: {self.due_date})"

# データの保存先ファイル名
DATA_FILE = "tasks.json"

def save_tasks(tasks):
    """タスクリストをJSONファイルとして保存する"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        # Taskオブジェクトを辞書のリストに変換して保存
        json_data = [t.to_dict() for t in tasks]
        json.dump(json_data, f, ensure_ascii=False, indent=4)

def load_tasks():
    """JSONファイルからタスクリストを読み込む"""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        # 辞書データからTaskオブジェクトのリストを再構成
        return [Task(**t) for t in data]

# メイン処理
if __name__ == "__main__":
    # 1. 保存されているデータを読み込む
    tasks = load_tasks()
    print(f"--- 現在の登録数: {len(tasks)} 件 ---")

    # 2. 新しいタスクを追加（テスト用）
    if len(tasks) == 0:
        new_task = Task("ログイン画面のUI修正", "背景色を青に変更", "テラゾー", "2026-04-20")
        tasks.append(new_task)
        save_tasks(tasks)
        print("新しいタスクを保存しました。")
    
    # 3. 一覧表示
    for t in tasks:
        print(t)