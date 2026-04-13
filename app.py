import datetime
import sqlite3
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection
from urllib.parse import quote, urlparse
import gspread
from google.oauth2.service_account import Credentials

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="Team Task Manager", page_icon="📋", layout="wide")

LOCAL_DB_FILE = "tasks.db"

def get_gsheets_connection():
    """接続失敗時は None を返してフォールバック可能にする。"""
    try:
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception:
        return None

def get_spreadsheet_ref():
    """secrets の spreadsheet を URL/ID どちらでも使える形に正規化する"""
    raw = str(st.secrets["connections"]["gsheets"]["spreadsheet"]).strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parts = [p for p in urlparse(raw).path.split("/") if p]
        if "d" in parts:
            idx = parts.index("d")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return raw

def get_worksheet_name():
    """接続設定に worksheet があれば使用。無ければ既定値 tasks。"""
    try:
        ws = str(st.secrets["connections"]["gsheets"].get("worksheet", "tasks")).strip()
        return ws or "tasks"
    except Exception:
        return "tasks"

def get_service_account_email() -> str:
    try:
        return str(st.secrets["connections"]["gsheets"].get("client_email", "")).strip()
    except Exception:
        return ""

def get_service_account_dict() -> dict:
    try:
        return dict(st.secrets["connections"]["gsheets"])
    except Exception:
        return {}

def read_tasks_with_gspread(spreadsheet: str, worksheet: str) -> pd.DataFrame:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(get_service_account_dict(), scopes=scopes)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(spreadsheet).worksheet(worksheet)
    rows = ws.get_all_records()
    return normalize_task_columns(pd.DataFrame(rows))

def write_tasks_with_gspread(spreadsheet: str, worksheet: str, df: pd.DataFrame) -> None:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(get_service_account_dict(), scopes=scopes)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(spreadsheet).worksheet(worksheet)
    safe_df = normalize_task_columns(df.copy())
    values = [safe_df.columns.tolist()] + safe_df.astype(str).values.tolist()
    ws.clear()
    ws.update(values)

