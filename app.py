"""Team Task Manager — Web UI (Streamlit). データは main.py と同じ tasks.json を使用します。"""

import datetime

import pandas as pd
import streamlit as st

from main import Task, load_tasks, save_tasks


def persist():
    save_tasks(st.session_state.tasks)


def notify_ui(watchers, message: str):
    if watchers:
        st.toast(f"🔔 宛先: {', '.join(watchers)} — {message}")


st.set_page_config(page_title="Team Task Manager", page_icon="📋", layout="wide")

if "tasks" not in st.session_state:
    st.session_state.tasks = load_tasks()

st.title("📋 Team Task Manager")
st.caption(f"登録タスク数: **{len(st.session_state.tasks)}** 件")

col_reload, _ = st.columns([1, 4])
with col_reload:
    if st.button("JSON から再読み込み"):
        st.session_state.tasks = load_tasks()
        st.rerun()

tab_list, tab_add, tab_edit, tab_search, tab_delete = st.tabs(
    ["一覧", "新規登録", "編集・通知", "検索", "削除"]
)

with tab_list:
    if not st.session_state.tasks:
        st.info("タスクがありません。「新規登録」から追加してください。")
    else:
        rows = []
        for i, t in enumerate(st.session_state.tasks):
            rows.append(
                {
                    "No.": i,
                    "ステータス": t.status,
                    "タイトル": t.title,
                    "担当": t.assignee,
                    "期限": t.due_date,
                    "進捗 %": t.progress,
                    "優先度": t.priority,
                    "ウォッチャー": ", ".join(t.watchers) if t.watchers else "",
                    "更新": t.updated_at,
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab_add:
    st.subheader("新規タスク")
    with st.form("new_task", clear_on_submit=True):
        title = st.text_input("タスク名", placeholder="レポート第3章")
        assignee = st.text_input("担当者")
        due = st.text_input("期限", placeholder="2026-04-20")
        watcher_input = st.text_input(
            "ウォッチャー（通知先）", placeholder="カンマ区切り: 田中, 佐藤"
        )
        submitted = st.form_submit_button("登録")
    if submitted:
        if not title.strip():
            st.error("タスク名を入力してください。")
        else:
            watchers = (
                [w.strip() for w in watcher_input.split(",") if w.strip()]
                if watcher_input
                else []
            )
            st.session_state.tasks.append(
                Task(title.strip(), "", assignee.strip(), due.strip(), watchers=watchers)
            )
            persist()
            st.success("登録しました。")
            st.rerun()

with tab_edit:
    st.subheader("編集・ウォッチ通知")
    if not st.session_state.tasks:
        st.info("編集できるタスクがありません。")
    else:
        labels = [f"{i}: [{t.status}] {t.title}" for i, t in enumerate(st.session_state.tasks)]
        idx = st.selectbox("タスクを選択", range(len(labels)), format_func=lambda i: labels[i])
        t = st.session_state.tasks[idx]
        st.markdown(f"**現在:** {t.title} — 担当 {t.assignee} / 期限 {t.due_date}")

        edit_kind = st.radio(
            "操作",
            ["ステータス変更", "進捗更新", "ウォッチャー追加"],
            horizontal=True,
        )

        if edit_kind == "ステータス変更":
            new_status = st.text_input("新しいステータス", value=t.status)
            if st.button("ステータスを保存"):
                old = t.status
                t.status = new_status.strip() or t.status
                t.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                notify_ui(
                    t.watchers,
                    f"タスク『{t.title}』のステータスが {old} → {t.status} に変更されました。",
                )
                persist()
                st.success("更新しました。")
                st.rerun()

        elif edit_kind == "進捗更新":
            progress = st.slider("進捗率 (%)", 0, 100, int(t.progress))
            if st.button("進捗を保存"):
                t.progress = progress
                t.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                notify_ui(
                    t.watchers,
                    f"タスク『{t.title}』の進捗が {t.progress}% に更新されました。",
                )
                persist()
                st.success("更新しました。")
                st.rerun()

        else:
            new_watcher = st.text_input("追加するウォッチャー名")
            if st.button("ウォッチャーを追加"):
                if not new_watcher.strip():
                    st.warning("名前を入力してください。")
                else:
                    t.watchers.append(new_watcher.strip())
                    t.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    persist()
                    st.success(f"「{new_watcher.strip()}」を通知リストに追加しました。")
                    st.rerun()

with tab_search:
    st.subheader("検索")
    s_kind = st.radio(
        "検索の種類",
        ["担当者名", "ステータス", "キーワード（タイトル・説明）"],
        horizontal=True,
    )
    word = st.text_input("検索ワード")
    if st.button("検索する") and word.strip():
        tasks = st.session_state.tasks
        if s_kind == "担当者名":
            results = [x for x in tasks if word in x.assignee]
        elif s_kind == "ステータス":
            results = [x for x in tasks if word.lower() == x.status.lower()]
        else:
            results = [
                x for x in tasks if word in x.title or word in (x.description or "")
            ]
        st.markdown(f"**検索結果: {len(results)} 件**")
        for r in results:
            st.write(f"[{r.status}] **{r.title}** （担当: {r.assignee}）")
    elif st.button("検索する"):
        st.warning("検索ワードを入力してください。")

with tab_delete:
    st.subheader("タスク削除")
    if not st.session_state.tasks:
        st.info("削除できるタスクがありません。")
    else:
        labels_d = [f"{i}: [{t.status}] {t.title}" for i, t in enumerate(st.session_state.tasks)]
        del_idx = st.selectbox("削除するタスク", range(len(labels_d)), format_func=lambda i: labels_d[i])
        if st.button("このタスクを削除", type="primary"):
            st.session_state.tasks.pop(del_idx)
            persist()
            st.success("削除しました。")
            st.rerun()

st.divider()
st.caption("CLI 版と同じ `tasks.json` を共有します。終了時の明示保存は不要です（操作のたびに保存）。")
