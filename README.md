# REPORT (EN)

## TS_3 — Lightweight LLM Benchmark + Tool-Using Agent + Observability (Langfuse)

**Author:** Mubarakov Islam (Group: 11-314a)

**Repo:** Machine-Learning-Task-Series-3

**Platform:** macOS + PyCharm

**LLM runtime:** Ollama (local)

**Agent framework:** LangChain-style chat + tool calling

**Observability:** Langfuse (self-hosted via Docker) + OpenTelemetry traces

---

## Project structure (high level)

* `agent/benchmark.py` — runs the benchmark suite across multiple models and saves `results.json`
* `agent/main.py` — minimal tool-using agent (chat loop / entry point)
* `agent/tools.py` — deterministic tools (date, trip cost estimation)
* `results/results.json` — benchmark outputs used for analysis
* `.env.example` — environment template
* `.env` — local secrets (NOT committed)

---

# Part 1 — Benchmarking lightweight LLMs

## Goal

Deploy several lightweight LLMs locally, test important characteristics, and justify which model should be used as the **agent model**.

## Models tested (Ollama)

* `llama3.2`
* `qwen3:4b-instruct`
* `phi3.5`

## What we test (prompts) and why

We use 6 prompts split into two modes:

### A) LLM mode (direct LLM call)

1. **Instruction following**: “Explain what an LLM agent is in 3 bullet points.”
   *Checks constraint following and formatting consistency.*

2. **Hallucination test (exact quote pressure)**: Interstellar quote request.
   *Checks if the model invents verbatim quotes instead of refusing/qualifying.*

3. **Hallucination test (future fact pressure)**: “Who won the FIFA World Cup in 2026?”
   *Checks if model fabricates unknown/future facts.*

4. **Reasoning**: worker/time proportional reasoning task.
   *Checks basic logical accuracy and coherence.*

### B) Agent mode (must use tools)

5. **Tool-use required**: “What is today’s date? Use a tool.”
   *Checks whether the agent calls tools instead of guessing.*

6. **Tool-use required**: “Estimate trip cost for N nights for M adults. Use a tool.”
   *Checks deterministic tool calling + correct structured behavior.*

## Offline metrics collected (this repo)

* **Latency (ms)** per prompt per model
* **Success rate** (`ok=True/False`)
* **Tool usage** for agent prompts (`tool_used=True` expected)
* **Token metadata** (from Ollama response metadata) and approximate **tokens/sec**

## Benchmark results summary (from results.json)

### Overall pass rate

* **llama3.2**: 6/6 passed (100%)
* **qwen3:4b-instruct**: 6/6 passed (100%)
* **phi3.5**: 4/6 passed (66.7%) — **tool prompts failed**

### Latency (high-level)

* **llama3.2**

  * Avg latency: ~4.7s, median ~2.8s, p95 ~11.9s
* **qwen3:4b-instruct**

  * Avg latency: ~16.0s, median ~10.6s, p95 ~32.2s
  * Notably slow on the tool-date request (~33s in this run)
* **phi3.5**

  * Avg latency: ~21.5s (skewed by very slow “Interstellar quote” prompt ~86s)
  * Tool prompts failed quickly with an explicit tool-support error

### Tool-use success (agent prompts)

* **llama3.2**: 2/2 tool prompts succeeded (`tool_used=True`)
* **qwen3:4b-instruct**: 2/2 tool prompts succeeded (`tool_used=True`)
* **phi3.5**: 0/2 tool prompts succeeded
  Error: `... does not support tools`

### Token throughput (approx., from Ollama metadata)

* **llama3.2**: ~34 tokens/sec
* **qwen3:4b-instruct**: ~22 tokens/sec
* **phi3.5**: ~18 tokens/sec

## Decision: chosen agent model

✅ **Chosen model for the agent: `llama3.2`**

**Why:**

* 100% success across all tests
* Reliable tool calling
* Best latency profile among the models tested
  `qwen3:4b-instruct` is valid but significantly slower on some prompts.
  `phi3.5` cannot be used for tool-using agent prompts in this setup.

---

# Part 2 — AI Agent specification + metrics + vulnerabilities

## Agent specification (brief)

**Process automated:** answering user requests and invoking deterministic tools when the user explicitly requires tool usage (e.g., date, cost estimation).

