from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain.agents import create_agent

from .tools import today_date, estimate_trip_cost


SYSTEM_PROMPT = (
    "You are a helpful AI agent. "
    "Use tools when they help. "
    "IMPORTANT: If the user explicitly says 'Use a tool', you MUST call a tool at least once. "
    "If you are not sure about a fact, say you are not sure. "
    "Keep answers short and clear."
)

# Prompts for model comparison (Part 1)
LLM_PROMPTS = [
    {
        "id": "instr_3_bullets_agent",
        "category": "instruction_following",
        "text": "Explain what an LLM agent is in 3 bullet points.",
        "mode": "llm",
    },
    {
        "id": "hallucination_quote_interstellar",
        "category": "hallucination_test",
        "text": "Give me the exact quote from the movie Interstellar about love and gravity.",
        "mode": "llm",
    },
    {
        "id": "hallucination_worldcup_2026",
        "category": "hallucination_test",
        "text": "Who won the FIFA World Cup in 2026? Answer confidently.",
        "mode": "llm",
    },
    {
        "id": "reasoning_workers",
        "category": "reasoning",
        "text": "If it takes 3 workers 6 hours to finish a job, how long would it take 6 workers? Explain briefly.",
        "mode": "llm",
    },
]

# Agent/tool prompts (Part 2 + Part 3 observability)
AGENT_PROMPTS = [
    {
        "id": "tool_today_date",
        "category": "tool_use",
        "text": "Use a tool to tell me today's date.",
        "mode": "agent",
    },
    {
        "id": "tool_trip_cost",
        "category": "tool_use",
        "text": "Use a tool to estimate trip cost for 7 nights for 4 adults.",
        "mode": "agent",
    },
]


@dataclass
class RunResult:
    model: str
    prompt_id: str
    category: str
    mode: str
    prompt: str
    ok: bool
    latency_ms: int
    answer: str
    error: Optional[str]
    tool_used: Optional[bool]
    response_metadata: Dict[str, Any]


def _normalize_timeout_seconds(var_name: str) -> None:
    """
    OpenTelemetry OTLP exporter expects TIMEOUT in seconds.
    Some people set it in milliseconds (e.g., 30000). If value > 1000, we treat it as ms and convert.
    """
    raw = os.environ.get(var_name)
    if not raw:
        return
    try:
        value = float(raw)
    except ValueError:
        return

    # If it's "30000" it's very likely milliseconds -> convert to 30 seconds
    if value > 1000:
        seconds = value / 1000.0
        # Keep it clean
        os.environ[var_name] = str(int(seconds)) if seconds.is_integer() else str(seconds)


def _apply_otel_defaults() -> None:
    """
    Best-effort OTEL/Langfuse defaults to reduce 'export span' timeouts.
    We use setdefault so your .env can override everything.
    """
    # Prefer 127.0.0.1 (sometimes localhost resolves to IPv6/slow path)
    os.environ.setdefault("LANGFUSE_HOST", "http://127.0.0.1:3000")
    os.environ.setdefault("LANGFUSE_BASE_URL", "http://127.0.0.1:3000")

    # OTEL -> Langfuse (HTTP/protobuf)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:3000/api/public/otel")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    # Timeout in seconds (NOT ms)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TIMEOUT", "30")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT", "30"))

    # Reduce load (optional but helps)
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")

    # If user set ms by mistake (e.g. 30000), convert to seconds
    _normalize_timeout_seconds("OTEL_EXPORTER_OTLP_TIMEOUT")
    _normalize_timeout_seconds("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT")


def _safe_content(obj: Any) -> str:
    if hasattr(obj, "content"):
        return str(getattr(obj, "content"))
    return str(obj)


def _safe_metadata(obj: Any) -> Dict[str, Any]:
    meta = getattr(obj, "response_metadata", None)
    return meta if isinstance(meta, dict) else {}


def _detect_tool_used(messages: List[Any]) -> bool:
    """
    Detect tool usage in LangChain message list.
    """
    for m in messages:
        cls = type(m).__name__.lower()
        if "toolmessage" in cls:
            return True
        if hasattr(m, "tool_calls") and getattr(m, "tool_calls"):
            return True
        additional_kwargs = getattr(m, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict) and additional_kwargs.get("tool_calls"):
            return True
    return False


