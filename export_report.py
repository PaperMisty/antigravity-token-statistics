"""
多维度 Token 统计聚合与精美报告生成器
- 支持 Windows 与 WSL2 跨环境数据整合（完全跨机型自适应，无硬编码）
- 支持顶层工具类型切换（Antigravity IDE vs Antigravity CLI vs 全部）
- 支持自定义主题（默认暖黄护眼风格，可选极客暗黑风格）
- 支持 GitHub 风格年度贡献热力图（含年份切换与 Hover 浮层）
- 支持每日走势图（日期范围与模型下拉多选联动、紧凑高度约70%、实时求和统计卡片栏）
- 支持执行完成后自动在系统默认浏览器中打开 HTML 报表
"""

import csv
from datetime import datetime
import json
import os
import sys
import webbrowser
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

# 确保在 Windows 控制台下的 UTF-8 打印兼容
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from token_analyzer import collect_all_data, discover_all_data_dirs


def format_num(n: Union[int, float]) -> str:
    """格式化大数字，添加千分位逗号"""
    if isinstance(n, float):
        return f"{n:,.2f}"
    return f"{n:,}"


def human_tokens(n: int) -> str:
    """人性化大数字展示"""
    if n >= 100_000_000:
        return f"约 {n / 100_000_000:.2f} 亿 Tokens"
    elif n >= 10_000:
        return f"约 {n / 10_000:.1f} 万 Tokens"
    return f"{format_num(n)} Tokens"