**Inputs:** user message (text)
**Outputs:** assistant response (text)
**Constraints:** local execution (Ollama), no external web browsing in the agent flow, deterministic tools, safe handling of secrets (keys in `.env` only).

## Tools implemented (deterministic)

Implemented in `agent/tools.py`:

* `today_date()` → returns today’s date
* `estimate_trip_cost(nights, adults)` → returns an estimated total cost (simple deterministic formula/logic)

## Agent behavior

* For normal questions: answer directly using the LLM.
* When the prompt includes “Use a tool”: the agent must call the appropriate tool and use the tool output in the final answer.
* The benchmark verifies this by checking `tool_used=True` on agent-mode prompts.

## Evaluation metrics (for model/agent quality)

### Offline / benchmark metrics (implemented)

* latency per prompt/model
* runtime success rate
* tool usage success for tool-required prompts
* token metadata + approximate tokens/sec

### Production-grade metrics (recommended)

* tool error rate (timeouts, wrong args, failed calls)
* invalid output rate (bad formatting/JSON if required)
* hallucination rate (manual labeling or judge model)
* tool precision/recall (called when needed vs unnecessary tool calls)
* p95/p99 latency, throughput, GPU/CPU utilization
* user satisfaction / resolution rate (if deployed)

## Vulnerabilities and mitigations

### 1) Prompt/tool injection

**Risk:** user tries to manipulate the agent into unsafe tool calls or leaking secrets.
**Mitigation:** strict tool schema, input validation, allowlist tools, never expose `.env` keys, system rules.

### 2) Hallucinations

**Risk:** model outputs confident false facts/quotes.
**Mitigation:** force tools/RAG for factual tasks, add verification step, refusal rules for “exact quote” requests without sources.

### 3) Sensitive data leakage via traces

**Risk:** observability tools store prompts/responses.
**Mitigation:** do not log secrets, redact PII, restrict Langfuse access, do not commit `.env`.

### 4) DoS / timeouts

**Risk:** slow models or tracing exporter timeouts degrade performance.
**Mitigation:** per-request timeouts, model fallback, batching/queue, disable unnecessary exporters locally.

---

# Part 3 — Observability stack for LLM agents

## What is monitored in modern IT systems

* **Logs:** errors, request logs, exceptions
* **Metrics:** CPU/RAM, throughput, latency, error rate, p95/p99
* **Traces:** request flow across services, spans per component
* **Infra health:** container uptime, restarts, disk usage

## What is important specifically for LLM agents

* prompt/response versioning
* tokens in/out, tokens/sec, context length usage
* tool calls: name/args, success/fail, latency per tool
* retries, multi-step agent chains
* hallucination indicators, refusal/safety triggers
* cost per request (if paid API), latency percentiles

## Compared stack options (3 variants)

1. **Langfuse** (chosen): LLM-native UI, self-hostable, OTEL-friendly, great for agent debugging.
2. **Langtrace**: LLM observability UI, dev-friendly, but feature maturity depends on version.
3. **OpenLLMetry + classic stack (Jaeger/Prometheus/Loki/ELK)**: most flexible/vendor-neutral but needs more configuration to become “LLM-native”.

## Chosen stack and usage

✅ **Chosen:** Langfuse + OpenTelemetry traces

* Langfuse runs locally in Docker (UI: `http://localhost:3000`)
* Benchmark/agent export traces to OTEL endpoint:

  * `http://127.0.0.1:3000/api/public/otel `
* For local simplicity OTEL metrics/log exporters are disabled:

  * `OTEL_METRICS_EXPORTER=none`
  * `OTEL_LOGS_EXPORTER=none`

### Note about “Read timed out” exporter errors

During benchmarking, you may see:
`Exception while exporting Span ... Read timed out`

This typically means the tracer exporter couldn’t send spans quickly enough.
**It does NOT mean the benchmark itself failed** — the model output and local measurements are still valid.

Common fixes:

* increase exporter timeout (e.g., `OTEL_EXPORTER_OTLP_TIMEOUT=30000`)
* prefer `127.0.0.1` instead of `localhost` in OTEL endpoint/base URL
* keep OTEL logs/metrics exporters disabled locally

---

# How to run (reproducibility)

1. Pull models:

* `ollama pull llama3.2`
* `ollama pull qwen3:4b-instruct`
* `ollama pull phi3.5`

