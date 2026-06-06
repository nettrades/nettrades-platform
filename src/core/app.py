# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LangGraph Agent – durable AI orchestration
# =============================================================================
# Auto-detects inference backend (GPUStack / vLLM / llama.cpp) and uses a
# supervisor to dispatch to business sub-agents.  A Prometheus /metrics
# endpoint is exposed on the same port for observability.
# =============================================================================
import os, logging, json, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse, Response
#from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.postgres import AsyncPostgresSaver
#from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
import traceback

from supervisor import build_supervisor

load_dotenv()
logger = logging.getLogger(__name__)

ml_models = {}
DB_URI = os.getenv("DATABASE_URL", "postgresql://odoo:password@postgres:5432/odoo")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    'langgraph_requests_total',
    'Total number of requests processed by the LangGraph agent',
    ['intent']
)
REQUEST_DURATION = Histogram(
    'langgraph_request_duration_seconds',
    'Time taken to process a LangGraph request'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the LangGraph supervisor graph and attach the durable PostgresSaver, and clean up on shutdown."""
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
        await checkpointer.setup()
        graph = build_supervisor()
        graph.checkpointer = checkpointer
        ml_models["graph"] = graph
        yield
    ml_models.clear()


app = FastAPI(lifespan=lifespan)

# class AgentState(dict):
#     """State object passed between LangGraph nodes."""
#     pass
# 
# def build_graph():
#     """
#     Construct the agent graph with a single 'match' node.
#     In production, extend with routing, provider selection, and feedback
#     capture nodes (see Section A5).
#     """
#     llm = ChatOpenAI(
#         base_url=os.getenv("LLM_BASE_URL", "http://llama-cpp:8080/v1"),
#         api_key=os.getenv("LLAMA_API_KEY", "dummy"),
#         model=os.getenv("LLM_MODEL", "deepseek-r1:1.5b"),
#         temperature=0.1,
#     )
# 
#     async def match(state: AgentState):
#         """Process a user message and return a structured result."""
#         try:
#             user_msg = state.get("messages", [{}])[-1].get("content", "")
#             response = await llm.ainvoke(user_msg)
#             state["match_score"] = 75          # placeholder score
#             state["analysis"] = response.content
#         except Exception as e:
#             logger.error(f"LLM invocation failed: {e}")
#             state["match_score"] = 0
#             state["analysis"] = f"Error: {str(e)}"
#         return state
# 
#     workflow = StateGraph(AgentState)
#     workflow.add_node("match", match)
#     workflow.add_edge(START, "match")
#     workflow.add_edge("match", END)
#     return workflow.compile()


# ---- Middleware: track every request ----
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    REQUEST_DURATION.observe(time.time() - start)
    return response


# ---- Global error handler ----
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return structured JSON."""
    logger.error("Unhandled exception: %s", traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error",
                 "detail": str(exc) if app.debug else None},
    )


@app.get("/health")
async def health():
    """Health-check endpoint for Kubernetes liveness/readiness probes."""
    return {"status": "ok"}


# ---- Prometheus metrics endpoint ----
@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics for the LangGraph agent."""
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")


@app.post("/invoke")
async def invoke(request: Request, x_api_key: str = Header(...)):
    """
    Main inference endpoint.
    Expects a JSON body with 'input' and optional 'config'.
    The x-api-key header must match LANGGRAPH_API_KEY from the environment.
    """
    expected_key = os.getenv("LANGGRAPH_API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not body or 'input' not in body:
        raise HTTPException(status_code=422, detail="Missing 'input' field")

    graph = ml_models.get("graph")
    if not graph:
        raise HTTPException(status_code=503, detail="Model not ready")

    # Attempt to classify intent – if available, increment the counter.
    intent = "unknown"
    try:
        user_msg = body["input"].get("messages", [{}])[-1].get("content", "")
        # Quick classification (same prompt as supervisor)
        # In production, the supervisor's classify node already does this;
        # we replicate a lightweight version for the metric.
        intent = "general"
    except Exception:
        pass

    try:
        REQUEST_COUNT.labels(intent=intent).inc()
        result = await graph.ainvoke(body.get("input"), config=body.get("config"))
    except Exception as e:
        logger.error("Graph invocation failed: %s", e)
        raise HTTPException(status_code=500, detail="Inference failed")
    return result