def normalize_task_columns(df: pd.DataFrame) -> pd.DataFrame:
    """シート列名の揺れを吸収し、アプリ期待列を保証する。"""
    if df is None:
        df = pd.DataFrame()

    rename_map = {
        "assigness": "assignee",
        "assignees": "assignee",
        "due_data": "due_date",
        "duedate": "due_date",
        "watcher": "watchers",
    }
    existing_map = {c: rename_map[c] for c in df.columns if c in rename_map}
    if existing_map:
        df = df.rename(columns=existing_map)

    required_cols = ["title", "status", "assignee", "due_date", "progress", "watchers"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = "" if col != "progress" else 0
    return df[required_cols]

def load_tasks_local() -> pd.DataFrame:
    """ローカルSQLiteからタスクを読む。"""
    try:
        with sqlite3.connect(LOCAL_DB_FILE) as con:
            table_exists = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchone()
            if not table_exists:
                return pd.DataFrame(columns=["title", "status", "assignee", "due_date", "progress", "watchers"])

            columns = [row[1] for row in con.execute("PRAGMA table_info(tasks)").fetchall()]
            select_parts = [
                "title" if "title" in columns else "'' AS title",
                "status" if "status" in columns else "'' AS status",
                "assignee" if "assignee" in columns else "'' AS assignee",
                "due_date" if "due_date" in columns else "'' AS due_date",
                "progress" if "progress" in columns else "0 AS progress",
                "watchers" if "watchers" in columns else "'' AS watchers",
            ]
            query = f"SELECT {', '.join(select_parts)} FROM tasks ORDER BY id"
            return normalize_task_columns(pd.read_sql_query(query, con))
    except Exception:
        return pd.DataFrame(columns=["title", "status", "assignee", "due_date", "progress", "watchers"])

def save_tasks_local(df: pd.DataFrame) -> None:
    """ローカルSQLiteへ全件保存する。"""
    safe_df = normalize_task_columns(df.copy())
    with sqlite3.connect(LOCAL_DB_FILE) as con:
        con.execute(
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
        con.execute("DELETE FROM tasks")
        columns = [row[1] for row in con.execute("PRAGMA table_info(tasks)").fetchall()]
        insert_columns = [c for c in [
            "title", "description", "assignee", "due_date", "status",
            "priority", "progress", "watchers", "created_at", "updated_at"
        ] if c in columns]
        placeholders = ", ".join(["?"] * len(insert_columns))
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        rows = []
        for _, r in safe_df.iterrows():
            base = {
                "title": str(r["title"]),
                "description": "",
                "assignee": str(r["assignee"]),
                "due_date": str(r["due_date"]),
                "status": str(r["status"]),
                "priority": "Medium",
                "progress": int(r["progress"]) if str(r["progress"]).strip() else 0,
                "watchers": str(r["watchers"]),
                "created_at": now,
                "updated_at": now,
            }
            rows.append(tuple(base[c] for c in insert_columns))

        con.executemany(
            f"INSERT INTO tasks ({', '.join(insert_columns)}) VALUES ({placeholders})",
            rows,
        )
        con.commit()

def load_tasks_public_csv(spreadsheet_id: str, worksheet: str) -> pd.DataFrame:
    """公開シートをCSVエンドポイント経由で読む。"""
    encoded_sheet = quote(worksheet)
    public_csv_url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={encoded_sheet}"
    )
    return normalize_task_columns(pd.read_csv(public_csv_url))

# --- 2. 認証・ログイン機能 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.title("🔒 Team Task Manager")
    st.info("アクセスにはパスワードが必要です。")
    
    with st.form("login_form"):
        # secrets.toml の [auth] password を参照
        try:
            correct_password = str(st.secrets["auth"]["password"]).strip()
        except Exception:
            st.error("secrets.toml の [auth] 設定を読み込めません。書式を確認してください。")
            return False
        pwd_input = st.text_input("パスワードを入力してください", type="password")
        
        if st.form_submit_button("ログイン"):
            if pwd_input.strip() == correct_password:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("パスワードが正しくありません。")
    return False

if not check_password():
    st.stop()

# --- 3. データ操作関数 ---
def load_tasks():
    """スプレッドシートから最新のDataFrameを読み込む"""
    conn = get_gsheets_connection()
    if conn is None:
        st.info("Google Sheets 認証を読み込めないため、ローカルDB(tasks.db)を使用します。")
        return load_tasks_local()

    spreadsheet = get_spreadsheet_ref()
    worksheet = get_worksheet_name()
    try:
        return normalize_task_columns(conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl="0s"))
    except Exception:
        try:
            return read_tasks_with_gspread(spreadsheet, worksheet)
        except Exception:
            pass
        # worksheet 名が一致しないケースでは、先頭シートで再試行する
        try:
            return normalize_task_columns(conn.read(spreadsheet=spreadsheet, ttl="0s"))
        except Exception as e:
            msg = str(e)
            if "HTTP Error 400" in msg or "HTTP エラー 400" in msg or "HTTPError" in msg:
                try:
                    return load_tasks_public_csv(spreadsheet, worksheet)
                except Exception as csv_e:
                    csv_msg = str(csv_e)
                    if "404" in csv_msg or "notFound" in csv_msg:
                        st.error("タスクの読み込みに失敗しました。サービスアカウントにこのスプレッドシートの閲覧権限がありません。")
                        st.info("対処: シート共有に service account の client_email を追加し、権限を『編集者』にしてください。")
                        st.caption(
                            f"確認用: spreadsheet={spreadsheet} / service_account={get_service_account_email()}"
                        )
                    else:
                        st.error("タスクの読み込みに失敗しました。スプレッドシートID、公開設定、または許可設定を確認してください。")
                        st.info("対処: 1) spreadsheet に正しいIDを設定 2) シートを『リンクを知っている全員が閲覧可能』にする、またはサービスアカウント権限を設定")
                    st.caption(f"詳細: {csv_e}")
                    return load_tasks_local()
            else:
                st.error(f"タスクの読み込みに失敗しました: {e}")
                return load_tasks_local()
            return pd.DataFrame(columns=["title", "status", "assignee", "due_date", "progress", "watchers"])

def save_tasks(df):
    """DataFrameをスプレッドシートに書き込む"""
    conn = get_gsheets_connection()
    if conn is None:
        save_tasks_local(df)
        st.info("Google Sheets 認証を読み込めないため、ローカルDB(tasks.db)へ保存しました。")
        return

    spreadsheet = get_spreadsheet_ref()
    worksheet = get_worksheet_name()
    try:
        conn.update(spreadsheet=spreadsheet, worksheet=worksheet, data=df)
    except Exception:
        try:
            write_tasks_with_gspread(spreadsheet, worksheet, df)
            return
        except Exception:
            pass
        try:
            conn.update(spreadsheet=spreadsheet, data=df)
        except Exception as e:
            err = str(e)
            if "Public Spreadsheet cannot be written to" in err:
                st.info("公開シートは書き込み不可のため、ローカルDB(tasks.db)へ保存しました。")
            else:
                st.warning(f"Google Sheets に保存できないため、ローカルDBへ切り替えます: {e}")
            try:
                save_tasks_local(df)
            except Exception as local_e:
                st.error(f"ローカルDB保存にも失敗しました: {local_e}")

# --- 4. セッション状態の初期化 ---
if "current_page" not in st.session_state:
    st.session_state.current_page = "一覧"
if "edit_target_idx" not in st.session_state:
    st.session_state.edit_target_idx = 0
if "notifications" not in st.session_state:
    st.session_state.notifications = []

def notify_ui(watchers, message, level="info"):
    now = datetime.datetime.now().strftime('%H:%M')
    target = watchers if watchers else "全員"
    full_msg = f"🔔 {target} へ: {message}"
    st.toast(full_msg)
    st.session_state.notifications.append({"time": now, "message": full_msg, "level": level})