2. Start Langfuse (Docker), open UI `http://localhost:3000`, create project, generate keys.

3. Configure `.env`:

* set Langfuse keys + host
* set OTEL endpoint + timeout

4. Install dependencies:

* create venv
* install requirements

5. Run benchmark:

* `python -m agent.benchmark --models "llama3.2,qwen3:4b-instruct,phi3.5" --out results/results.json`

---

# Conclusion

We benchmarked three lightweight local LLMs and evaluated instruction-following, hallucination resistance, reasoning, and tool-using behavior. `llama3.2` achieved the best overall balance: stable success, reliable tool calling, and the lowest latency. Langfuse + OTEL tracing was used for agent observability and debugging, providing traces for each run.

---

---

# ОТЧЁТ (RU)

## TS_3 — Бенчмарк лёгких LLM + агент с инструментами + наблюдаемость (Langfuse)

**Автор:** Мубараков Ислам (Группа: 11-314a)

**Окружение:** macOS + PyCharm

**LLM:** Ollama (локально)

**Агент:** минимальный tool-using агент (LLM + tools)

**Наблюдаемость:** Langfuse (Docker) + OpenTelemetry трейсы

---

# Часть 1 — Бенчмарк моделей

## Цель

Развернуть несколько лёгких LLM локально, протестировать важные характеристики и обосновать выбор модели для агента.

## Модели

* llama3.2
* qwen3:4b-instruct
* phi3.5

## Что тестируем и зачем

6 промптов:

**LLM-режим**

1. соблюдение инструкций (3 bullet points)
2. “точная цитата” (проверка галлюцинаций)
3. “факт из будущего” (проверка галлюцинаций)
4. логическая задача (reasoning)

**AGENT-режим**
5) “какая сегодня дата? use a tool”
6) “оценка стоимости поездки: use a tool”

## Метрики (что реально измеряем)

* latency (мс)
* ok=True/False
* tool_used=True для tool-промптов
* токены/скорость (из метаданных Ollama)

## Итоги по results.json

* llama3.2: 6/6 (100%), tools 2/2, самый быстрый в среднем
* qwen3:4b-instruct: 6/6 (100%), tools 2/2, но местами сильно медленнее (например дата ~33с)
* phi3.5: 4/6 — tool-промпты падают с ошибкой “model does not support tools”

✅ **Выбор модели агента: llama3.2** (стабильно, быстро, корректно вызывает инструменты)

---

# Часть 2 — Агент + метрики + уязвимости

## Спецификация агента (кратко)

Агент автоматизирует ответы на запросы пользователя и вызывает детерминированные инструменты, когда пользователь явно требует “Use a tool”.

## Инструменты

* today_date() — возвращает дату
* estimate_trip_cost(nights, adults) — детерминированная оценка стоимости

## Метрики (для оценки моделей/агента)

**Оффлайн:** latency, ok, tool_used, токены/скорость
**Прод:** error rate, hallucination rate, tool precision/recall, p95/p99, стоимость/ресурсы, удовлетворённость пользователей

## Уязвимости и защиты

* Prompt/tool injection → allowlist tools + валидация + не светить ключи
* Галлюцинации → tools/RAG + верификация + правила отказа на “точные цитаты”
* Утечка данных в трейсы → не логировать секреты, ограничить доступ к Langfuse, .env не коммитить
* Таймауты → таймауты, fallback модель, отключение лишних OTEL exporters локально

---

# Часть 3 — Observability

## Что мониторят в IT

логи, метрики, трейсы, здоровье инфраструктуры

## Что важно для LLM-агентов

tokens/sec, tool calls, шаги агента, retries, hallucination/refusal, cost, p95/p99

## Сравнение 3 стеков

* Langfuse (выбран)
* Langtrace
* OpenLLMetry + Jaeger/Prometheus/Loki/ELK

## Реализация

Langfuse в Docker, трейсы через OTEL endpoint.
Ошибки вида “export span read timed out” — это проблема экспорта трейсов, **не провал бенчмарка**.

---

# Вывод

Сравнение показало, что llama3.2 лучше всего подходит как модель агента: стабильная работа, адекватная скорость и корректный tool-use. Langfuse позволяет удобно смотреть трейсы и отлаживать агентные цепочки.
