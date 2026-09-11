import streamlit as st
import pandas as pd
import altair as alt
import os
import io
import base64
import requests
from datetime import date

st.set_page_config(page_title="体重记录器", page_icon="📊")
st.title("📊 我的体重记录器")
st.caption("第 4 课作品：输入体重，自动保存，画出趋势图，可删除记录")

CSV_FILE = "weight.csv"
TARGET_FILE = "target_weight.txt"
GITHUB_REPO = "1078111347tm-crypto/weight-tracker"
API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}/contents"

# 判断运行环境：st.secrets 里有 github_token 就走 GitHub API（云端），否则回退到本地文件
github_token = None
try:
    github_token = st.secrets["github_token"]
except Exception:
    github_token = None
USE_GITHUB = github_token is not None
HEADERS = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"} if USE_GITHUB else {}
st.caption(f"数据存储：{'GitHub 仓库（云端）' if USE_GITHUB else '本地文件'}")

# ---- 读写小工具：云端走 GitHub API，本地走磁盘 ----

def read_text_file(path):
    """读取一个文本文件，返回 (内容, sha)。文件不存在时返回 (None, None)。"""
    if USE_GITHUB:
        resp = requests.get(f"{API_BASE}/{path}", headers=HEADERS)
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), None
    return None, None


def write_text_file(path, content, sha=None, message="更新数据"):
    """写入一个文本文件，返回新的 sha。更新已有文件时要把旧 sha 传进去。"""
    if USE_GITHUB:
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        }
        if sha is not None:
            body["sha"] = sha
        resp = requests.put(f"{API_BASE}/{path}", headers=HEADERS, json=body)
        resp.raise_for_status()
        return resp.json()["content"]["sha"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return None


def df_to_csv_text(df):
    """把体重记录表变成 CSV 文本，日期统一存成 YYYY-MM-DD。"""
    save_df = df.copy()
    if "日期" in save_df.columns:
        save_df["日期"] = pd.to_datetime(save_df["日期"], format="mixed").dt.date.astype(str)
    return save_df.to_csv(index=False, lineterminator="\n")


# 读取已有体重数据（云端拉 weight.csv，本地读磁盘）
csv_text, csv_sha = read_text_file(CSV_FILE)
if csv_text and csv_text.strip():
    df = pd.read_csv(io.StringIO(csv_text))
else:
    df = pd.DataFrame(columns=["日期", "体重"])

# 读取已保存的目标体重（文件不存在或内容不对就当作还没设置）
target_text, target_sha = read_text_file(TARGET_FILE)
target_weight = None
if target_text and target_text.strip():
    try:
        target_weight = float(target_text.strip())
    except ValueError:
        target_weight = None

# ---- 目标体重设置 ----
st.subheader("🎯 目标体重")
target_input = st.number_input(
    "目标体重（公斤）",
    min_value=30.0,
    max_value=200.0,
    value=target_weight if target_weight is not None else 70.0,
    step=0.1,
)
if st.button("保存目标"):
    target_sha = write_text_file(TARGET_FILE, str(target_input), sha=target_sha, message="Update target weight")
    st.success(f"目标体重已保存：{target_input} kg")

# ---- 输入区域 ----
st.subheader("记录今天的体重")
weight = st.number_input("体重（公斤）", min_value=30.0, max_value=200.0, value=80.0, step=0.1)
today = st.date_input("日期", value=date.today())

if st.button("保存记录", type="primary"):
    new_row = pd.DataFrame({"日期": [str(today)], "体重": [weight]})
    df = pd.concat([df, new_row], ignore_index=True)
    csv_sha = write_text_file(CSV_FILE, df_to_csv_text(df), sha=csv_sha, message="Add weight record")
    st.success(f"已保存：{today} 体重 {weight} kg")

# ---- 统计 ----
st.subheader("统计")
if len(df) > 0:
    latest = df.iloc[-1]["体重"]
    first = df.iloc[0]["体重"]
    change = latest - first
    st.metric("最新体重", f"{latest} kg", delta=f"{change:+.1f} kg")
    if target_weight is not None:
        diff = latest - target_weight
        if diff > 0:
            st.write(f"距离目标还差 {diff:.1f} kg")
        elif diff < 0:
            st.write(f"已低于目标 {abs(diff):.1f} kg")
        else:
            st.write("🎉 已达到目标体重！")
    else:
        st.info("还没设置目标体重，去页面顶部设置一个吧")
else:
    st.info("还没有记录，先保存一条吧")

# ---- 趋势图 ----
st.subheader("体重趋势")
if len(df) > 1:
    df["日期"] = pd.to_datetime(df["日期"], format="mixed")
    df = df.sort_values("日期")
    chart_df = df[["日期", "体重"]]

    # 体重曲线（蓝色实线，带悬浮提示）
    line = alt.Chart(chart_df).mark_line(color="#2a78d6", strokeWidth=2).encode(
        x=alt.X("日期:T", title="日期"),
        y=alt.Y("体重:Q", axis=alt.Axis(title="体重 (kg)"), scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("日期:T"), alt.Tooltip("体重:Q", format=".1f")],
    )
    chart = line

    # 目标线（红色虚线）+ 线尾直接标注目标值
    if target_weight is not None:
        rule = (
            alt.Chart(pd.DataFrame({"目标体重": [target_weight]}))
            .mark_rule(color="#e34948", strokeWidth=2, strokeDash=[6, 4])
            .encode(y=alt.Y("目标体重:Q", axis=alt.Axis(title="体重 (kg)")))
        )
        label_df = pd.DataFrame({
            "日期": [chart_df["日期"].max()],
            "目标体重": [target_weight],
            "标签": [f"目标 {target_weight:.1f} kg"],
        })
        label = (
            alt.Chart(label_df)
            .mark_text(align="right", dx=-6, dy=-8)
            .encode(x="日期:T", y="目标体重:Q", text="标签:N")
        )
        chart = line + rule + label

    st.altair_chart(chart, width="stretch")
else:
    st.info("再记录一条，就能画出趋势图啦")

# ---- 历史记录（带删除按钮）----
st.subheader("历史记录")
if len(df) == 0:
    st.info("还没有记录")
else:
    # 按日期倒序，并记住每条记录在原始数据里的行号
    display_df = df.sort_values("日期", ascending=False).reset_index()

    for i, row in display_df.iterrows():
        original_idx = row["index"]
        cols = st.columns([3, 2, 1])
        cols[0].write(row["日期"])
        cols[1].write(f"{row['体重']} kg")
        if cols[2].button("🗑️ 删除", key=f"del_{original_idx}"):
            df = df.drop(original_idx)
            df = df.reset_index(drop=True)
            csv_sha = write_text_file(CSV_FILE, df_to_csv_text(df), sha=csv_sha, message="Delete weight record")
            st.rerun()