def generate_multi_dimensional_stats(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成单套记录的多维度统计数据结构"""
    total_calls = len(records)
    total_input = 0
    total_cached = 0
    total_output = 0
    total_thinking = 0
    total_response = 0
    total_tokens = 0
    total_latency = 0.0
    valid_latency_count = 0

    timestamps = [r["timestamp"] for r in records if r.get("timestamp")]
    min_time = min(timestamps) if timestamps else None
    max_time = max(timestamps) if timestamps else None

    # 1. 模型维度
    model_stats = defaultdict(
        lambda: {
            "model_name": "",
            "model_id": "",
            "calls": 0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
            "total_latency": 0.0,
            "latency_count": 0,
        }
    )

    # 2. 会话维度
    conv_stats = defaultdict(
        lambda: {
            "conv_id": "",
            "db_file": "",
            "env": "windows",
            "client_type": "Antigravity IDE",
            "calls": 0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "total_tokens": 0,
            "models": defaultdict(int),
            "first_time": None,
            "last_time": None,
        }
    )

    # 3. 环境维度 (Windows 本地 vs WSL2:Ubuntu 等)
    env_stats = defaultdict(
        lambda: {
            "env": "",
            "calls": 0,
            "conversations": set(),
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
        }
    )

    # 4. 工具客户端维度 (Antigravity IDE vs Antigravity CLI)
    client_stats = defaultdict(
        lambda: {
            "client_type": "",
            "calls": 0,
            "conversations": set(),
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
        }
    )

    # 5. 时间维度 (按日、按月、按日+模型细分统计)
    daily_stats = defaultdict(
        lambda: {
            "date": "",
            "calls": 0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
        }
    )

    daily_by_model = defaultdict(
        lambda: defaultdict(
            lambda: {
                "calls": 0,
                "input_tokens": 0,
                "cached_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "response_tokens": 0,
                "total_tokens": 0,
            }
        )
    )

    monthly_stats = defaultdict(
        lambda: {
            "month": "",
            "calls": 0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "total_tokens": 0,
        }
    )

    # 6. Prompt Breakdown 细分统计
    prompt_breakdown_stats = {
        "count_with_breakdown": 0,
        "total_system_prompt": 0,
        "total_tools": 0,
        "total_chat_messages": 0,
    }

    for r in records:
        inp = r.get("input_tokens", 0)
        cac = r.get("cached_tokens", 0)
        out = r.get("output_tokens", 0)
        thk = r.get("thinking_tokens", 0)
        rsp = r.get("response_tokens", 0)
        tok = r.get("total_tokens", 0)
        lat = r.get("latency_sec", 0.0) or 0.0
        ts = r.get("timestamp")
        env_val = r.get("env", "windows")
        client_val = r.get("client_type", "Antigravity IDE")

        total_input += inp
        total_cached += cac
        total_output += out
        total_thinking += thk
        total_response += rsp
        total_tokens += tok
        if lat > 0:
            total_latency += lat
            valid_latency_count += 1

        # 环境聚合
        e_dict = env_stats[env_val]
        e_dict["env"] = env_val
        e_dict["calls"] += 1
        e_dict["conversations"].add(r.get("conv_id", ""))
        e_dict["input_tokens"] += inp
        e_dict["cached_tokens"] += cac
        e_dict["output_tokens"] += out
        e_dict["thinking_tokens"] += thk
        e_dict["response_tokens"] += rsp
        e_dict["total_tokens"] += tok

        # 工具客户端聚合
        cl_dict = client_stats[client_val]
        cl_dict["client_type"] = client_val
        cl_dict["calls"] += 1
        cl_dict["conversations"].add(r.get("conv_id", ""))
        cl_dict["input_tokens"] += inp
        cl_dict["cached_tokens"] += cac
        cl_dict["output_tokens"] += out
        cl_dict["thinking_tokens"] += thk
        cl_dict["response_tokens"] += rsp
        cl_dict["total_tokens"] += tok

        # 模型聚合
        m_key = r.get("model_name", "Unknown")
        m_dict = model_stats[m_key]
        m_dict["model_name"] = m_key
        m_dict["model_id"] = r.get("model_id", "")
        m_dict["calls"] += 1
        m_dict["input_tokens"] += inp
        m_dict["cached_tokens"] += cac
        m_dict["output_tokens"] += out
        m_dict["thinking_tokens"] += thk
        m_dict["response_tokens"] += rsp
        m_dict["total_tokens"] += tok
        if lat > 0:
            m_dict["total_latency"] += lat
            m_dict["latency_count"] += 1

        # 会话聚合
        c_key = r.get("conv_id", "")
        c_dict = conv_stats[c_key]
        c_dict["conv_id"] = c_key
        c_dict["db_file"] = r.get("db_file", "")
        c_dict["env"] = env_val
        c_dict["client_type"] = client_val
        c_dict["calls"] += 1
        c_dict["input_tokens"] += inp
        c_dict["cached_tokens"] += cac
        c_dict["output_tokens"] += out
        c_dict["thinking_tokens"] += thk
        c_dict["total_tokens"] += tok
        c_dict["models"][m_key] += 1
        if ts:
            if not c_dict["first_time"] or ts < c_dict["first_time"]:
                c_dict["first_time"] = ts
            if not c_dict["last_time"] or ts > c_dict["last_time"]:
                c_dict["last_time"] = ts

        # 时间维度聚合
        if ts:
            dt = datetime.fromtimestamp(ts)
            day_str = dt.strftime("%Y-%m-%d")
            month_str = dt.strftime("%Y-%m")

            d_dict = daily_stats[day_str]
            d_dict["date"] = day_str
            d_dict["calls"] += 1
            d_dict["input_tokens"] += inp
            d_dict["cached_tokens"] += cac
            d_dict["output_tokens"] += out
            d_dict["thinking_tokens"] += thk
            d_dict["response_tokens"] += rsp
            d_dict["total_tokens"] += tok

            dm_dict = daily_by_model[day_str][m_key]
            dm_dict["calls"] += 1
            dm_dict["input_tokens"] += inp
            dm_dict["cached_tokens"] += cac
            dm_dict["output_tokens"] += out
            dm_dict["thinking_tokens"] += thk
            dm_dict["response_tokens"] += rsp
            dm_dict["total_tokens"] += tok

            mo_dict = monthly_stats[month_str]
            mo_dict["month"] = month_str
            mo_dict["calls"] += 1
            mo_dict["input_tokens"] += inp
            mo_dict["cached_tokens"] += cac
            mo_dict["output_tokens"] += out
            mo_dict["thinking_tokens"] += thk
            mo_dict["total_tokens"] += tok

        # Prompt Breakdown
        pb = r.get("prompt_breakdown")
        if pb and (pb.get("system_prompt_tokens") or pb.get("tools_tokens") or pb.get("chat_messages_tokens")):
            prompt_breakdown_stats["count_with_breakdown"] += 1
            prompt_breakdown_stats["total_system_prompt"] += pb.get("system_prompt_tokens", 0)
            prompt_breakdown_stats["total_tools"] += pb.get("tools_tokens", 0)
            prompt_breakdown_stats["total_chat_messages"] += pb.get("chat_messages_tokens", 0)

    total_full_prompt = total_input + total_cached
    cache_hit_rate = (total_cached / total_full_prompt * 100) if total_full_prompt > 0 else 0.0
    avg_latency = (total_latency / valid_latency_count) if valid_latency_count > 0 else 0.0

    # 格式化环境统计
    env_list = []
    for k, v in env_stats.items():
        v_copy = dict(v)
        v_copy["conv_count"] = len(v["conversations"])
        del v_copy["conversations"]
        env_list.append(v_copy)
    env_list.sort(key=lambda x: x["total_tokens"], reverse=True)

    # 格式化工具客户端统计
    client_list = []
    for k, v in client_stats.items():
        v_copy = dict(v)
        v_copy["conv_count"] = len(v["conversations"])
        del v_copy["conversations"]
        client_list.append(v_copy)
    client_list.sort(key=lambda x: x["total_tokens"], reverse=True)

    # 格式化 daily_by_model 结构
    formatted_daily_model = {}
    for day, m_map in sorted(daily_by_model.items()):
        formatted_daily_model[day] = dict(m_map)

    return {
        "overview": {
            "total_calls": total_calls,
            "total_conversations": len(conv_stats),
            "min_time": datetime.fromtimestamp(min_time).strftime("%Y-%m-%d %H:%M:%S") if min_time else "N/A",
            "max_time": datetime.fromtimestamp(max_time).strftime("%Y-%m-%d %H:%M:%S") if max_time else "N/A",
            "total_input_uncached": total_input,
            "total_cached_read": total_cached,
            "total_full_input": total_full_prompt,
            "cache_hit_rate": cache_hit_rate,
            "total_output": total_output,
            "total_thinking": total_thinking,
            "total_response": total_response,
            "total_tokens": total_tokens,
            "avg_latency": avg_latency,
        },
        "environments": env_list,
        "clients": client_list,
        "models": sorted(model_stats.values(), key=lambda x: x["total_tokens"], reverse=True),
        "conversations": sorted(conv_stats.values(), key=lambda x: x["total_tokens"], reverse=True),
        "daily": sorted(daily_stats.values(), key=lambda x: x["date"]),
        "daily_by_model": formatted_daily_model,
        "monthly": sorted(monthly_stats.values(), key=lambda x: x["month"]),
        "prompt_breakdown": prompt_breakdown_stats,
    }


def render_markdown_report(
    stats: Dict[str, Any],
    scanned_targets: Optional[List[Dict[str, str]]] = None
) -> str:
    """渲染生成结构化 Markdown 报告"""
    ov = stats["overview"]
    pb = stats["prompt_breakdown"]
    envs = stats.get("environments", [])
    clients = stats.get("clients", [])

    md = []
    md.append("# Antigravity Token 多维度使用统计分析报告\n")
    md.append(f"> **统计生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    md.append(f"> **数据统计区间**：`{ov['min_time']}` 至 `{ov['max_time']}`  ")

    # 扫描范围展示
    if scanned_targets:
        md.append("> **数据库扫描覆盖范围**：")
        for st in scanned_targets:
            md.append(f"> - `[{st['env']}]` `{st['path']}`")
        md.append("")
    else:
        md.append("> **数据库扫描范围**：Windows 本地与 WSL2 跨环境全部会话数据库\n")

    md.append("## 一、 总体宏观消耗概览 (Overall Overview)\n")
    md.append("| 指标项 | 统计数值 | 说明 |")
    md.append("| :--- | :--- | :--- |")
    md.append(
        f"| **总会话数量 (Conversations)** | `{format_num(ov['total_conversations'])}` 个 | 包含有效对话记录的数据库 |"
    )
    md.append(f"| **总模型调用次数 (Total Calls)** | `{format_num(ov['total_calls'])}` 次 | LLM 生成响应总轮次 |")
    md.append(
        f"| **累计消耗总 Token (Total Tokens)** | **`{format_num(ov['total_tokens'])}`** ({human_tokens(ov['total_tokens'])}) | 未缓存输入 + 缓存读取 + 输出 |"
    )
    md.append(
        f"| **未缓存输入 Token (Uncached Input)** | `{format_num(ov['total_input_uncached'])}` | 需全额计算的 Prompt Token |"
    )
    md.append(
        f"| **缓存读取 Token (Cache Read)** | `{format_num(ov['total_cached_read'])}` | 命中的上下文缓存 Token（省成本与提速） |"
    )
    md.append(
        f"| **总提示词输入量 (Full Prompt)** | `{format_num(ov['total_full_input'])}` | 逻辑总输入量（未缓存+缓存） |"
    )
    md.append(f"| **上下文缓存命中率 (Cache Hit Rate)** | **`{ov['cache_hit_rate']:.2f}%`** | 缓存占总输入提示词比例 |")
    md.append(f"| **总生成输出 Token (Total Output)** | `{format_num(ov['total_output'])}` | 模型生成的总 Token |")
    md.append(
        f"| ↳ **思维链思考 Token (Thinking)** | `{format_num(ov['total_thinking'])}` | 推理思考消耗的 Token 数量 |"
    )
    md.append(
        f"| ↳ **最终文本输出 Token (Response)** | `{format_num(ov['total_response'])}` | 实际呈现给用户的正文 Token |"
    )
    md.append(f"| **平均单次响应耗时 (Avg Latency)** | `{ov['avg_latency']:.2f} 秒` | 模型接口往返平均耗时 |")
    md.append("\n---\n")

    # 客户端工具分布统计
    if clients:
        md.append("## 二、 工具类型分布统计 (Tool/Client Breakdown)\n")
        md.append("| 工具类型 (Client Type) | 独立会话数 | 模型调用次数 | 未缓存输入 | 缓存命中输入 | 模型输出 Token | 消耗总 Token | 占比 |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for cl in clients:
            pct = (cl["total_tokens"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0.0
            md.append(
                f"| **`{cl['client_type']}`** | {format_num(cl['conv_count'])} 个 | {format_num(cl['calls'])} 次 | "
                f"{format_num(cl['input_tokens'])} | {format_num(cl['cached_tokens'])} | "
                f"{format_num(cl['output_tokens'])} | **{format_num(cl['total_tokens'])}** | `{pct:.2f}%` |"
            )
        md.append("\n---\n")

    # 运行环境分布统计
    if envs:
        md.append("## 三、 运行环境分布统计 (Environment Distribution)\n")
        md.append("| 运行环境 (Environment) | 独立会话数 | 模型调用次数 | 未缓存输入 | 缓存命中输入 | 模型输出 Token | 消耗总 Token | 占比 |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for e in envs:
            pct = (e["total_tokens"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0.0
            md.append(
                f"| **`{e['env']}`** | {format_num(e['conv_count'])} 个 | {format_num(e['calls'])} 次 | "
                f"{format_num(e['input_tokens'])} | {format_num(e['cached_tokens'])} | "
                f"{format_num(e['output_tokens'])} | **{format_num(e['total_tokens'])}** | `{pct:.2f}%` |"
            )
        md.append("\n---\n")

    md.append("## 四、 模型维度统计 (Token Usage by Model)\n")
    md.append(
        "| 模型名称 (Model Name) | 调用次数 | 未缓存输入 | 缓存命中输入 | 输出 Token (思考 / 正文) | 总消耗 Token | 缓存命中率 | 平均耗时 |"
    )
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for m in stats["models"]:
        full_inp = m["input_tokens"] + m["cached_tokens"]
        c_rate = (m["cached_tokens"] / full_inp * 100) if full_inp > 0 else 0.0
        avg_lat = (m["total_latency"] / m["latency_count"]) if m["latency_count"] > 0 else 0.0
        out_detail = f"{format_num(m['output_tokens'])}<br><small>({format_num(m['thinking_tokens'])} 思考 / {format_num(m['response_tokens'])} 正文)</small>"
        md.append(
            f"| **{m['model_name']}**<br>`{m['model_id']}` "
            f"| {format_num(m['calls'])} "
            f"| {format_num(m['input_tokens'])} "
            f"| {format_num(m['cached_tokens'])} "
            f"| {out_detail} "
            f"| **{format_num(m['total_tokens'])}** "
            f"| {c_rate:.1f}% "
            f"| {avg_lat:.2f}s |"
        )
    md.append("\n---\n")

    md.append("## 五、 时间维度统计 (Time Trends)\n")
    md.append("### 1. 月度消耗统计 (Monthly Trend)\n")
    md.append("| 月份 | 调用次数 | 未缓存输入 | 缓存命中读取 | 生成输出 (其中思考) | 月度消耗总 Token |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for mo in stats["monthly"]:
        md.append(
            f"| **{mo['month']}** "
            f"| {format_num(mo['calls'])} "
            f"| {format_num(mo['input_tokens'])} "
            f"| {format_num(mo['cached_tokens'])} "
            f"| {format_num(mo['output_tokens'])} ({format_num(mo['thinking_tokens'])}) "
            f"| **{format_num(mo['total_tokens'])}** |"
        )
    md.append("\n")

    md.append("### 2. 最近 30 天每日消耗走势 (Recent 30 Days Daily Trend)\n")
    md.append("| 日期 | 调用次数 | 未缓存输入 | 缓存命中输入 | 输出 Token | 当日总 Token |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
    recent_daily = stats["daily"][-30:]
    for d in recent_daily:
        md.append(
            f"| {d['date']} "
            f"| {format_num(d['calls'])} "
            f"| {format_num(d['input_tokens'])} "
            f"| {format_num(d['cached_tokens'])} "
            f"| {format_num(d['output_tokens'])} "
            f"| **{format_num(d['total_tokens'])}** |"
        )
    md.append("\n---\n")

    md.append("## 六、 会话维度深度分析 (Top 20 Most Consumed Conversations)\n")
    md.append("| 排名 | 会话 ID | 工具类型 | 运行环境 | 交互轮次 | 主要使用模型 | 起止时间 | 缓存命中率 | 会话消耗总 Token |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :--- | :--- | :---: | :---: |")
    for rank, c in enumerate(stats["conversations"][:20], 1):
        top_model = max(c["models"].items(), key=lambda x: x[1])[0] if c["models"] else "Unknown"
        start_str = datetime.fromtimestamp(c["first_time"]).strftime("%m-%d %H:%M") if c["first_time"] else "N/A"
        end_str = datetime.fromtimestamp(c["last_time"]).strftime("%m-%d %H:%M") if c["last_time"] else "N/A"
        full_inp = c["input_tokens"] + c["cached_tokens"]
        c_rate = (c["cached_tokens"] / full_inp * 100) if full_inp > 0 else 0.0
        env_badge = f"`{c.get('env', 'windows')}`"
        client_badge = f"`{c.get('client_type', 'IDE')}`"
        md.append(
            f"| {rank} "
            f"| `{c['conv_id'][:16]}...` "
            f"| {client_badge} "
            f"| {env_badge} "
            f"| {format_num(c['calls'])} 轮 "
            f"| {top_model} "
            f"| {start_str} ~ {end_str} "
            f"| {c_rate:.1f}% "
            f"| **{format_num(c['total_tokens'])}** |"
        )
    md.append("\n---\n")

    md.append("## 七、 Token 组成结构与 Prompt 细分剖析 (Token Composition & Breakdown)\n")
    if pb["count_with_breakdown"] > 0:
        tot_breakdown = pb["total_system_prompt"] + pb["total_tools"] + pb["total_chat_messages"]
        sp_pct = (pb["total_system_prompt"] / tot_breakdown * 100) if tot_breakdown > 0 else 0
        tl_pct = (pb["total_tools"] / tot_breakdown * 100) if tot_breakdown > 0 else 0
        cm_pct = (pb["total_chat_messages"] / tot_breakdown * 100) if tot_breakdown > 0 else 0
        md.append(f"> 基于包含详细细分指标的 `{format_num(pb['count_with_breakdown'])}` 次请求采样统计：\n")
        md.append("| Prompt 组成模块 | 累计 Token 消耗 | 占比 | 作用与特点 |")
        md.append("| :--- | :---: | :---: | :--- |")
        md.append(
            f"| **系统预设 (System Prompt)** | `{format_num(pb['total_system_prompt'])}` | **{sp_pct:.1f}%** | 包含 Agent 身份、代码规范、上下文规则 |"
        )
        md.append(
            f"| **工具定义 (Tools / MCPs)** | `{format_num(pb['total_tools'])}` | **{tl_pct:.1f}%** | 各种内置文件、终端工具及 MCP 工具的 JSON Schema |"
        )
        md.append(
            f"| **对话历史 (Chat Messages)** | `{format_num(pb['total_chat_messages'])}` | **{cm_pct:.1f}%** | 用户问题、模型中间思考过程与工具调用历史记录 |"
        )
        md.append("\n")

    md.append("### Token 宏观结构占比\n")
    inp_pct = (ov["total_input_uncached"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0
    cac_pct = (ov["total_cached_read"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0
    out_pct = (ov["total_output"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0
    thk_pct = (ov["total_thinking"] / ov["total_output"] * 100) if ov["total_output"] > 0 else 0

    md.append(f"- **未缓存直接输入 (Uncached Input)**：占总 Token 的 **{inp_pct:.1f}%**")
    md.append(f"- **上下文缓存命中 (Cache Read)**：占总 Token 的 **{cac_pct:.1f}%**")
    md.append(f"- **模型生成输出 (Model Output)**：占总 Token 的 **{out_pct:.1f}%**")
    md.append(f"  - 在所有输出中，**思维链深度思考 (Thinking Tokens)** 占比达 **{thk_pct:.1f}%**")
    return "\n".join(md)


def render_html_dashboard(
    stats_by_client: Dict[str, Any],
    scanned_targets: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    生成高度交互式的现代化 HTML 仪表盘：
    - 支持顶层工具客户端切换 (ALL vs Antigravity IDE vs Antigravity CLI)
    - 支持暖黄色与暗黑色调自由切换
    - 类似 GitHub 的年度贡献热力图 (带年份筛选与悬浮 Tooltip)
    - 每日走势图高度缩减至原先 70%，并带日期范围与模型下拉多选联动
    - 动态求和统计卡片栏
    """
    # 序列化各客户端的完整聚合数据
    stats_json_str = json.dumps(stats_by_client, ensure_ascii=False)

    targets_desc = "自适应扫描探测"
    if scanned_targets:
        targets_desc = "覆盖: " + " + ".join(sorted(set(st['env'] for st in scanned_targets)))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity Token 多维度使用统计仪表盘</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        /* ================= 基础重置与主题变量 ================= */
        :root {{
            /* 默认暖黄色调风格 (Warm Amber / Parchment) */
            --bg: #fcf8f0;
            --bg-subtle: #f6efe1;
            --card-bg: #ffffff;
            --card-border: #ede1cb;
            --text-main: #332921;
            --text-muted: #857467;
            --text-sub: #a49386;
            --primary: #d97706;
            --primary-hover: #b45309;
            --accent: #ca8a04;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
            --border: #e6dac3;
            --card-shadow: 0 4px 20px -2px rgba(180, 83, 9, 0.05), 0 2px 6px -1px rgba(0,0,0,0.02);
            --chart-grid: rgba(180, 83, 9, 0.08);
            --chart-tick: #857467;
            --input-bg: #fffdf9;
            --hover-bg: rgba(217, 119, 6, 0.06);
            --badge-bg: rgba(217, 119, 6, 0.12);
            --badge-color: #b45309;
            --filter-bar-bg: #f9f3e5;
            --sum-card-bg: #fdfaf3;
            --sum-border: #eedfc5;

            /* 热力图色阶 (暖黄) */
            --heat-l0: #ede4d4;
            --heat-l1: #fde68a;
            --heat-l2: #f59e0b;
            --heat-l3: #d97706;
            --heat-l4: #92400e;
        }}

        body.theme-dark {{
            /* 可选暗黑风格 (Sleek Dark Slate) */
            --bg: #0b1120;
            --bg-subtle: #111b2e;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-sub: #64748b;
            --primary: #38bdf8;
            --primary-hover: #0284c7;
            --accent: #818cf8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f43f5e;
            --border: #334155;
            --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            --chart-grid: rgba(255, 255, 255, 0.06);
            --chart-tick: #94a3b8;
            --input-bg: #0f172a;
            --hover-bg: rgba(56, 189, 248, 0.08);
            --badge-bg: rgba(56, 189, 248, 0.15);
            --badge-color: #38bdf8;
            --filter-bar-bg: #131d31;
            --sum-card-bg: #162238;
            --sum-border: #293852;

            /* 热力图色阶 (暗黑) */
            --heat-l0: #1e293b;
            --heat-l1: #075985;
            --heat-l2: #0284c7;
            --heat-l3: #38bdf8;
            --heat-l4: #bae6fd;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            padding: 24px;
            line-height: 1.5;
            transition: background-color 0.25s ease, color 0.25s ease;
        }}

        /* Header 头部与主题切换 */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 18px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .header-title-box h1 {{
            font-size: 26px;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .header-title-box p {{
            color: var(--text-muted);
            font-size: 14px;
        }}

        /* 顶层工具切换器 (Client Tabs) */
        .client-tabs-bar {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 22px;
            flex-wrap: wrap;
        }}
        .client-tab {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 8px 16px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            box-shadow: var(--card-shadow);
        }}
        .client-tab:hover {{
            color: var(--text-main);
            border-color: var(--primary);
        }}
        .client-tab.active {{
            background: var(--primary);
            color: #ffffff;
            border-color: var(--primary);
            box-shadow: 0 4px 12px rgba(217, 119, 6, 0.25);
        }}
        body.theme-dark .client-tab.active {{
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.25);
        }}
        .tab-badge {{
            font-size: 11px;
            padding: 1px 7px;
            border-radius: 9999px;
            background: rgba(0, 0, 0, 0.08);
            color: inherit;
        }}
        .client-tab.active .tab-badge {{
            background: rgba(255, 255, 255, 0.25);
            color: #ffffff;
        }}

        /* 主题选择切换胶囊 */
        .theme-switcher {{
            display: flex;
            align-items: center;
            background: var(--bg-subtle);
            border: 1px solid var(--border);
            border-radius: 9999px;
            padding: 4px;
            gap: 4px;
        }}
        .theme-btn {{
            border: none;
            background: transparent;
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            padding: 6px 14px;
            border-radius: 9999px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        }}
        .theme-btn.active {{
            background: var(--card-bg);
            color: var(--primary);
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .theme-btn:hover:not(.active) {{
            color: var(--text-main);
        }}

        /* KPI 指标卡片 */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 18px;
            box-shadow: var(--card-shadow);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
        }}
        .kpi-title {{
            font-size: 13px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
            font-weight: 600;
        }}
        .kpi-value {{
            font-size: 26px;
            font-weight: 700;
            color: var(--primary);
        }}
        .kpi-desc {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        /* 通用卡片容器 */
        .card-container {{
            background-color: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: var(--card-shadow);
        }}
        .card-header-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .card-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* ================= GitHub 风格贡献热力图 ================= */
        .heatmap-card {{
            overflow-x: auto;
        }}
        .heatmap-scroll-wrap {{
            overflow-x: auto;
            padding-bottom: 8px;
        }}
        .heatmap-svg {{
            display: block;
            margin: 0 auto;
        }}
        .heatmap-legend {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 6px;
            margin-top: 12px;
            font-size: 12px;
            color: var(--text-muted);
        }}
        .legend-cell {{
            width: 11px;
            height: 11px;
            border-radius: 2px;
        }}
        .heat-cell {{
            cursor: pointer;
            transition: stroke 0.15s ease, transform 0.15s ease;
        }}
        .heat-cell:hover {{
            stroke: var(--text-main);
            stroke-width: 1.5px;
        }}

        /* 热力图悬浮 Tooltip */
        .heatmap-tooltip {{
            position: absolute;
            display: none;
            background: rgba(30, 24, 18, 0.92);
            color: #ffffff;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.4;
            pointer-events: none;
            z-index: 1000;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(4px);
            white-space: nowrap;
        }}
        body.theme-dark .heatmap-tooltip {{
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid #334155;
        }}

        /* 图表网格 */
        .charts-grid {{
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        @media (max-width: 1100px) {{
            .charts-grid {{ grid-template-columns: 1fr; }}
        }}

        /* 走势图高度缩短至约 70% */
        .daily-chart-wrap {{
            position: relative;
            max-height: 220px;
        }}

        /* 表格样式 */
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            text-align: left;
        }}
        th, td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background-color: var(--bg-subtle);
            color: var(--text-muted);
            font-weight: 600;
        }}
        tr:hover {{
            background-color: var(--hover-bg);
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 12px;
            background: var(--badge-bg);
            color: var(--badge-color);
            font-weight: 600;
        }}
        .badge-wsl {{
            background: rgba(129, 140, 248, 0.18);
            color: var(--accent);
        }}

        /* 筛选工具栏 (Toolbar) */
        .filter-toolbar {{
            background: var(--filter-bar-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 14px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }}
        .filter-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .filter-label {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-muted);
            white-space: nowrap;
        }}

        /* 快捷日期胶囊 */
        .date-pills {{
            display: flex;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 2px;
            gap: 2px;
        }}
        .pill-btn {{
            border: none;
            background: transparent;
            color: var(--text-muted);
            font-size: 12px;
            font-weight: 600;
            padding: 4px 9px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .pill-btn:hover {{
            color: var(--text-main);
        }}
        .pill-btn.active {{
            background: var(--primary);
            color: #ffffff;
        }}

        /* 日期选择 input */
        .date-input-wrap {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .date-input {{
            background: var(--input-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-main);
            padding: 4px 8px;
            font-size: 13px;
            font-family: inherit;
            outline: none;
        }}
        .date-input:focus {{
            border-color: var(--primary);
        }}

        /* 下拉多选模型 (Dropdown Multi-select) */
        .dropdown-select {{
            position: relative;
            display: inline-block;
        }}
        .dropdown-trigger {{
            background: var(--input-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 5px 12px;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-main);
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 170px;
            justify-content: space-between;
            transition: border-color 0.2s ease;
        }}
        .dropdown-trigger:hover {{
            border-color: var(--primary);
        }}
        .dropdown-menu {{
            position: absolute;
            top: calc(100% + 6px);
            right: 0;
            min-width: 250px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.15);
            padding: 8px;
            z-index: 100;
            display: none;
        }}
        .dropdown-menu.open {{
            display: block;
        }}
        .dropdown-actions {{
            display: flex;
            justify-content: space-between;
            padding: 4px 8px 8px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 6px;
        }}
        .action-link {{
            background: none;
            border: none;
            color: var(--primary);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            padding: 2px 4px;
        }}
        .action-link:hover {{
            text-decoration: underline;
        }}
        .dropdown-list {{
            max-height: 200px;
            overflow-y: auto;
        }}
        .dropdown-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 8px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            user-select: none;
            color: var(--text-main);
        }}
        .dropdown-item:hover {{
            background: var(--hover-bg);
        }}
        .dropdown-item input[type="checkbox"] {{
            accent-color: var(--primary);
            cursor: pointer;
        }}

        /* 筛选求和统计卡片栏 (Summary Stats Bar) */
        .summary-stats-bar {{
            background: var(--sum-card-bg);
            border: 1px solid var(--sum-border);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 14px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
        }}
        .sum-item {{
            border-right: 1px solid var(--border);
            padding-right: 10px;
        }}
        .sum-item:last-child {{
            border-right: none;
            padding-right: 0;
        }}
        .sum-label {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 3px;
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .sum-val {{
            font-size: 18px;
            font-weight: 700;
            color: var(--text-main);
            line-height: 1.2;
        }}
        .sum-sub {{
            font-size: 11px;
            color: var(--text-sub);
            margin-top: 2px;
        }}
        .text-primary {{ color: var(--primary); }}
        .text-success {{ color: var(--success); }}
        .text-warning {{ color: var(--warning); }}
        .text-danger {{ color: var(--danger); }}
    </style>
</head>
<body class="theme-warm">
    <!-- Header 头部 -->
    <div class="header">
        <div class="header-title-box">
            <h1>📊 Antigravity Token 多维度使用统计仪表盘</h1>
            <p id="headerSubtitle">跨环境自适应扫描 | {targets_desc}</p>
        </div>
        <!-- 主题切换栏 (默认暖黄色，可选暗黑) -->
        <div class="theme-switcher">
            <button id="themeWarmBtn" class="theme-btn active" onclick="setTheme('warm')">
                <span>☀️ 暖阳米黄 (默认)</span>
            </button>
            <button id="themeDarkBtn" class="theme-btn" onclick="setTheme('dark')">
                <span>🌙 极客暗黑</span>
            </button>
        </div>
    </div>

    <!-- 顶层工具分类切换器 (Client Tabs) -->
    <div class="client-tabs-bar">
        <button id="tabALL" class="client-tab active" onclick="switchClientTab('ALL')">
            <span>🚀 全部工具 (All)</span>
            <span class="tab-badge" id="badgeAll">...</span>
        </button>
        <button id="tabIDE" class="client-tab" onclick="switchClientTab('Antigravity IDE')">
            <span>💻 Antigravity IDE</span>
            <span class="tab-badge" id="badgeIDE">...</span>
        </button>
        <button id="tabCLI" class="client-tab" onclick="switchClientTab('Antigravity CLI')">
            <span>⚡ Antigravity CLI</span>
            <span class="tab-badge" id="badgeCLI">...</span>
        </button>
    </div>

    <!-- 总体宏观 KPI 卡片 -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">累计消耗总 Token</div>
            <div class="kpi-value text-primary" id="kpiTotalTokens">0</div>
            <div class="kpi-desc" id="kpiHumanTokens">约 0 Tokens</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">上下文缓存命中率</div>
            <div class="kpi-value text-success" id="kpiCacheRate">0.0%</div>
            <div class="kpi-desc" id="kpiCachedRead">缓存读取: 0</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">LLM 调用总轮次</div>
            <div class="kpi-value text-warning" id="kpiTotalCalls">0</div>
            <div class="kpi-desc" id="kpiConversations">涉及会话: 0 个</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">平均单次响应延迟</div>
            <div class="kpi-value" style="color: var(--accent);" id="kpiAvgLatency">0.00s</div>
            <div class="kpi-desc">模型首包/整体往返耗时</div>
        </div>
    </div>

    <!-- GitHub 风格年度贡献热力图 (Heatmap) -->
    <div class="card-container heatmap-card">
        <div class="card-header-bar">
            <div class="card-title">🔥 Token 使用贡献热力图 (GitHub Heatmap 风格)</div>
            <!-- 年份筛选器 -->
            <div class="filter-group">
                <span class="filter-label">年份筛选:</span>
                <div class="date-pills" id="yearPillsContainer">
                    <!-- 由 JS 动态填充年份 -->
                </div>
            </div>
        </div>
        <div class="heatmap-scroll-wrap">
            <svg id="heatmapSvg" class="heatmap-svg" width="840" height="135"></svg>
        </div>
        <div class="heatmap-legend">
            <span>少 (Less)</span>
            <div class="legend-cell" style="background: var(--heat-l0);"></div>
            <div class="legend-cell" style="background: var(--heat-l1);"></div>
            <div class="legend-cell" style="background: var(--heat-l2);"></div>
            <div class="legend-cell" style="background: var(--heat-l3);"></div>
            <div class="legend-cell" style="background: var(--heat-l4);"></div>
            <span>多 (More)</span>
        </div>
    </div>

    <!-- 浮动 Tooltip -->
    <div id="heatmapTooltip" class="heatmap-tooltip"></div>

    <!-- 图表网格 -->
    <div class="charts-grid">
        <!-- 各模型占比环形图 -->
        <div class="card-container">
            <div class="card-header-bar">
                <div class="card-title">各模型 Token 消耗对比</div>
            </div>
            <canvas id="modelTokenChart" height="230"></canvas>
        </div>

        <!-- 每日 Token 消耗走势 (带筛选栏与求和统计项目栏，高度缩小至约70%) -->
        <div class="card-container">
            <div class="card-header-bar">
                <div class="card-title">📈 每日 Token 消耗走势与细分统计</div>
            </div>

            <!-- ① 筛选工具栏: 2 个筛选栏 (日期范围 + 模型多选) -->
            <div class="filter-toolbar">
                <!-- 筛选栏 1: 日期范围筛选 (快捷胶囊 + 具体日期控件) -->
                <div class="filter-group">
                    <span class="filter-label">📅 日期范围:</span>
                    <div class="date-pills">
                        <button class="pill-btn" onclick="setDateRangePreset(7, this)">7天</button>
                        <button class="pill-btn" onclick="setDateRangePreset(14, this)">14天</button>
                        <button class="pill-btn active" onclick="setDateRangePreset(30, this)">近30天</button>
                        <button class="pill-btn" onclick="setDateRangePreset(60, this)">60天</button>
                        <button class="pill-btn" onclick="setDateRangePreset(90, this)">90天</button>
                        <button class="pill-btn" onclick="setDateRangePreset(0, this)">全部</button>
                    </div>
                    <div class="date-input-wrap">
                        <input type="date" id="startDateInput" class="date-input" onchange="onCustomDateChange()">
                        <span style="color:var(--text-muted);font-size:12px;">至</span>
                        <input type="date" id="endDateInput" class="date-input" onchange="onCustomDateChange()">
                    </div>
                </div>

                <!-- 筛选栏 2: 多选模型列表 (下拉多选) -->
                <div class="filter-group">
                    <span class="filter-label">🤖 模型筛选:</span>
                    <div class="dropdown-select" id="modelDropdownSelect">
                        <div class="dropdown-trigger" onclick="toggleModelDropdown()">
                            <span id="modelDropdownLabel">已选模型 (0)</span>
                            <span style="font-size:10px;">▼</span>
                        </div>
                        <div class="dropdown-menu" id="modelDropdownMenu">
                            <div class="dropdown-actions">
                                <button type="button" class="action-link" onclick="selectAllModels(true)">全选</button>
                                <button type="button" class="action-link" onclick="selectAllModels(false)">清空</button>
                            </div>
                            <div class="dropdown-list" id="modelCheckboxList">
                                <!-- 由 JS 动态生成模型多选项 -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ② 求和统计项目栏: 根据给定日期与模型动态实时汇总 -->
            <div class="summary-stats-bar">
                <div class="sum-item">
                    <div class="sum-label">💎 所选范围总消耗</div>
                    <div class="sum-val text-primary" id="sumTotalTokens">0</div>
                    <div class="sum-sub" id="sumHumanTokens">约 0 Tokens</div>
                </div>
                <div class="sum-item">
                    <div class="sum-label">⚡ 上下文缓存命中</div>
                    <div class="sum-val text-success" id="sumCachedTokens">0</div>
                    <div class="sum-sub" id="sumCacheRate">命中率: 0.0%</div>
                </div>
                <div class="sum-item">
                    <div class="sum-label">📥 未缓存直接输入</div>
                    <div class="sum-val" id="sumUncachedTokens">0</div>
                    <div class="sum-sub" id="sumUncachedPct">占比: 0.0%</div>
                </div>
                <div class="sum-item">
                    <div class="sum-label">📤 模型生成输出</div>
                    <div class="sum-val text-danger" id="sumOutputTokens">0</div>
                    <div class="sum-sub" id="sumThinkingDetail">思考: 0 (0.0%)</div>
                </div>
                <div class="sum-item">
                    <div class="sum-label">🔄 交互调用与均值</div>
                    <div class="sum-val" id="sumCallsCount">0 次</div>
                    <div class="sum-sub" id="sumDailyAvg">日均: 0 Tokens</div>
                </div>
            </div>

            <!-- 堆叠柱状图 (高度设为约70%) -->
            <div class="daily-chart-wrap">
                <canvas id="dailyTrendChart" height="150"></canvas>
            </div>
        </div>
    </div>

    <!-- 运行环境分布概览 -->
    <div class="card-container">
        <div class="card-header-bar">
            <div class="card-title">🖥️ 运行环境分布概览 (Windows & WSL2)</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>运行环境</th>
                    <th>独立会话数</th>
                    <th>调用次数</th>
                    <th>未缓存输入</th>
                    <th>缓存命中读取</th>
                    <th>模型生成输出</th>
                    <th>总消耗 Token</th>
                    <th>占比</th>
                </tr>
            </thead>
            <tbody id="envTableBody">
                <!-- 由 JS 动态渲染 -->
            </tbody>
        </table>
    </div>

    <!-- 模型消耗明细总览表格 -->
    <div class="card-container">
        <div class="card-header-bar">
            <div class="card-title">📋 模型消耗全量明细总览</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>模型名称</th>
                    <th>调用次数</th>
                    <th>未缓存输入</th>
                    <th>缓存命中输入</th>
                    <th>输出 Token (思考 / 正文)</th>
                    <th>总消耗 Token</th>
                    <th>缓存命中率</th>
                    <th>平均耗时</th>
                </tr>
            </thead>
            <tbody id="modelsTableBody">
                <!-- 由 JS 动态渲染 -->
            </tbody>
        </table>
    </div>

    <!-- ================= 前端核心交互逻辑 ================= -->
    <script>
        // 1. 注入全量数据
        const STATS_BY_CLIENT = {stats_json_str};

        // 2. 全局状态
        let currentClient = 'ALL';
        let currentTheme = localStorage.getItem('antigravity_theme') || 'warm';
        let currentYear = null;
        let selectedModels = new Set();
        let currentStartDate = "";
        let currentEndDate = "";

        let modelChartInstance = null;
        let dailyChartInstance = null;

        // 辅助格式化
        function fmtNum(n) {{
            if (n === null || n === undefined) return "0";
            return Number(n).toLocaleString('en-US');
        }}

        function humanTok(n) {{
            if (n >= 100000000) return "约 " + (n / 100000000).toFixed(2) + " 亿 Tokens";
            if (n >= 10000) return "约 " + (n / 10000).toFixed(1) + " 万 Tokens";
            return fmtNum(n) + " Tokens";
        }}

        // 3. 主题系统
        function setTheme(theme) {{
            currentTheme = theme;
            document.body.className = 'theme-' + theme;
            localStorage.setItem('antigravity_theme', theme);
            
            document.getElementById('themeWarmBtn').classList.toggle('active', theme === 'warm');
            document.getElementById('themeDarkBtn').classList.toggle('active', theme === 'dark');
            
            updateChartThemeColors();
            renderHeatmap();
        }}

        function getThemeColors() {{
            const isDark = currentTheme === 'dark';
            return {{
                grid: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(180, 83, 9, 0.08)',
                tick: isDark ? '#94a3b8' : '#857467',
                legend: isDark ? '#94a3b8' : '#857467',
                cachedBar: isDark ? '#34d399' : '#16a34a',
                uncachedBar: isDark ? '#38bdf8' : '#d97706',
                outputBar: isDark ? '#f43f5e' : '#dc2626',
            }};
        }}

        // 4. 切换顶层工具 (Client)
        function switchClientTab(clientKey) {{
            currentClient = clientKey;
            
            document.getElementById('tabALL').classList.toggle('active', clientKey === 'ALL');
            document.getElementById('tabIDE').classList.toggle('active', clientKey === 'Antigravity IDE');
            document.getElementById('tabCLI').classList.toggle('active', clientKey === 'Antigravity CLI');

            applyClientData();
        }}

        function applyClientData() {{
            const clientData = STATS_BY_CLIENT[currentClient] || STATS_BY_CLIENT['ALL'];
            const ov = clientData.overview;

            // 1. 更新 Header 与 KPI
            document.getElementById('headerSubtitle').innerText = 
                `数据区间：${{ov.min_time}} ~ ${{ov.max_time}} | 覆盖会话数据库：${{ov.total_conversations}} 个`;
            
            document.getElementById('kpiTotalTokens').innerText = fmtNum(ov.total_tokens);
            document.getElementById('kpiHumanTokens').innerText = humanTok(ov.total_tokens);
            document.getElementById('kpiCacheRate').innerText = ov.cache_hit_rate.toFixed(1) + "%";
            document.getElementById('kpiCachedRead').innerText = "缓存读取: " + fmtNum(ov.total_cached_read);
            document.getElementById('kpiTotalCalls').innerText = fmtNum(ov.total_calls);
            document.getElementById('kpiConversations').innerText = "涉及会话: " + fmtNum(ov.total_conversations) + " 个";
            document.getElementById('kpiAvgLatency').innerText = ov.avg_latency.toFixed(2) + "s";

            // 2. 更新模型多选下拉 (默认全选该客户端拥有的全部模型)
            const modelsList = clientData.models.map(m => m.model_name);
            selectedModels = new Set(modelsList);
            buildModelDropdown(modelsList);

            // 3. 更新日期默认区间 (近30天)
            const datesList = clientData.daily.map(d => d.date);
            if (datesList.length > 0) {{
                const maxDateStr = datesList[datesList.length - 1];
                let minIndex = Math.max(0, datesList.length - 30);
                currentStartDate = datesList[minIndex];
                currentEndDate = maxDateStr;

                document.getElementById('startDateInput').value = currentStartDate;
                document.getElementById('endDateInput').value = currentEndDate;
                document.getElementById('startDateInput').min = datesList[0];
                document.getElementById('startDateInput').max = maxDateStr;
                document.getElementById('endDateInput').min = datesList[0];
                document.getElementById('endDateInput').max = maxDateStr;
            }}

            // 4. 重建热力图年份切换器
            initHeatmapYears(clientData);

            // 5. 渲染各模型环形图
            updateModelDoughnutChart(clientData.models);

            // 6. 渲染环境表格
            renderEnvTable(clientData.environments, ov.total_tokens);

            // 7. 渲染模型明细表格
            renderModelsTable(clientData.models);

            // 8. 刷新走势图和求和卡片栏
            updateDailyTrendAndSummary();
        }}

        // 5. 模型下拉多选组件
        function buildModelDropdown(modelsList) {{
            const container = document.getElementById('modelCheckboxList');
            container.innerHTML = "";

            modelsList.forEach(m => {{
                const item = document.createElement('label');
                item.className = 'dropdown-item';
                item.innerHTML = `
                    <input type="checkbox" value="${{m}}" checked onchange="onModelCheckboxChange(this)">
                    <span>${{m}}</span>
                `;
                container.appendChild(item);
            }});
            updateModelDropdownLabel(modelsList.length);
        }}

        function toggleModelDropdown() {{
            document.getElementById('modelDropdownMenu').classList.toggle('open');
        }}

        document.addEventListener('click', (e) => {{
            const wrap = document.getElementById('modelDropdownSelect');
            if (wrap && !wrap.contains(e.target)) {{
                document.getElementById('modelDropdownMenu').classList.remove('open');
            }}
        }});

        function onModelCheckboxChange(checkbox) {{
            if (checkbox.checked) {{
                selectedModels.add(checkbox.value);
            }} else {{
                selectedModels.delete(checkbox.value);
            }}
            const clientData = STATS_BY_CLIENT[currentClient] || STATS_BY_CLIENT['ALL'];
            updateModelDropdownLabel(clientData.models.length);
            updateDailyTrendAndSummary();
        }}

        function selectAllModels(select) {{
            const checkboxes = document.querySelectorAll('#modelCheckboxList input[type="checkbox"]');
            checkboxes.forEach(cb => {{
                cb.checked = select;
                if (select) {{
                    selectedModels.add(cb.value);
                }} else {{
                    selectedModels.delete(cb.value);
                }}
            }});
            const clientData = STATS_BY_CLIENT[currentClient] || STATS_BY_CLIENT['ALL'];
            updateModelDropdownLabel(clientData.models.length);
            updateDailyTrendAndSummary();
        }}

        function updateModelDropdownLabel(totalCount) {{
            const label = document.getElementById('modelDropdownLabel');
            if (selectedModels.size === totalCount) {{
                label.innerText = `已选全部模型 (${{totalCount}}/${{totalCount}})`;
            }} else if (selectedModels.size === 0) {{
                label.innerText = `未选择任何模型 (0/${{totalCount}})`;
            }} else {{
                label.innerText = `已选 ${{selectedModels.size}} 个模型`;
            }}
        }}

        // 6. 日期筛选逻辑
        function setDateRangePreset(days, btn) {{
            document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');

            const clientData = STATS_BY_CLIENT[currentClient] || STATS_BY_CLIENT['ALL'];
            const datesList = clientData.daily.map(d => d.date);
            if (datesList.length === 0) return;

            currentEndDate = datesList[datesList.length - 1];
            if (days === 0) {{
                currentStartDate = datesList[0];
            }} else {{
                let minIndex = Math.max(0, datesList.length - days);
                currentStartDate = datesList[minIndex];
            }}

            document.getElementById('startDateInput').value = currentStartDate;
            document.getElementById('endDateInput').value = currentEndDate;

            updateDailyTrendAndSummary();
        }}

        function onCustomDateChange() {{
            const s = document.getElementById('startDateInput').value;
            const e = document.getElementById('endDateInput').value;
            if (s && e) {{
                currentStartDate = s;
                currentEndDate = e;
                document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
                updateDailyTrendAndSummary();
            }}
        }}

        // 7. GitHub 风格年度贡献热力图 (Heatmap)
        function initHeatmapYears(clientData) {{
            const dates = clientData.daily.map(d => d.date);
            const yearsSet = new Set(dates.map(d => d.slice(0, 4)));
            const years = Array.from(yearsSet).sort().reverse();
            if (years.length === 0) years.push(new Date().getFullYear().toString());

            const container = document.getElementById('yearPillsContainer');
            container.innerHTML = "";

            if (!currentYear || !yearsSet.has(currentYear)) {{
                currentYear = years[0];
            }}

            years.forEach((yr, idx) => {{
                const btn = document.createElement('button');
                btn.className = 'pill-btn' + (yr === currentYear ? ' active' : '');
                btn.innerText = yr + '年';
                btn.onclick = () => {{
                    currentYear = yr;
                    document.querySelectorAll('#yearPillsContainer .pill-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    renderHeatmap();
                }};
                container.appendChild(btn);
            }});

            renderHeatmap();
        }}

        function renderHeatmap() {{
            const clientData = STATS_BY_CLIENT[currentClient] || STATS_BY_CLIENT['ALL'];
            const svg = document.getElementById('heatmapSvg');
            svg.innerHTML = "";

            // 构建每日 Token 映射
            const dateMap = {{}};
            clientData.daily.forEach(d => {{
                dateMap[d.date] = d;
            }});

            const yr = parseInt(currentYear, 10);
            const startDate = new Date(yr, 0, 1);
            const endDate = new Date(yr, 11, 31);

            // 对齐到第一周的周日
            const startDayOfWeek = startDate.getDay(); // 0 是周日
            const calStart = new Date(startDate);
            calStart.setDate(calStart.getDate() - startDayOfWeek);

            // 获取非零日消耗的分位数
            const nonZeroTokens = clientData.daily
                .filter(d => d.date.startsWith(currentYear) && d.total_tokens > 0)
                .map(d => d.total_tokens)
                .sort((a, b) => a - b);

            let q1 = 50000, q2 = 300000, q3 = 1000000;
            if (nonZeroTokens.length > 4) {{
                q1 = nonZeroTokens[Math.floor(nonZeroTokens.length * 0.25)];
                q2 = nonZeroTokens[Math.floor(nonZeroTokens.length * 0.50)];
                q3 = nonZeroTokens[Math.floor(nonZeroTokens.length * 0.75)];
            }}

            const isDark = currentTheme === 'dark';
            const colors = [
                isDark ? '#1e293b' : '#ede4d4', // L0
                isDark ? '#075985' : '#fde68a', // L1
                isDark ? '#0284c7' : '#f59e0b', // L2
                isDark ? '#38bdf8' : '#d97706', // L3
                isDark ? '#bae6fd' : '#92400e', // L4
            ];

            const cellSize = 11;
            const cellGap = 3;
            const leftOffset = 36;
            const topOffset = 22;

            // 绘制左侧星期标签 (一、三、五)
            const weekLabels = [
                {{ day: 1, text: '周一' }},
                {{ day: 3, text: '周三' }},
                {{ day: 5, text: '周五' }},
            ];
            weekLabels.forEach(wl => {{
                const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
                t.setAttribute("x", "4");
                t.setAttribute("y", topOffset + wl.day * (cellSize + cellGap) + 9);
                t.setAttribute("font-size", "10");
                t.setAttribute("fill", isDark ? "#64748b" : "#a49386");
                t.textContent = wl.text;
                svg.appendChild(t);
            }});

            // 绘制日期格子和月份标签
            let cur = new Date(calStart);
            let weekCol = 0;
            let lastMonth = -1;

            const tooltip = document.getElementById('heatmapTooltip');

            while (cur <= endDate || cur.getDay() !== 0) {{
                const colX = leftOffset + weekCol * (cellSize + cellGap);
                const dayOfWeek = cur.getDay();
                const rowY = topOffset + dayOfWeek * (cellSize + cellGap);

                const m = cur.getMonth();
                if (cur.getFullYear() === yr && m !== lastMonth && dayOfWeek === 0) {{
                    const mt = document.createElementNS("http://www.w3.org/2000/svg", "text");
                    mt.setAttribute("x", colX);
                    mt.setAttribute("y", topOffset - 6);
                    mt.setAttribute("font-size", "10");
                    mt.setAttribute("fill", isDark ? "#94a3b8" : "#857467");
                    mt.textContent = (m + 1) + "月";
                    svg.appendChild(mt);
                    lastMonth = m;
                }}

                const dateStr = cur.toISOString().slice(0, 10);
                const dData = dateMap[dateStr];
                const tokens = dData ? dData.total_tokens : 0;
                const calls = dData ? dData.calls : 0;

                let level = 0;
                if (tokens > 0) {{
                    if (tokens <= q1) level = 1;
                    else if (tokens <= q2) level = 2;
                    else if (tokens <= q3) level = 3;
                    else level = 4;
                }}

                // 仅显示当年内的格子，跨年边缘格略微半透明
                const inCurrentYear = cur.getFullYear() === yr;
                const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                rect.setAttribute("x", colX);
                rect.setAttribute("y", rowY);
                rect.setAttribute("width", cellSize);
                rect.setAttribute("height", cellSize);
                rect.setAttribute("rx", "2");
                rect.setAttribute("fill", inCurrentYear ? colors[level] : (isDark ? '#0f172a' : '#f8f4ec'));
                rect.setAttribute("class", "heat-cell");
                if (!inCurrentYear) rect.setAttribute("opacity", "0.3");

                // Tooltip 交互
                rect.addEventListener('mouseenter', (ev) => {{
                    let content = `<strong>${{dateStr}}</strong>`;
                    if (tokens > 0) {{
                        content += `<br>消耗: <strong>${{fmtNum(tokens)}}</strong> Tokens`;
                        content += `<br>调用: ${{fmtNum(calls)}} 次轮次`;
                    }} else {{
                        content += `<br>暂无 Token 消耗记录`;
                    }}
                    tooltip.innerHTML = content;
                    tooltip.style.display = 'block';
                }});

                rect.addEventListener('mousemove', (ev) => {{
                    tooltip.style.left = (ev.pageX + 12) + 'px';
                    tooltip.style.top = (ev.pageY - 28) + 'px';
                }});

                rect.addEventListener('mouseleave', () => {{
                    tooltip.style.display = 'none';
                }});

                svg.appendChild(rect);

                cur.setDate(cur.getDate() + 1);
                if (cur.getDay() === 0) {{
                    weekCol++;
                }}
            }}

            const totalWidth = leftOffset + (weekCol + 1) * (cellSize + cellGap) + 10;
            svg.setAttribute("width", Math.max(820, totalWidth));
        }}

        // 8. 环形图更新
        function updateModelDoughnutChart(modelsList) {{
            const c = getThemeColors();
            const labels = modelsList.map(m => m.model_name);
            const data = modelsList.map(m => m.total_tokens);

            if (!modelChartInstance) {{
                modelChartInstance = new Chart(document.getElementById('modelTokenChart'), {{
                    type: 'doughnut',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            data: data,
                            backgroundColor: [
                                '#d97706', '#0284c7', '#dc2626', '#16a34a', '#818cf8', 
                                '#ca8a04', '#ec4899', '#f97316', '#64748b'
                            ]
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{
                                position: 'bottom',
                                labels: {{ color: c.legend, boxWidth: 12, font: {{ size: 11 }} }}
                            }}
                        }}
                    }}
                }});
            }} else {{
                modelChartInstance.data.labels = labels;
                modelChartInstance.data.datasets[0].data = data;
                modelChartInstance.options.plugins.legend.labels.color = c.legend;
                modelChartInstance.update();
            }}
        }}

        // 9. 走势图与求和统计联动
        function updateDailyTrendAndSummary() {{
            const clientData = STATS_BY_CLIENT[currentClient] || STATS_BY_CLIENT['ALL'];
            const allDates = clientData.daily.map(d => d.date);

            const filteredDates = allDates.filter(d => 
                (!currentStartDate || d >= currentStartDate) && 
                (!currentEndDate || d <= currentEndDate)
            );

            let sumUncached = 0;
            let sumCached = 0;
            let sumOutput = 0;
            let sumThinking = 0;
            let sumResponse = 0;
            let sumTotal = 0;
            let sumCalls = 0;

            const chartUncached = [];
            const chartCached = [];
            const chartOutput = [];

            filteredDates.forEach(date => {{
                let dayUncached = 0;
                let dayCached = 0;
                let dayOutput = 0;

                const dayMap = clientData.daily_by_model[date];
                if (dayMap) {{
                    Object.keys(dayMap).forEach(modelName => {{
                        if (selectedModels.has(modelName)) {{
                            const mData = dayMap[modelName];
                            const u = mData.input_tokens || 0;
                            const c = mData.cached_tokens || 0;
                            const o = mData.output_tokens || 0;
                            const th = mData.thinking_tokens || 0;
                            const resp = mData.response_tokens || 0;
                            const tot = mData.total_tokens || 0;
                            const calls = mData.calls || 0;

                            dayUncached += u;
                            dayCached += c;
                            dayOutput += o;

                            sumUncached += u;
                            sumCached += c;
                            sumOutput += o;
                            sumThinking += th;
                            sumResponse += resp;
                            sumTotal += tot;
                            sumCalls += calls;
                        }}
                    }});
                }}

                chartUncached.push(dayUncached);
                chartCached.push(dayCached);
                chartOutput.push(dayOutput);
            }});

            // 更新求和统计项目栏
            const fullPrompt = sumUncached + sumCached;
            const cacheRate = fullPrompt > 0 ? ((sumCached / fullPrompt) * 100).toFixed(1) : "0.0";
            const uncachedPct = sumTotal > 0 ? ((sumUncached / sumTotal) * 100).toFixed(1) : "0.0";
            const thinkingPct = sumOutput > 0 ? ((sumThinking / sumOutput) * 100).toFixed(1) : "0.0";
            const daysCount = Math.max(1, filteredDates.length);
            const dailyAvg = Math.round(sumTotal / daysCount);

            document.getElementById('sumTotalTokens').innerText = fmtNum(sumTotal);
            document.getElementById('sumHumanTokens').innerText = humanTok(sumTotal);
            document.getElementById('sumCachedTokens').innerText = fmtNum(sumCached);
            document.getElementById('sumCacheRate').innerText = "命中率: " + cacheRate + "%";
            document.getElementById('sumUncachedTokens').innerText = fmtNum(sumUncached);
            document.getElementById('sumUncachedPct').innerText = "占比: " + uncachedPct + "%";
            document.getElementById('sumOutputTokens').innerText = fmtNum(sumOutput);
            document.getElementById('sumThinkingDetail').innerText = "思考: " + fmtNum(sumThinking) + " (" + thinkingPct + "%)";
            document.getElementById('sumCallsCount').innerText = fmtNum(sumCalls) + " 次";
            document.getElementById('sumDailyAvg').innerText = "日均: " + fmtNum(dailyAvg) + " Tokens";

            // 初始化或更新走势图 (高度保持紧凑)
            const c = getThemeColors();
            if (!dailyChartInstance) {{
                dailyChartInstance = new Chart(document.getElementById('dailyTrendChart'), {{
                    type: 'bar',
                    data: {{
                        labels: filteredDates,
                        datasets: [
                            {{ label: '缓存命中', data: chartCached, backgroundColor: c.cachedBar, stack: 'stack0' }},
                            {{ label: '未缓存输入', data: chartUncached, backgroundColor: c.uncachedBar, stack: 'stack0' }},
                            {{ label: '模型输出', data: chartOutput, backgroundColor: c.outputBar, stack: 'stack0' }}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {{
                            x: {{
                                stacked: true,
                                ticks: {{ color: c.tick, maxRotation: 45, minRotation: 0, font: {{ size: 10 }} }},
                                grid: {{ color: c.grid }}
                            }},
                            y: {{
                                stacked: true,
                                ticks: {{ color: c.tick, font: {{ size: 10 }} }},
                                grid: {{ color: c.grid }}
                            }}
                        }},
                        plugins: {{
                            legend: {{
                                labels: {{ color: c.legend, boxWidth: 12, font: {{ size: 11 }} }}
                            }},
                            tooltip: {{
                                callbacks: {{
                                    label: function(context) {{
                                        return context.dataset.label + ': ' + fmtNum(context.raw) + ' Tokens';
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});
            }} else {{
                dailyChartInstance.data.labels = filteredDates;
                dailyChartInstance.data.datasets[0].data = chartCached;
                dailyChartInstance.data.datasets[1].data = chartUncached;
                dailyChartInstance.data.datasets[2].data = chartOutput;
                dailyChartInstance.update();
            }}
        }}

        function updateChartThemeColors() {{
            const c = getThemeColors();
            if (modelChartInstance) {{
                modelChartInstance.options.plugins.legend.labels.color = c.legend;
                modelChartInstance.update();
            }}
            if (dailyChartInstance) {{
                dailyChartInstance.data.datasets[0].backgroundColor = c.cachedBar;
                dailyChartInstance.data.datasets[1].backgroundColor = c.uncachedBar;
                dailyChartInstance.data.datasets[2].backgroundColor = c.outputBar;
                dailyChartInstance.options.scales.x.ticks.color = c.tick;
                dailyChartInstance.options.scales.x.grid.color = c.grid;
                dailyChartInstance.options.scales.y.ticks.color = c.tick;
                dailyChartInstance.options.scales.y.grid.color = c.grid;
                dailyChartInstance.options.plugins.legend.labels.color = c.legend;
                dailyChartInstance.update();
            }}
        }}

        // 10. 表格渲染
        function renderEnvTable(envs, totalTokens) {{
            const tbody = document.getElementById('envTableBody');
            tbody.innerHTML = "";
            envs.forEach(e => {{
                const pct = totalTokens > 0 ? ((e.total_tokens / totalTokens) * 100).toFixed(2) : "0.00";
                const badgeCls = e.env.toLowerCase().includes('wsl') ? 'badge-wsl' : 'badge';
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="badge ${{badgeCls}}">${{e.env}}</span></td>
                    <td>${{fmtNum(e.conv_count)}}</td>
                    <td>${{fmtNum(e.calls)}}</td>
                    <td>${{fmtNum(e.input_tokens)}}</td>
                    <td>${{fmtNum(e.cached_tokens)}}</td>
                    <td>${{fmtNum(e.output_tokens)}} <small style="color:var(--text-muted)">(${{fmtNum(e.thinking_tokens)}} 思考)</small></td>
                    <td><strong class="text-primary">${{fmtNum(e.total_tokens)}}</strong></td>
                    <td><strong>${{pct}}%</strong></td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function renderModelsTable(models) {{
            const tbody = document.getElementById('modelsTableBody');
            tbody.innerHTML = "";
            models.forEach(m => {{
                const fullInp = m.input_tokens + m.cached_tokens;
                const cRate = fullInp > 0 ? ((m.cached_tokens / fullInp) * 100).toFixed(1) : "0.0";
                const avgLat = m.latency_count > 0 ? (m.total_latency / m.latency_count).toFixed(2) : "0.00";
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${{m.model_name}}</strong><br><small style="color:var(--text-muted)">${{m.model_id}}</small></td>
                    <td>${{fmtNum(m.calls)}}</td>
                    <td>${{fmtNum(m.input_tokens)}}</td>
                    <td>${{fmtNum(m.cached_tokens)}}</td>
                    <td>${{fmtNum(m.output_tokens)}} <br><small style="color:var(--text-muted)">(${{fmtNum(m.thinking_tokens)}} 思考 / ${{fmtNum(m.response_tokens)}} 正文)</small></td>
                    <td><strong class="text-primary">${{fmtNum(m.total_tokens)}}</strong></td>
                    <td><span class="badge">${{cRate}}%</span></td>
                    <td>${{avgLat}}s</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        // 11. 初始化工具 Tab 徽章数字
        function initTabBadges() {{
            const allCalls = STATS_BY_CLIENT['ALL']?.overview?.total_calls || 0;
            const ideCalls = STATS_BY_CLIENT['Antigravity IDE']?.overview?.total_calls || 0;
            const cliCalls = STATS_BY_CLIENT['Antigravity CLI']?.overview?.total_calls || 0;

            document.getElementById('badgeAll').innerText = fmtNum(allCalls) + " 次";
            document.getElementById('badgeIDE').innerText = fmtNum(ideCalls) + " 次";
            document.getElementById('badgeCLI').innerText = fmtNum(cliCalls) + " 次";
        }}

        // 12. 页面就绪入口
        window.addEventListener('DOMContentLoaded', () => {{
            initTabBadges();
            setTheme(currentTheme);
            applyClientData();
        }});
    </script>
</body>
</html>
"""
    return html


def export_all(
    base_dirs: Optional[Union[str, List[Union[str, Dict[str, str]]]]] = None,
    output_dir: str = "."
):
    """主执行函数：自动探测环境与工具类型、收集聚合数据并导出完整报告，并在浏览器中自动打开"""
    scanned_targets = discover_all_data_dirs() if base_dirs is None else None

    records = collect_all_data(base_dirs)
    if not records:
        print("未找到任何 Token 记录！")
        return

    # 全量总览统计
    overall_stats = generate_multi_dimensional_stats(records)

    # 按工具类型分拆聚合统计 (供前端顶层切换联动)
    stats_by_client = {
        "ALL": overall_stats
    }
    client_types = set(r.get("client_type", "Antigravity IDE") for r in records)
    for c_name in client_types:
        sub_records = [r for r in records if r.get("client_type") == c_name]
        stats_by_client[c_name] = generate_multi_dimensional_stats(sub_records)

    # 1. 导出 Markdown 报告
    report_md_path = os.path.join(output_dir, "Antigravity_Token_Report.md")
    md_content = render_markdown_report(overall_stats, scanned_targets)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[OK] 统计报告已保存至: {os.path.abspath(report_md_path)}")

    # 1.2 导出 HTML 仪表盘
    dashboard_html_path = os.path.join(output_dir, "Antigravity_Token_Dashboard.html")
    html_content = render_html_dashboard(stats_by_client, scanned_targets)
    with open(dashboard_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] 可视化仪表盘已保存至: {os.path.abspath(dashboard_html_path)}")

    # 2. 导出全量 JSON 数据
    json_path = os.path.join(output_dir, "token_stats_summary.json")

    # 确保序列化纯 dict
    for s_item in stats_by_client.values():
        for c in s_item.get("conversations", []):
            if isinstance(c.get("models"), defaultdict):
                c["models"] = dict(c["models"])

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stats_by_client, f, ensure_ascii=False, indent=2)
    print(f"[OK] 结构化统计数据已保存至: {os.path.abspath(json_path)}")

    # 3. 导出精简明细 CSV 文件
    csv_path = os.path.join(output_dir, "token_records_detailed.csv")
    csv_fields = [
        "conv_id",
        "client_type",
        "env",
        "step_idx",
        "timestamp",
        "model_name",
        "model_id",
        "input_tokens",
        "cached_tokens",
        "output_tokens",
        "thinking_tokens",
        "response_tokens",
        "total_tokens",
        "latency_sec",
        "request_id",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)
    print(f"[OK] 明细 CSV 数据已保存至: {os.path.abspath(csv_path)}")

    # 4. 打印终端控制台摘要
    ov = overall_stats["overview"]
    envs = overall_stats.get("environments", [])
    clients = overall_stats.get("clients", [])
    print("\n" + "=" * 68)
    print("           ANTIGRAVITY TOKEN 跨环境与多工具统计总览")
    print("=" * 68)
    print(f"有效数据库会话总数 : {ov['total_conversations']}")
    print(f"LLM 响应总调用次数 : {ov['total_calls']}")
    print(f"消耗总 Token 数量   : {format_num(ov['total_tokens'])} ({human_tokens(ov['total_tokens'])})")
    print(f"  ├─ 未缓存输入   : {format_num(ov['total_input_uncached'])}")
    print(f"  ├─ 缓存读取输入 : {format_num(ov['total_cached_read'])} (缓存率: {ov['cache_hit_rate']:.1f}%)")
    print(
        f"  └─ 模型生成输出 : {format_num(ov['total_output'])} (思考: {format_num(ov['total_thinking'])}, 正文: {format_num(ov['total_response'])})"
    )
    print(f"平均单次响应耗时   : {ov['avg_latency']:.2f} 秒")
    print("-" * 68)
    print("工具类型分布 (Client Breakdown):")
    for cl in clients:
        pct = (cl["total_tokens"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0.0
        print(
            f" - {cl['client_type']:<18} : {format_num(cl['total_tokens']):>12} Tokens ({pct:>5.1f}%) | {cl['conv_count']:>3} 会话 | {cl['calls']:>5} 次调用"
        )
    print("-" * 68)
    print("跨运行环境分布 (Environment Distribution):")
    for e in envs:
        pct = (e["total_tokens"] / ov["total_tokens"] * 100) if ov["total_tokens"] > 0 else 0.0
        print(
            f" - {e['env']:<18} : {format_num(e['total_tokens']):>12} Tokens ({pct:>5.1f}%) | {e['conv_count']:>3} 会话 | {e['calls']:>5} 次调用"
        )
    print("-" * 68)
    print("各模型消耗分布 (Top Models):")
    for m in overall_stats["models"][:8]:
        print(
            f" - {m['model_name']:<30} : {format_num(m['total_tokens']):>12} Tokens ({m['calls']:>4} 次调用, 平均耗时 {m['total_latency'] / max(1, m['latency_count']):.2f}s)"
        )
    print("=" * 68 + "\n")

    # 5. 自动在系统默认浏览器中打开 HTML 仪表盘
    dashboard_abs_url = f"file:///{os.path.abspath(dashboard_html_path).replace(os.sep, '/')}"
    try:
        webbrowser.open(dashboard_abs_url)
        print(f"[OK] 已在系统默认浏览器中自动打开统计仪表盘: {dashboard_abs_url}")
    except Exception:
        pass


if __name__ == "__main__":
    export_all()
    # 如果处于交互式控制台则提示按回车退出
    if sys.stdin.isatty():
        try:
            input("按回车键退出...")
        except Exception:
            pass
