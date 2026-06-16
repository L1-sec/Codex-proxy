import sys
import os
import json
import uuid
import queue
import logging
import threading
import time
import traceback
from datetime import datetime

import httpx
from flask import Flask, request, Response
from openai import OpenAI

# ===================== 配置（直接修改此处） =====================
# API 配置
API_KEY = "sk-********************************************"  # 替换为API Key
MODEL = "deepseek-v4-flash"  # 默认模型
BASE_URL = "https://token.sensenova.cn/v1"

#API_KEY = "nvapi-*************************************"  # 替换为API Key
#MODEL = "mistralai/mistral-nemotron"  # 默认模型
#BASE_URL = "https://integrate.api.nvidia.com/v1"

# 服务配置
HOST = "127.0.0.1"
PORT = 6000
THREADS = 12
DEBUG = False  # 设为 True 开启调试日志

# ===================== 日志配置 =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_LOG = os.path.join(BASE_DIR, "proxy_debug.log")


class _Fmt(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created))},{int(record.msecs):03d}"

_fmt = _Fmt('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_h = logging.StreamHandler()
_h.setFormatter(_fmt)
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO, handlers=[_h], force=True)

logger = logging.getLogger('proxy')

app = Flask(__name__)

_client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
    timeout=httpx.Timeout(600.0, connect=30.0, read=600.0),
)


@app.before_request
def _log_req():
    if request.method == 'POST':
        logger.info(f"\u2192 {request.path}")


@app.after_request
def _log_res(response):
    if request.method == 'POST':
        logger.info(f"\u2190 {response.status_code}")
    return response


# ===================== 工具函数 =====================
def _clean_schema(obj):
    """清理 JSON Schema，移除API 不支持的字段"""
    if not isinstance(obj, dict):
        return obj
    cleaned = {}
    for k, v in obj.items():
        if k in ("additionalProperties", "strict"):
            continue
        if isinstance(v, dict):
            cleaned[k] = _clean_schema(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_schema(i) if isinstance(i, dict) else i for i in v]
        else:
            cleaned[k] = v
    return cleaned


def _convert_tools(tools: list) -> list:
    """将 Responses API 的 tools 格式转换为 Chat Completions 格式"""
    result = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            continue
        func = {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
        }
        if "parameters" in tool:
            func["parameters"] = _clean_schema(tool["parameters"])
        result.append({"type": "function", "function": func})
    return result


def _convert_tool_choice(tc):
    """转换 tool_choice 参数"""
    if tc is None:
        return "auto"
    if isinstance(tc, str):
        return tc
    if isinstance(tc, dict) and tc.get("type") == "function":
        return {"type": "function", "function": {"name": tc.get("name", "")}}
    return "auto"


