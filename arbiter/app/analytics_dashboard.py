import asyncio
import csv
import io
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import mean, median, pstdev

import streamlit as st

try:  # pragma: no cover - optional richer charting path
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - graceful fallback
    px = None
    go = None

from arbiter.app.ui_styles import UI_CSS
from arbiter.infra.benchmark_store import get_benchmark_store
from arbiter.infra.db import (
    database_enabled,
    get_benchmark_stats as db_get_benchmark_stats,
    get_run_iterations as db_get_run_iterations,
    list_runs as db_list_runs,
    sqlalchemy_available,
)
from arbiter.infra.memory_store import get_memory_store
from arbiter.infra.plugin_registry import get_plugin_registry

try:
    from arbiter import __version__
except ImportError:
    try:
        __version__ = version("the-arbiter")
    except PackageNotFoundError:
        __version__ = "0.1.0"


st.set_page_config(
    page_title="The Arbiter Analytics",
    page_icon="•",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(UI_CSS, unsafe_allow_html=True)


def summary_cards(items):
    cards = []
    for label, value in items:
        cards.append(
            "<div class='summary-card'>"
            f"<div class='summary-card-label'>{label}</div>"
            f"<div class='summary-card-value'>{value}</div>"
            "</div>"
        )
    st.markdown("<div class='summary-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def truncate_text(text: str, limit: int = 180) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 16].rstrip() + "... [truncated]"


def run_async(coro, default):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(coro)
        except Exception:
            return default
    return default


def fallback_runs(limit: int = 300) -> list[dict]:
    store = get_benchmark_store()
    output = []
    for item in store.recent_runs(limit):
        output.append(
            {
                "id": item.get("run_id", ""),
                "created_at": item.get("timestamp_utc", ""),
                "task_mode": item.get("task_mode", "Unknown"),
                "user_input": "",
                "best_score": float(item.get("best_score", 0.0) or 0.0),
                "best_solution": "",
                "iteration_count": int(item.get("iteration_count", 0) or 0),
                "total_cost_usd": float(item.get("total_cost", 0.0) or 0.0),
                "stop_reason": item.get("stop_reason", ""),
                "ship_readiness": item.get("ship_readiness", "UNASSESSED"),
                "verification_status": item.get("verification_status", "UNVERIFIED"),
                "validity_status": item.get("validity_status", "UNKNOWN"),
                "run_metadata": {
                    "benchmark_mode": item.get("benchmark_mode", False),
                    "benchmark_strategy": item.get("benchmark_strategy", ""),
                    "benchmark_pack": item.get("benchmark_pack", ""),
                    "benchmark_case_id": item.get("benchmark_case_id", ""),
                    "benchmark_case_title": item.get("benchmark_case_title", ""),
                },
            }
        )
    return list(reversed(output))


def load_runs(limit: int = 300) -> tuple[list[dict], str]:
    if database_enabled():
        runs = run_async(db_list_runs(limit=limit), default=[])
        if runs:
            return runs, "database"
    return fallback_runs(limit=limit), "benchmark_store"


def load_run_iterations(run_id: str) -> list[dict]:
    if not database_enabled():
        return []
    return run_async(db_get_run_iterations(run_id), default=[])


def load_benchmark_stats(runs_source: str) -> dict:
    if runs_source == "database" and database_enabled():
        stats = run_async(db_get_benchmark_stats(), default={})
        if stats:
            return stats
    return get_benchmark_store().stats()


def architect_model_from_run(run: dict) -> str:
    metadata = dict(run.get("run_metadata", {}) or {})
    usages = list(metadata.get("model_usage", []) or [])
    for item in reversed(usages):
        if item.get("role") == "Architect" and item.get("model"):
            return str(item.get("model"))
    return "unknown"


def iter_model_usage(runs: list[dict]):
    for run in runs:
        metadata = dict(run.get("run_metadata", {}) or {})
        for item in list(metadata.get("model_usage", []) or []):
            enriched = dict(item)
            enriched["run_id"] = run.get("id", "")
            enriched["best_score"] = float(run.get("best_score", 0.0) or 0.0)
            yield enriched


def export_csv_text(runs: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "id",
            "created_at",
            "task_mode",
            "best_score",
            "iteration_count",
            "total_cost_usd",
            "ship_readiness",
            "verification_status",
            "validity_status",
            "stop_reason",
        ],
    )
    writer.writeheader()
    for run in runs:
        writer.writerow(
            {
                "id": run.get("id", ""),
                "created_at": run.get("created_at", ""),
                "task_mode": run.get("task_mode", ""),
                "best_score": run.get("best_score", 0.0),
                "iteration_count": run.get("iteration_count", 0),
                "total_cost_usd": run.get("total_cost_usd", 0.0),
                "ship_readiness": run.get("ship_readiness", ""),
                "verification_status": run.get("verification_status", ""),
                "validity_status": run.get("validity_status", ""),
                "stop_reason": run.get("stop_reason", ""),
            }
        )
    return buffer.getvalue()


def breakdown_rows(runs: list[dict], field: str, default: str = "UNKNOWN") -> list[dict]:
    counts: dict[str, int] = {}
    for run in runs:
        value = str(run.get(field, default) or default)
        counts[value] = counts.get(value, 0) + 1
    return [
        {"label": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def filter_runs(
    runs: list[dict],
    mode_filter: str = "All",
    readiness_filter: str = "All",
    verification_filter: str = "All",
    search_text: str = "",
) -> list[dict]:
    query = str(search_text or "").strip().lower()
    filtered = []
    for run in runs:
        if mode_filter != "All" and run.get("task_mode") != mode_filter:
            continue
        if readiness_filter != "All" and run.get("ship_readiness") != readiness_filter:
            continue
        if verification_filter != "All" and run.get("verification_status") != verification_filter:
            continue

        if query:
            metadata = dict(run.get("run_metadata", {}) or {})
            searchable = " ".join(
                [
                    str(run.get("id", "")),
                    str(run.get("task_mode", "")),
                    str(run.get("user_input", "")),
                    str(run.get("best_solution", "")),
                    str(metadata.get("benchmark_case_title", "")),
                    str(metadata.get("benchmark_strategy", "")),
                ]
            ).lower()
            if query not in searchable:
                continue
        filtered.append(run)
    return filtered


def benchmark_stats_table(runs: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        mode = str(run.get("task_mode", "Unknown") or "Unknown")
        grouped.setdefault(mode, []).append(run)

    rows = []
    for mode, items in grouped.items():
        scores = [float(item.get("best_score", 0.0) or 0.0) for item in items]
        rows.append(
            {
                "task_mode": mode,
                "count": len(scores),
                "mean": round(mean(scores), 2),
                "median": round(median(scores), 2),
                "std": round(pstdev(scores), 2) if len(scores) > 1 else 0.0,
                "min": round(min(scores), 2),
                "max": round(max(scores), 2),
            }
        )
    return sorted(rows, key=lambda item: item["task_mode"])


def benchmark_strategy_rows(runs: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        metadata = dict(run.get("run_metadata", {}) or {})
        strategy = str(metadata.get("benchmark_strategy", "") or "ad_hoc")
        grouped.setdefault(strategy, []).append(run)

    rows = []
    for strategy, items in grouped.items():
        scores = [float(item.get("best_score", 0.0) or 0.0) for item in items]
        costs = [float(item.get("total_cost_usd", 0.0) or 0.0) for item in items]
        rows.append(
            {
                "strategy": strategy,
                "runs": len(items),
                "avg_score": round(mean(scores), 2) if scores else 0.0,
                "avg_cost": round(mean(costs), 4) if costs else 0.0,
            }
        )
    return sorted(rows, key=lambda item: (-item["runs"], item["strategy"]))


def model_comparison_rows(runs: list[dict]) -> tuple[list[dict], list[dict]]:
    by_architect: dict[str, list[dict]] = {}
    by_model_usage: dict[str, list[dict]] = {}

    for run in runs:
        arch_model = architect_model_from_run(run)
        by_architect.setdefault(arch_model, []).append(run)

    for usage in iter_model_usage(runs):
        model = str(usage.get("model", "") or "unknown")
        by_model_usage.setdefault(model, []).append(usage)

    architect_rows = []
    for model, items in by_architect.items():
        avg_score = mean(float(item.get("best_score", 0.0) or 0.0) for item in items)
        total_cost = mean(float(item.get("total_cost_usd", 0.0) or 0.0) for item in items)
        architect_rows.append(
            {
                "architect_model": model,
                "avg_score": round(avg_score, 2),
                "runs": len(items),
                "cost_per_point": round(total_cost / avg_score, 4) if avg_score > 0 else 0.0,
            }
        )

    latency_rows = []
    for model, items in by_model_usage.items():
        latencies = [float(item.get("latency_ms", 0.0) or 0.0) for item in items if item.get("latency_ms") is not None]
        costs = [float(item.get("estimated_cost_usd", 0.0) or 0.0) for item in items]
        score_denominator = mean(float(item.get("best_score", 0.0) or 0.0) for item in items) if items else 0.0
        latency_rows.append(
            {
                "model": model,
                "avg_latency_ms": round(mean(latencies), 2) if latencies else 0.0,
                "calls": len(items),
                "avg_cost_per_call": round(mean(costs), 6) if costs else 0.0,
                "cost_per_quality_point": round((mean(costs) / score_denominator), 6) if costs and score_denominator > 0 else 0.0,
            }
        )

    return (
        sorted(architect_rows, key=lambda item: item["avg_score"], reverse=True),
        sorted(latency_rows, key=lambda item: item["avg_latency_ms"]),
    )


def count_eval_fixtures() -> int:
    fixtures_dir = Path(__file__).resolve().parents[2] / "evals" / "fixtures"
    total = 0
    for path in fixtures_dir.glob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                total += sum(1 for line in handle if line.strip())
        except Exception:
            continue
    return total


def provider_catalog_rows(registry) -> list[dict]:
    providers = sorted(
        {
            plugin.provider
            for model_id in registry.all_model_ids()
            for plugin in [registry.get(model_id)]
            if plugin is not None
        }
    )
    rows = []
    for provider in providers:
        state = dict(registry.provider_state(provider) or {})
        models = list(state.get("models", []) or [])
        available_count = 0
        total_count = 0
        for model_id in registry.all_model_ids():
            plugin = registry.get(model_id)
            if plugin is None or plugin.provider != provider:
                continue
            total_count += 1
            if registry.is_model_available(model_id):
                available_count += 1
        rows.append(
            {
                "provider": provider,
                "catalog_status": str(state.get("status", "static") or "static"),
                "catalog_models": len(models),
                "registry_models": total_count,
                "available_models": available_count,
            }
        )
    return rows


def render_plotly_or_table(title: str, rows: list[dict], x: str, y: str, chart_type: str = "bar") -> None:
    st.markdown(f"#### {title}")
    if not rows:
        st.caption("No data available yet.")
        return

    if px is not None:
        if chart_type == "line":
            fig = px.line(rows, x=x, y=y, markers=True)
        elif chart_type == "scatter":
            fig = px.scatter(rows, x=x, y=y, hover_data=list(rows[0].keys()))
        else:
            fig = px.bar(rows, x=x, y=y)
        fig.update_layout(
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font_color="#171717",
            margin=dict(l=24, r=24, t=30, b=24),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart({row[x]: row[y] for row in rows})


runs, runs_source = load_runs(limit=300)
benchmark_stats = load_benchmark_stats(runs_source)
memory_stats = get_memory_store().stats()
registry = get_plugin_registry()

st.title("The Arbiter Analytics")
st.caption(
    "Operational analytics, benchmark history, and run-level observability. "
    f"Current source: {runs_source.upper()}."
)

summary_cards(
    [
        ("Run Source", runs_source.upper()),
        ("Stored Runs", len(runs)),
        ("Database", "READY" if database_enabled() else "FALLBACK"),
        ("Model Catalog", f"{len(registry.all_model_ids())} models"),
    ]
)

overview_tab, explorer_tab, analytics_tab, benchmarks_tab, system_tab = st.tabs(
    ["Overview", "Run Explorer", "Analytics", "Benchmarks", "System"]
)

with overview_tab:
    ready_runs = sum(1 for run in runs if run.get("ship_readiness") == "READY")
    total_cost = sum(float(run.get("total_cost_usd", 0.0) or 0.0) for run in runs)
    total_tokens = sum(
        int(item.get("total_tokens", 0) or 0)
        for item in iter_model_usage(runs)
    )
    avg_score = round(mean(float(run.get("best_score", 0.0) or 0.0) for run in runs), 2) if runs else 0.0
    success_rate = round((ready_runs / len(runs)) * 100, 1) if runs else 0.0

    summary_cards(
        [
            ("Avg Score", avg_score),
            ("Ready Rate", f"{success_rate}%"),
            ("Total Cost", f"${total_cost:.4f}"),
            ("Tracked Tokens", f"{total_tokens:,}"),
        ]
    )
    summary_cards(
        [
            ("Verified Rate", f"{benchmark_stats.get('verified_rate', 0.0)}%"),
            ("Avg Iterations", benchmark_stats.get("avg_iterations", 0.0)),
            ("Benchmark Runs", benchmark_stats.get("benchmark_runs", 0)),
            ("Memory Entries", memory_stats.get("count", 0)),
        ]
    )

    left, right = st.columns(2)
    with left:
        render_plotly_or_table(
            "Readiness Breakdown",
            breakdown_rows(runs, "ship_readiness", default="UNASSESSED"),
            x="label",
            y="count",
        )
    with right:
        render_plotly_or_table(
            "Verification Breakdown",
            breakdown_rows(runs, "verification_status", default="UNVERIFIED"),
            x="label",
            y="count",
        )

    st.markdown("#### Last 5 Runs")
    recent = list(reversed(runs[-5:])) if runs else []
    if recent:
        st.dataframe(
            [
                {
                    "run_id": run.get("id", ""),
                    "task_mode": run.get("task_mode", ""),
                    "score": run.get("best_score", 0.0),
                    "iters": run.get("iteration_count", 0),
                    "cost_usd": round(float(run.get("total_cost_usd", 0.0) or 0.0), 4),
                    "readiness": run.get("ship_readiness", ""),
                    "verification": run.get("verification_status", ""),
                }
                for run in recent
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No runs recorded yet.")

with explorer_tab:
    st.markdown("#### Run Explorer")
    if not runs:
        st.caption("No run history available yet.")
    else:
        filter_cols = st.columns([1.2, 1, 1, 1.4])
        mode_filter = filter_cols[0].selectbox(
            "Task mode",
            ["All"] + sorted({str(run.get("task_mode", "Unknown") or "Unknown") for run in runs}),
            index=0,
        )
        readiness_filter = filter_cols[1].selectbox(
            "Readiness",
            ["All"] + sorted({str(run.get("ship_readiness", "UNASSESSED") or "UNASSESSED") for run in runs}),
            index=0,
        )
        verification_filter = filter_cols[2].selectbox(
            "Verification",
            ["All"] + sorted({str(run.get("verification_status", "UNVERIFIED") or "UNVERIFIED") for run in runs}),
            index=0,
        )
        search_text = filter_cols[3].text_input("Search runs", placeholder="Run ID, task mode, benchmark title...")

        filtered_runs = filter_runs(
            runs,
            mode_filter=mode_filter,
            readiness_filter=readiness_filter,
            verification_filter=verification_filter,
            search_text=search_text,
        )
        st.caption(f"{len(filtered_runs)} runs match the current filters.")
        st.dataframe(
            [
                {
                    "run_id": run.get("id", ""),
                    "created_at": run.get("created_at", ""),
                    "task_mode": run.get("task_mode", ""),
                    "best_score": run.get("best_score", 0.0),
                    "iteration_count": run.get("iteration_count", 0),
                    "total_cost_usd": round(float(run.get("total_cost_usd", 0.0) or 0.0), 4),
                    "ship_readiness": run.get("ship_readiness", ""),
                    "verification_status": run.get("verification_status", ""),
                    "stop_reason": run.get("stop_reason", ""),
                }
                for run in filtered_runs
            ],
            use_container_width=True,
            hide_index=True,
        )

        labels = [
            f"{run.get('id', 'run')} · {run.get('task_mode', 'Unknown')} · score {run.get('best_score', 0.0)}"
            for run in filtered_runs
        ]
        if labels:
            selected_label = st.selectbox("Inspect run", labels)
            selected_run = filtered_runs[labels.index(selected_label)]
            summary_cards(
                [
                    ("Run ID", selected_run.get("id", "")),
                    ("Readiness", selected_run.get("ship_readiness", "")),
                    ("Verification", selected_run.get("verification_status", "")),
                    ("Cost", f"${float(selected_run.get('total_cost_usd', 0.0) or 0.0):.4f}"),
                ]
            )
            summary_cards(
                [
                    ("Iterations", selected_run.get("iteration_count", 0)),
                    ("Stop Reason", selected_run.get("stop_reason", "") or "n/a"),
                    ("Validity", selected_run.get("validity_status", "") or "unknown"),
                    ("Source", runs_source.upper()),
                ]
            )
            metadata = dict(selected_run.get("run_metadata", {}) or {})
            with st.expander("Input and Metadata", expanded=False):
                st.markdown("**Input**")
                user_input = truncate_text(selected_run.get("user_input", "") or metadata.get("task", ""), limit=600)
                st.write(user_input or "Full user input was not stored for this run source.")
                if metadata:
                    st.markdown("**Run Metadata**")
                    st.json(metadata)
            with st.expander("Solution", expanded=False):
                solution = str(selected_run.get("best_solution", "") or "").strip()
                st.write(solution or "Detailed solution text is only available when persistence is enabled for full runs.")
            model_usage = list(metadata.get("model_usage", []) or [])
            if model_usage:
                st.markdown("#### Model Usage")
                st.dataframe(model_usage, use_container_width=True, hide_index=True)
            iterations = load_run_iterations(selected_run.get("id", ""))
            if iterations:
                st.markdown("#### Iteration Breakdown")
                st.dataframe(iterations, use_container_width=True, hide_index=True)
            else:
                st.caption("Detailed iteration history is not available yet for this data source.")

with analytics_tab:
    st.markdown("#### Score Trends")
    trend_rows = [
        {
            "created_at": run.get("created_at", ""),
            "best_score": float(run.get("best_score", 0.0) or 0.0),
            "task_mode": run.get("task_mode", ""),
            "total_cost_usd": float(run.get("total_cost_usd", 0.0) or 0.0),
        }
        for run in runs
    ]
    render_plotly_or_table("Score Over Time", trend_rows, x="created_at", y="best_score", chart_type="line")
    render_plotly_or_table(
        "Score Distribution by Task Mode",
        [
            {"task_mode": row["task_mode"], "avg_score": row["mean"]}
            for row in benchmark_stats_table(runs)
        ],
        x="task_mode",
        y="avg_score",
    )
    render_plotly_or_table("Cost vs Quality", trend_rows, x="total_cost_usd", y="best_score", chart_type="scatter")
    render_plotly_or_table(
        "Iteration Count by Task Mode",
        [
            {"task_mode": row["task_mode"], "avg_iterations": round(mean(
                float(run.get("iteration_count", 0) or 0)
                for run in runs
                if str(run.get("task_mode", "Unknown") or "Unknown") == row["task_mode"]
            ), 2)}
            for row in benchmark_stats_table(runs)
        ],
        x="task_mode",
        y="avg_iterations",
    )

    architect_rows, latency_rows = model_comparison_rows(runs)
    left, right = st.columns(2)
    with left:
        render_plotly_or_table("Avg Score by Architect Model", architect_rows, x="architect_model", y="avg_score")
    with right:
        render_plotly_or_table("Avg Latency by Model", latency_rows, x="model", y="avg_latency_ms")

    st.markdown("#### Cost per Quality Point by Model")
    if latency_rows:
        st.dataframe(latency_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("Model usage details become richer once persistence is enabled and more runs are stored.")

with benchmarks_tab:
    summary_cards(
        [
            ("Runs", benchmark_stats.get("count", 0)),
            ("Avg Score", benchmark_stats.get("avg_score", 0.0)),
            ("Avg Cost", f"${benchmark_stats.get('avg_cost', 0.0):.4f}"),
            ("Ready Rate", f"{benchmark_stats.get('ready_rate', 0.0)}%"),
        ]
    )

    stats_rows = benchmark_stats_table(runs)
    st.markdown("#### Benchmark Statistics by Task Mode")
    if stats_rows:
        st.dataframe(stats_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No benchmark history is available yet.")

    strategy_rows = benchmark_strategy_rows(runs)
    st.markdown("#### Strategy Comparison")
    if strategy_rows:
        st.dataframe(strategy_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No benchmark strategy labels are available yet.")

    readiness_breakdown = {}
    for run in runs:
        readiness = str(run.get("ship_readiness", "UNASSESSED") or "UNASSESSED")
        readiness_breakdown[readiness] = readiness_breakdown.get(readiness, 0) + 1

    if readiness_breakdown:
        st.markdown("#### Ship Readiness Breakdown")
        rows = [{"ship_readiness": key, "count": value} for key, value in readiness_breakdown.items()]
        if px is not None:
            fig = px.pie(rows, values="count", names="ship_readiness")
            fig.update_layout(paper_bgcolor="#ffffff", font_color="#171717")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart({row["ship_readiness"]: row["count"] for row in rows})

    col_csv, col_json = st.columns(2)
    col_csv.download_button(
        "Download CSV",
        data=export_csv_text(runs),
        file_name="the_arbiter_runs.csv",
        mime="text/csv",
        use_container_width=True,
    )
    col_json.download_button(
        "Download JSON",
        data=json.dumps(runs, ensure_ascii=False, indent=2),
        file_name="the_arbiter_runs.json",
        mime="application/json",
        use_container_width=True,
    )

with system_tab:
    summary_cards(
        [
            ("Version", __version__),
            ("SQLAlchemy", "READY" if sqlalchemy_available() else "MISSING"),
            ("Database Enabled", "YES" if database_enabled() else "NO"),
            ("Memory Backend", memory_stats.get("backend", "native")),
            ("Eval Fixtures", count_eval_fixtures()),
        ]
    )
    provider_rows = provider_catalog_rows(registry)
    if provider_rows:
        st.markdown("#### Provider Catalog Status")
        st.dataframe(provider_rows, use_container_width=True, hide_index=True)

    alias_rows = [
        {"alias": alias, "resolved_model": target or "unresolved"}
        for alias, target in sorted(registry.aliases().items())
    ]
    if alias_rows:
        st.markdown("#### Stable Alias Resolution")
        st.dataframe(alias_rows, use_container_width=True, hide_index=True)
    st.markdown("#### System Notes")
    st.markdown(
        "- The dashboard reads from the database first when DB persistence is enabled.\n"
        "- When DB dependencies are missing, it falls back to the current benchmark store.\n"
        "- Detailed iteration drill-down and model usage are richest when database persistence is active.\n"
        "- The main Streamlit product UI is unchanged; this page is intentionally separate.\n"
        "- Optional features remain degradable by design, so this surface reflects what is actually available in the current install."
    )