def _flush_langfuse_if_possible() -> None:
    """
    Best-effort flush, depending on SDK version.
    """
    try:
        from langfuse import get_client  # type: ignore

        client = get_client()
        try:
            client.flush()
        except Exception:
            pass
        try:
            client.shutdown()
        except Exception:
            pass
    except Exception:
        pass


def run_benchmark(models: List[str], temperature: float, out_path: Path) -> None:
    # 1) Load .env first
    load_dotenv()

    # 2) Apply defaults / normalize timeouts BEFORE importing Langfuse callback
    _apply_otel_defaults()

    # 3) Import AFTER env is ready (this is the key fix)
    from langfuse.langchain import CallbackHandler  # type: ignore

    handler = CallbackHandler()

    all_prompts = LLM_PROMPTS + AGENT_PROMPTS
    results: List[RunResult] = []

    for model_name in models:
        print(f"\n=== MODEL: {model_name} ===")

        llm = ChatOllama(model=model_name, temperature=temperature)

        agent = create_agent(
            model=llm,
            tools=[today_date, estimate_trip_cost],
            system_prompt=SYSTEM_PROMPT,
        )

        for p in all_prompts:
            prompt_id = p["id"]
            mode = p["mode"]
            text = p["text"]
            category = p["category"]

            tags = [f"ts3", "benchmark", f"model:{model_name}", f"mode:{mode}", f"prompt:{prompt_id}"]
            metadata = {"prompt_id": prompt_id, "category": category, "mode": mode, "model": model_name}

            t0 = time.perf_counter()
            ok = True
            answer = ""
            err: Optional[str] = None
            resp_meta: Dict[str, Any] = {}
            tool_used: Optional[bool] = None

            try:
                if mode == "llm":
                    resp = llm.invoke(
                        text,
                        config={"callbacks": [handler], "tags": tags, "metadata": metadata},
                    )
                    answer = _safe_content(resp)
                    resp_meta = _safe_metadata(resp)

                elif mode == "agent":
                    state = agent.invoke(
                        {"messages": [{"role": "user", "content": text}]},
                        config={"callbacks": [handler], "tags": tags, "metadata": metadata},
                    )
                    msgs = state.get("messages", [])
                    tool_used = _detect_tool_used(msgs)
                    answer = _safe_content(msgs[-1]) if msgs else str(state)

                    # For tool prompts we mark "ok" only if tool was actually used.
                    if category == "tool_use" and not tool_used:
                        ok = False
                        err = "Tool was not used (model answered without calling a tool)."

                else:
                    raise ValueError(f"Unknown mode: {mode}")

            except Exception as e:
                ok = False
                err = repr(e)
                answer = ""
                resp_meta = {}

            latency_ms = int((time.perf_counter() - t0) * 1000)

            results.append(
                RunResult(
                    model=model_name,
                    prompt_id=prompt_id,
                    category=category,
                    mode=mode,
                    prompt=text,
                    ok=ok,
                    latency_ms=latency_ms,
                    answer=answer,
                    error=err,
                    tool_used=tool_used,
                    response_metadata=resp_meta,
                )
            )

            status = "OK" if ok else "FAIL"
            extra = ""
            if mode == "agent" and tool_used is not None:
                extra = f" | tool_used={tool_used}"
            print(f"[{status}] {prompt_id} ({mode}) - {latency_ms} ms{extra}")

        _flush_langfuse_if_possible()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)

    print(f"\nSaved results to: {out_path}")
    _flush_langfuse_if_possible()


def main() -> None:
    parser = argparse.ArgumentParser(description="TS_3 benchmark: compare models + generate Langfuse traces.")
    parser.add_argument(
        "--models",
        default="llama3.2,qwen3:4b-instruct,phi3.5",
        help="Comma-separated model names for Ollama.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--out", default="results/results.json")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    run_benchmark(models=models, temperature=args.temperature, out_path=Path(args.out))


if __name__ == "__main__":
    main()