def _estimate_tokens(text):
    """粗略估算 token 数量"""
    return max(1, len(text) // 4)


def _log_debug(messages, tools=None):
    """写入调试日志"""
    if not DEBUG:
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n--- [{datetime.now()}] ---\n")
            f.write(f"Messages:\n{json.dumps(messages, indent=2, ensure_ascii=False)}\n")
            if tools:
                f.write(f"Tools count: {len(tools)}\n")
    except Exception as e:
        logger.exception(f"写入调试日志失败")


# ===================== 消息提取 =====================
def extract_messages(data: dict):
    """
    从 Responses API 请求中提取 messages 列表、tools 列表和 tool_choice。
    支持 /responses 和 /v1/chat/completions 格式。
    """
    ROLE_MAP = {"developer": "system"}
    raw_tools = data.get("tools", [])
    tools = _convert_tools(raw_tools)
    tool_choice = _convert_tool_choice(data.get("tool_choice"))

    # 如果已经有 messages 字段（Chat Completions 格式），直接返回
    if "input" not in data:
        if "messages" in data:
            return data["messages"], tools, tool_choice
        return [], tools, tool_choice

    # 处理 Responses API 的 input 格式
    inp = data["input"]
    if isinstance(inp, str):
        messages = []
        if "instructions" in data and data["instructions"]:
            messages.append({"role": "system", "content": data["instructions"]})
        messages.append({"role": "user", "content": inp})
        return messages, tools, tool_choice

    if not isinstance(inp, list):
        return [], tools, tool_choice

    messages = []
    if "instructions" in data and data["instructions"]:
        messages.append({"role": "system", "content": data["instructions"]})

    pending_tool_calls = []
    pending_reasoning = ""

    def _flush_tool_calls():
        nonlocal pending_tool_calls, pending_reasoning
        if pending_tool_calls:
            msg = {
                "role": "assistant",
                "content": "",
                "tool_calls": pending_tool_calls,
            }
            if pending_reasoning:
                msg["reasoning_content"] = pending_reasoning
            messages.append(msg)
            pending_tool_calls = []
            pending_reasoning = ""

    for item in inp:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "message":
            _flush_tool_calls()
            role = item.get("role", "user")
            role = ROLE_MAP.get(role, role)
            content = item.get("content", "")

            if isinstance(content, list):
                texts = []
                tool_calls = []
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    c_type = c.get("type")
                    if c_type in ("text", "input_text", "output_text"):
                        t = c.get("text", "")
                        if t.strip():
                            texts.append(t)
                    elif c_type == "tool_call":
                        tool_calls.append({
                            "id": c.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": c.get("name", ""),
                                "arguments": c.get("arguments", ""),
                            }
                        })

                text_content = "\n".join(texts)
                if tool_calls:
                    msg = {"role": role, "content": text_content or ""}
                    msg["tool_calls"] = tool_calls
                    messages.append(msg)
                elif text_content:
                    msg = {"role": role, "content": text_content}
                    messages.append(msg)
            elif isinstance(content, str) and content.strip():
                msg = {"role": role, "content": content.strip()}
                messages.append(msg)

        elif item_type == "function_call":
            pending_tool_calls.append({
                "id": item.get("call_id", ""),
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", ""),
                }
            })

        elif item_type == "function_call_output":
            _flush_tool_calls()
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })

    _flush_tool_calls()

    # 重排消息，确保 tool 消息紧跟在对应的 assistant 消息后面
    reordered = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            expected_ids = {tc["id"] for tc in msg["tool_calls"]}
            tool_msgs = []
            non_tool_msgs = []
            j = i + 1
            while j < len(messages) and expected_ids:
                nxt = messages[j]
                if nxt.get("role") == "tool" and nxt.get("tool_call_id") in expected_ids:
                    expected_ids.remove(nxt["tool_call_id"])
                    tool_msgs.append(nxt)
                elif nxt.get("role") in ("system", "developer"):
                    non_tool_msgs.append(nxt)
                else:
                    break
                j += 1
            reordered.extend(non_tool_msgs)
            reordered.append(msg)
            reordered.extend(tool_msgs)
            i = j
        else:
            reordered.append(msg)
            i += 1

    return reordered, tools, tool_choice