# --- 5. サイドバー ---
with st.sidebar:
    st.title("メニュー")
    pages = ["一覧", "新規登録", "編集・通知", "検索", "削除"]
    choice = st.radio("ページを選択", pages, index=pages.index(st.session_state.current_page))
    st.session_state.current_page = choice

    st.divider()
    st.header("📜 通知ログ")
    if st.session_state.notifications:
        for log in reversed(st.session_state.notifications):
            line = f"[{log['time']}] {log['message']}"
            if log['level'] == "delete": st.error(line)
            elif log['level'] == "add": st.success(line)
            else: st.info(line)
        if st.button("ログをクリア"):
            st.session_state.notifications = []
            st.rerun()
    else:
        st.write("新しい通知はありません。")

# --- 6. メイン画面 ---
st.title(f"📋 Team Task Manager - {st.session_state.current_page}")

# 最新データを読み込み
df = load_tasks()

# --- 一覧ページ ---
if st.session_state.current_page == "一覧":
    if df.empty:
        st.info("タスクがありません。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 新規登録ページ ---
elif st.session_state.current_page == "新規登録":
    with st.form("new_task", clear_on_submit=True):
        title = st.text_input("タスク名")
        assignee = st.text_input("担当者")
        due = st.text_input("期限", placeholder="2026-04-20")
        watcher_input = st.text_input("ウォッチャー（カンマ区切り）")
        submitted = st.form_submit_button("登録")
    
    if submitted:
        if not title.strip():
            st.error("タスク名を入力してください。")
        else:
            new_row = pd.DataFrame([{
                "title": title.strip(), "status": "未着手", "assignee": assignee.strip(),
                "due_date": due.strip(), "progress": 0, "watchers": watcher_input.strip()
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_tasks(df)
            notify_ui(watcher_input, f"『{title}』を追加しました", level="add")
            st.success("追加しました。")
            st.rerun()

# --- 編集・通知ページ ---
elif st.session_state.current_page == "編集・通知":
    if df.empty:
        st.info("タスクがありません。")
    else:
        labels = [f"{i}: [{r['status']}] {r['title']}" for i, r in df.iterrows()]
        idx = st.selectbox(
            "タスクを選択", 
            range(len(labels)), 
            index=min(st.session_state.edit_target_idx, len(labels)-1),
            format_func=lambda i: labels[i]
        )
        target = df.iloc[idx]
        
        st.markdown(f"**詳細:** {target['title']} (担当: {target['assignee']})")
        edit_kind = st.radio("操作を選択", ["ステータス変更", "進捗更新"], horizontal=True)

        if edit_kind == "ステータス変更":
            new_status = st.text_input("新しいステータス", value=target["status"])
            if st.button("ステータスを更新"):
                old = target["status"]
                df.at[idx, "status"] = new_status.strip()
                save_tasks(df)
                notify_ui(target["watchers"], f"『{target['title']}』 {old} → {new_status}")
                st.rerun()

        elif edit_kind == "進捗更新":
            progress = st.slider("進捗率 (%)", 0, 100, int(target["progress"]))
            if st.button("進捗を保存"):
                df.at[idx, "progress"] = progress
                save_tasks(df)
                notify_ui(target["watchers"], f"『{target['title']}』 進捗 {progress}%")
                st.rerun()

# --- 検索ページ ---
elif st.session_state.current_page == "検索":
    word = st.text_input("検索ワード（タイトルまたは担当者）")
    if word.strip():
        # 大文字小文字を区別せずに検索
        mask = df["title"].str.contains(word, case=False, na=False) | df["assignee"].str.contains(word, case=False, na=False)
        results = df[mask]
        
        st.write(f"結果: {len(results)} 件")
        for i, r in results.iterrows():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"### {r['title']}")
                st.caption(f"[{r['status']}] 担当: {r['assignee']} / 期限: {r['due_date']}")
            with col2:
                if st.button("編集", key=f"ed_{i}"):
                    st.session_state.edit_target_idx = i
                    st.session_state.current_page = "編集・通知"
                    st.rerun()
            st.divider()

# --- 削除ページ ---
elif st.session_state.current_page == "削除":
    if df.empty:
        st.info("タスクがありません。")
    else:
        labels_d = [f"{i}: [{r['status']}] {r['title']}" for i, r in df.iterrows()]
        del_idx = st.selectbox(
            "削除するタスクを選択", 
            range(len(labels_d)), 
            index=min(st.session_state.edit_target_idx, len(labels_d)-1),
            format_func=lambda i: labels_d[i]
        )
        target = df.iloc[del_idx]
        st.error(f"警告: 『{target['title']}』を完全に削除します。")
        if st.button("削除を実行する", type="primary"):
            t_name = target['title']
            w_list = target['watchers']
            df = df.drop(del_idx)
            save_tasks(df)
            notify_ui(w_list, f"『{t_name}』を削除しました", level="delete")
            st.session_state.edit_target_idx = 0
            st.session_state.current_page = "一覧"
            st.rerun()