# ===================== 路由处理 =====================
@app.after_request
def add_cors(resp):
    """添加 CORS 头"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp


def _make_response():
    """处理所有 API 请求"""
    if request.method == "OPTIONS":
        return Response()

    req_data = request.get_json(silent=True) or {}
    messages, tools, tool_choice = extract_messages(req_data)
    effective_model = MODEL
    response_id = f"resp_{uuid.uuid4().hex[:12]}"

    _log_debug(messages, tools)

    def generate():
        # ========== 基于线程的流式处理（支持上游卡住时发心跳） ==========
        KEEPALIVE_INTERVAL = 8  # 秒

        chunk_queue = queue.Queue(maxsize=500)
        stop_event = threading.Event()

        # ---- 上游数据拉取线程 ----
        def upstream_worker():
            try:
                kwargs = {
                    "model": effective_model,
                    "messages": messages,
                    "stream": True,
                }
                if tools:
                    kwargs["tools"] = tools
                    if tool_choice != "auto":
                        kwargs["tool_choice"] = tool_choice

                stream = _client.chat.completions.create(**kwargs)
                for chunk in stream:
                    if stop_event.is_set():
                        stream.close()
                        return
                    chunk_queue.put(("chunk", chunk))
                chunk_queue.put(("done", None))
            except Exception as e:
                chunk_queue.put(("error", e))

        # ---- 心跳线程 ----
        def ping_worker():
            while not stop_event.is_set():
                if stop_event.wait(KEEPALIVE_INTERVAL):
                    return
                try:
                    chunk_queue.put(("ping", None), timeout=1)
                except queue.Full:
                    pass

        # ---- 主处理逻辑 ----
        def process_upstream():
            text_item_id = f"item_{uuid.uuid4().hex[:12]}"
            full_text = ""
            has_text = False
            text_started = False
            tool_calls_acc = {}
            input_tokens = 0
            output_tokens = 0
            seq = 0
            stream_done = False

            t_up = threading.Thread(target=upstream_worker, daemon=True)
            t_ping = threading.Thread(target=ping_worker, daemon=True)
            t_up.start()
            t_ping.start()

            try:
                while not stream_done:
                    try:
                        msg_type, data = chunk_queue.get(timeout=60)
                    except queue.Empty:
                        yield _make_ping()
                        continue

                    if msg_type == "ping":
                        yield _make_ping()
                        continue

                    if msg_type == "done":
                        stream_done = True
                        break

                    if msg_type == "error":
                        raise data

                    # msg_type == "chunk"
                    chunk = data

                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens or 0
                        output_tokens = chunk.usage.completion_tokens or 0

                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue

                    delta = choice.delta

                    if delta.content:
                        if not text_started:
                            text_started = True
                            has_text = True
                            for evt in _emit_text_start(text_item_id):
                                yield evt
                        full_text += delta.content
                        seq += 1
                        yield _format_sse("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "delta": delta.content,
                            "item_id": text_item_id,
                            "output_index": 0, "content_index": 0,
                            "sequence_number": seq,
                        })

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc.id or "",
                                    "name": "",
                                    "arguments": "",
                                    "item_id": f"item_{uuid.uuid4().hex[:12]}",
                                    "started": False,
                                }
                            acc = tool_calls_acc[idx]
                            if tc.function and tc.function.name:
                                acc["name"] = tc.function.name
                            if tc.id:
                                acc["id"] = tc.id
                            if tc.function and tc.function.arguments:
                                acc["arguments"] += tc.function.arguments
                                out_idx = (1 if has_text else 0) + sorted(tool_calls_acc.keys()).index(idx)
                                if not acc["started"]:
                                    acc["started"] = True
                                    yield _format_sse("response.output_item.added", {
                                        "type": "response.output_item.added",
                                        "output_index": out_idx,
                                        "item": {
                                            "id": acc["item_id"],
                                            "type": "function_call",
                                            "status": "in_progress",
                                            "call_id": acc["id"],
                                            "name": acc["name"],
                                            "arguments": "",
                                        },
                                    })
                                yield _format_sse("response.function_call_arguments.delta", {
                                    "type": "response.function_call_arguments.delta",
                                    "item_id": acc["item_id"],
                                    "output_index": out_idx,
                                    "delta": tc.function.arguments,
                                })

                # ---- 流结束，输出最终事件 ----
                output_items = []
                if has_text:
                    for evt in _emit_text_events(text_item_id, full_text):
                        yield evt
                    output_item_text = _emit_text_done(text_item_id, full_text)
                    output_items.append(output_item_text)
                    yield _format_sse("response.output_item.done", {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": output_item_text,
                    })

                for idx in sorted(tool_calls_acc.keys()):
                    acc = tool_calls_acc[idx]
                    out_idx = (1 if has_text else 0) + sorted(tool_calls_acc.keys()).index(idx)
                    for evt in _emit_tool_call_events(acc, out_idx):
                        yield evt
                    func_item = _emit_tool_call_done(acc, out_idx)
                    output_items.append(func_item)
                    yield _format_sse("response.output_item.done", {
                        "type": "response.output_item.done",
                        "output_index": out_idx,
                        "item": func_item,
                    })

                yield _format_sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": response_id, "object": "response",
                        "status": "completed", "model": effective_model,
                        "output": output_items,
                        "usage": {
                            "input_tokens": input_tokens or _estimate_tokens(json.dumps(messages)),
                            "output_tokens": output_tokens or _estimate_tokens(full_text),
                            "total_tokens": (input_tokens or _estimate_tokens(json.dumps(messages)))
                                            + (output_tokens or _estimate_tokens(full_text)),
                        },
                    },
                })

            finally:
                stop_event.set()

        # ---- 入口 ----
        try:
            if not messages:
                yield _format_sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": response_id, "object": "response",
                        "status": "completed", "model": effective_model,
                        "output": [], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    },
                })
                return

            yield _format_sse("response.created", {
                "type": "response.created",
                "response": {
                    "id": response_id, "object": "response",
                    "status": "in_progress", "model": effective_model,
                    "output": [], "usage": None,
                },
            })
            yield _format_sse("response.in_progress", {
                "type": "response.in_progress",
                "response": {
                    "id": response_id, "object": "response",
                    "status": "in_progress", "model": effective_model,
                    "output": [], "usage": None,
                },
            })

            yield from process_upstream()

        except GeneratorExit:
            logger.info("客户端断开连接，生成器退出")
        except Exception as e:
            err_msg = f"API error: {type(e).__name__}: {e}"
            logger.exception(err_msg)
            try:
                yield _format_sse("response.failed", {
                    "type": "response.failed",
                    "response": {
                        "id": response_id, "object": "response",
                        "status": "failed", "model": effective_model,
                        "error": {"message": err_msg, "type": "upstream_error"},
                        "output": [], "usage": None,
                    },
                })
            except GeneratorExit:
                pass

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ===================== SSE 辅助函数 =====================
def _format_sse(event_name, data):
    """格式化 SSE 事件"""
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _make_ping():
    """发送心跳保持连接"""
    return ": keepalive\n\n"


def _emit_text_start(text_item_id):
    """发送文本开始事件"""
    yield _format_sse("response.output_item.added", {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "id": text_item_id, "type": "message",
            "status": "in_progress", "role": "assistant",
            "content": [],
        },
    })
    yield _format_sse("response.content_part.added", {
        "type": "response.content_part.added",
        "item_id": text_item_id,
        "output_index": 0, "content_index": 0,
        "part": {"type": "text", "text": ""},
    })


def _emit_text_events(text_item_id, full_text):
    """发送文本完成事件"""
    yield _format_sse("response.output_text.done", {
        "type": "response.output_text.done",
        "text": full_text, "item_id": text_item_id,
        "output_index": 0, "content_index": 0,
    })
    yield _format_sse("response.content_part.done", {
        "type": "response.content_part.done",
        "item_id": text_item_id,
        "output_index": 0, "content_index": 0,
        "part": {"type": "text", "text": full_text},
    })


def _emit_text_done(text_item_id, full_text):
    """获取文本完成项数据"""
    output_item = {
        "id": text_item_id, "type": "message",
        "status": "completed", "role": "assistant",
        "content": [{"type": "text", "text": full_text}],
    }
    return output_item


def _emit_tool_call_events(acc, out_idx):
    """发送工具调用完成事件"""
    yield _format_sse("response.function_call_arguments.done", {
        "type": "response.function_call_arguments.done",
        "item_id": acc["item_id"],
        "output_index": out_idx,
        "arguments": acc["arguments"],
    })


def _emit_tool_call_done(acc, out_idx):
    """获取工具调用完成项数据"""
    func_item = {
        "id": acc["item_id"],
        "type": "function_call",
        "status": "completed",
        "call_id": acc["id"],
        "name": acc["name"],
        "arguments": acc["arguments"],
    }
    return func_item


# ===================== 注册路由 =====================
app.add_url_rule("/responses", "responses", _make_response, methods=["POST", "OPTIONS"])
app.add_url_rule("/v1/responses", "v1_responses", _make_response, methods=["POST", "OPTIONS"])
app.add_url_rule("/v1/chat/completions", "v1_chat", _make_response, methods=["POST", "OPTIONS"])

# ===================== 主程序 =====================
if __name__ == "__main__":
    from waitress import serve

    logger.info(f"Proxy started \u2192 http://{HOST}:{PORT} | model={MODEL} | debug={DEBUG} | threads={THREADS}")

    serve(app, host=HOST, port=PORT, threads=THREADS)
