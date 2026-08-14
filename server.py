"""xiaoyeeat.cn 作品站：首页 / 文章 / 试用说明 / 外呼测试台。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import websockets
from dotenv import load_dotenv
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import protocol
from extract_visit_note import extract_visit_note, load_enums

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

VOLC_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
APP_ID = os.getenv("VOLC_APP_ID", "").strip()
ACCESS_KEY = os.getenv("VOLC_ACCESS_KEY", "").strip()

# O2.0 + vivi 音色；业务人设 = 链驿市场部线索校验
MODEL = "1.2.1.1"
SPEAKER = "zh_female_vv_jupiter_bigtts"
BOT_NAME = "小陈"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _load_lead() -> dict:
    path = ROOT / "leads" / "current_lead.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_system_role(lead: dict) -> str:
    sop = _read_text(ROOT / "knowledge" / "call_sop.txt")
    product = _read_text(ROOT / "knowledge" / "product_brief.txt")
    contact = lead.get("contact") or {}
    referrer = lead.get("referrer") or {}
    lead_block = (
        "（系统内部信息，勿对用户口述编号或「线索/意向度」等词）\n"
        f"内部编号：{lead.get('lead_id', '未知')}。\n"
        f"来源：{lead.get('source', '员工推荐')}。\n"
        f"推荐人：{referrer.get('dept', '')} {referrer.get('name', '李明')}；"
        f"推荐备注：{referrer.get('note', '')}。\n"
        f"联系人：{contact.get('name', '王女士')}，"
        f"{contact.get('title', '')}，"
        f"公司/店铺：{contact.get('company', '')}，"
        f"城市：{contact.get('city', '')}。\n"
        f"预筛：未发现明显无效信号，需电话确认寄件需求真实性。"
    )
    return "\n\n".join(
        part
        for part in (
            sop or "你是链驿速递市场部小陈，负责电话确认寄件需求并交接销售。",
            "【当前外呼对象】\n" + lead_block,
            product,
        )
        if part
    )


LEAD = _load_lead()
SYSTEM_ROLE = _build_system_role(LEAD)
SPEAKING_STYLE = (
    "语气专业但亲切，像市场部同事打电话核实需求；"
    "句子偏短，一次只问一件事；听完再答，不抢话。"
)
_contact_name = (LEAD.get("contact") or {}).get("name") or "您好"
_referrer_name = (LEAD.get("referrer") or {}).get("name") or "李明"
HELLO_TEXT = (
    f"喂，您好，请问是{_contact_name}吗？"
    f"我是链驿速递市场部的小陈，我们同事{_referrer_name}推荐了您这边，"
    "想跟您确认一下快递合作的事，方便说两句吗？"
)

START_SESSION = {
    "asr": {
        "audio_info": {
            "format": "pcm",
            "sample_rate": 16000,
            "channel": 1,
        },
        "extra": {
            "end_smooth_window_ms": 1200,
        },
    },
    "tts": {
        "speaker": SPEAKER,
        "audio_config": {
            "channel": 1,
            "format": "pcm_s16le",
            "sample_rate": 24000,
        },
    },
    "dialog": {
        "bot_name": BOT_NAME,
        "system_role": SYSTEM_ROLE,
        "speaking_style": SPEAKING_STYLE,
        "dialog_id": "",
        "extra": {
            "strict_audit": False,
            "input_mod": "keep_alive",
            "model": MODEL,
        },
    },
}

WEB = ROOT / "web"
PUBLIC = ROOT / "public"
NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}
ARTICLES = {
    "lead-cleaning": WEB / "articles" / "lead-cleaning.html",
    "logistics-sales": WEB / "articles" / "logistics-sales.html",
}

app = FastAPI(title="xiaoyeeat.cn · Works")


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            path in {"/", "/lab", "/lab/", "/lab/call", "/lab/call/"}
            or path.startswith("/static/")
            or path.startswith("/assets/")
            or path.startswith("/articles/")
        ):
            for k, v in NO_CACHE.items():
                response.headers[k] = v
        return response


app.add_middleware(NoCacheStaticMiddleware)
app.mount("/static", StaticFiles(directory=PUBLIC), name="static")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(WEB / "index.html", headers=NO_CACHE)


@app.get("/articles/{slug}")
async def article(slug: str):
    path = ARTICLES.get(slug)
    if not path or not path.is_file():
        return Response("Not Found", status_code=404)
    return FileResponse(path, headers=NO_CACHE)


@app.get("/lab")
@app.get("/lab/")
async def lab_intro() -> FileResponse:
    return FileResponse(WEB / "lab" / "index.html", headers=NO_CACHE)


@app.get("/lab/call")
@app.get("/lab/call/")
async def lab_call() -> FileResponse:
    return FileResponse(PUBLIC / "index.html", headers=NO_CACHE)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": bool(APP_ID and ACCESS_KEY),
        "model": MODEL,
        "speaker": SPEAKER,
        "bot_name": BOT_NAME,
        "role": "marketing_lead_qualify",
        "lead_id": LEAD.get("lead_id"),
        "app_id_set": bool(APP_ID),
        "access_key_set": bool(ACCESS_KEY),
    }


@app.get("/api/lead")
async def current_lead() -> dict:
    return LEAD


@app.get("/api/enums")
async def api_enums() -> dict:
    return {"ok": True, "enums": load_enums()}


@app.post("/api/extract-visit-note")
async def api_extract_visit_note(payload: dict = Body(...)) -> dict:
    """挂机后基于录音稿生成结构化小记（优先 .env LLM，失败回退规则；不对用户口播内部标签）。"""
    transcript = payload.get("transcript") or []
    if not isinstance(transcript, list):
        return {"ok": False, "message": "transcript 须为数组"}
    draft = await extract_visit_note(transcript, LEAD)
    return {"ok": True, "draft": draft}


@app.post("/api/visit-notes")
async def save_visit_note(payload: dict = Body(...)) -> dict:
    """通话结束后落拜访小记；默认 AI 抽取后自动保存，人工改标走同一接口覆盖。"""
    notes_dir = ROOT / "leads" / "visit_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    lead_id = payload.get("lead_id") or LEAD.get("lead_id") or "unknown"
    stamp = payload.get("ended_at") or ""
    safe_stamp = stamp.replace(":", "").replace("-", "").replace("T", "_")[:15] or uuid.uuid4().hex[:8]
    note_id = payload.get("note_id") or f"{lead_id}_{safe_stamp}"
    path = notes_dir / f"{note_id}.json"

    ai_result = payload.get("ai_result") or payload.get("result") or ""
    ai_followable = payload.get("ai_followable")
    if ai_followable is None:
        ai_followable = payload.get("followable") in (True, "是", "true", "True")
    slots = payload.get("slots") or {}
    if not slots:
        slots = {
            "has_shipping_need": payload.get("has_shipping_need") or "",
            "origin": payload.get("origin") or "",
            "monthly_volume": payload.get("monthly_volume") or "",
            "contact_alt": payload.get("contact_alt") or "",
            "next_action": payload.get("next_action") or "",
        }
    destinations = slots.get("destinations")
    if not isinstance(destinations, list):
        raw = (
            slots.get("destination")
            or slots.get("destination_or_route")
            or payload.get("destination")
            or payload.get("route")
            or ""
        )
        if isinstance(raw, list):
            destinations = raw
        elif isinstance(raw, str) and raw.strip():
            destinations = [p.strip() for p in re.split(r"[、,，/|]+", raw) if p.strip()]
        else:
            destinations = []
    dest_label = "、".join(destinations) if destinations else ""
    slots = {
        **slots,
        "destinations": destinations,
        "destination": dest_label,
        "destination_or_route": dest_label,
    }

    record = {
        "note_id": note_id,
        "lead_id": lead_id,
        "source": LEAD.get("source"),
        "ended_at": stamp,
        "saved_at": stamp or str(uuid.uuid4()),
        "visit_method": payload.get("visit_method") or "电话拜访",
        "judgment_source": payload.get("judgment_source") or "call_transcript_extract",
        "ai_result": ai_result,
        "ai_invalid_reason": payload.get("ai_invalid_reason") or payload.get("invalid_reason") or "",
        "ai_intent": payload.get("ai_intent") or payload.get("intent") or "",
        "ai_followable": bool(ai_followable),
        "slots": slots,
        "communication_summary": payload.get("communication_summary")
        or payload.get("communication")
        or payload.get("summary")
        or "",
        "transcript": payload.get("transcript") or [],
        "edited": bool(payload.get("edited")),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "note_id": note_id, "record": record}


def _volc_headers() -> dict[str, str]:
    return {
        "X-Api-App-ID": APP_ID,
        "X-Api-Access-Key": ACCESS_KEY,
        "X-Api-Resource-Id": "volc.speech.dialog",
        "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }


async def _send_json(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload, ensure_ascii=False))


@app.websocket("/ws/call")
async def call_socket(browser: WebSocket) -> None:
    await browser.accept()

    if not APP_ID or not ACCESS_KEY:
        await _send_json(browser, {"type": "error", "message": "缺少 VOLC_APP_ID / VOLC_ACCESS_KEY，请检查 .env"})
        await browser.close()
        return

    session_id = str(uuid.uuid4())
    volc = None
    receiver: asyncio.Task | None = None

    try:
        await _send_json(browser, {"type": "status", "state": "connecting"})
        headers = _volc_headers()
        # 本机若配置了 SOCKS/HTTP 代理，websockets 默认会走代理；
        # 未装 python-socks 时会瞬间失败，表现为「点拨打闪一下就没了」。
        connect_kwargs = {
            "ping_interval": None,
            "max_size": 8 * 1024 * 1024,
            "open_timeout": 15,
            "proxy": None,
        }
        try:
            volc = await websockets.connect(
                VOLC_URL,
                additional_headers=headers,
                **connect_kwargs,
            )
        except TypeError:
            connect_kwargs.pop("proxy", None)
            try:
                volc = await websockets.connect(
                    VOLC_URL,
                    extra_headers=headers,
                    **connect_kwargs,
                )
            except TypeError:
                volc = await websockets.connect(
                    VOLC_URL,
                    extra_headers=headers,
                    ping_interval=None,
                    max_size=8 * 1024 * 1024,
                )
        logid = ""
        try:
            logid = volc.response.headers.get("X-Tt-Logid", "")
        except Exception:
            try:
                logid = volc.response_headers.get("X-Tt-Logid", "")
            except Exception:
                pass

        await volc.send(protocol.build_start_connection())
        conn_resp = protocol.parse_response(await volc.recv())
        if conn_resp.get("event") == 51:
            await _send_json(browser, {"type": "error", "message": f"连接失败: {conn_resp.get('payload_msg')}"})
            return

        await volc.send(protocol.build_start_session(session_id, START_SESSION))
        sess_resp = protocol.parse_response(await volc.recv())
        if sess_resp.get("event") == 153:
            await _send_json(
                browser,
                {"type": "error", "message": f"会话失败: {sess_resp.get('payload_msg')}", "logid": logid},
            )
            return

        dialog_id = ""
        payload = sess_resp.get("payload_msg") or {}
        if isinstance(payload, dict):
            dialog_id = payload.get("dialog_id", "")

        await volc.send(protocol.build_say_hello(session_id, HELLO_TEXT))
        await _send_json(
            browser,
            {
                "type": "status",
                "state": "in_call",
                "session_id": session_id,
                "dialog_id": dialog_id,
                "logid": logid,
            },
        )

        async def relay_from_volc() -> None:
            try:
                async for message in volc:
                    if isinstance(message, str):
                        continue
                    parsed = protocol.parse_response(message)
                    event = parsed.get("event")
                    msg = parsed.get("payload_msg")

                    # 音频帧
                    if event == 352 and isinstance(msg, (bytes, bytearray)):
                        await browser.send_bytes(bytes(msg))
                        continue

                    if event == 450:
                        await _send_json(browser, {"type": "interrupt"})
                    elif event == 451 and isinstance(msg, dict):
                        results = msg.get("results") or []
                        if results:
                            await _send_json(
                                browser,
                                {
                                    "type": "asr",
                                    "text": results[0].get("text", ""),
                                    "interim": bool(results[0].get("is_interim", True)),
                                },
                            )
                    elif event == 550 and isinstance(msg, dict):
                        await _send_json(browser, {"type": "bot_text", "text": msg.get("content", "")})
                    elif event == 350 and isinstance(msg, dict):
                        await _send_json(
                            browser,
                            {"type": "tts_start", "text": msg.get("text", ""), "tts_type": msg.get("tts_type")},
                        )
                    elif event == 359:
                        await _send_json(browser, {"type": "tts_end"})
                    elif event == 459:
                        await _send_json(browser, {"type": "asr_end"})
                    elif event == 599 and isinstance(msg, dict):
                        await _send_json(
                            browser,
                            {
                                "type": "error",
                                "message": msg.get("message") or str(msg),
                                "status_code": msg.get("status_code"),
                            },
                        )
                    elif event in (152, 52):
                        await _send_json(browser, {"type": "status", "state": "ended"})
                        break
            except websockets.exceptions.ConnectionClosed:
                await _send_json(browser, {"type": "status", "state": "ended"})
            except Exception as exc:
                await _send_json(browser, {"type": "error", "message": f"下行中断: {exc}"})

        receiver = asyncio.create_task(relay_from_volc())

        while True:
            frame = await browser.receive()
            if frame.get("type") == "websocket.disconnect":
                break

            if "bytes" in frame and frame["bytes"] is not None:
                await volc.send(protocol.build_task_request(session_id, frame["bytes"]))
                continue

            text = frame.get("text")
            if not text:
                continue
            data = json.loads(text)
            action = data.get("type")
            if action == "hangup":
                break
            if action == "interrupt":
                await volc.send(protocol.build_client_interrupt(session_id))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws/call] error: {type(exc).__name__}: {exc}", flush=True)
        try:
            await _send_json(browser, {"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if receiver and not receiver.done():
            receiver.cancel()
            try:
                await receiver
            except (asyncio.CancelledError, Exception):
                pass
        if volc is not None:
            try:
                await volc.send(protocol.build_finish_session(session_id))
            except Exception:
                pass
            try:
                await volc.send(protocol.build_finish_connection())
            except Exception:
                pass
            try:
                await volc.close()
            except Exception:
                pass
        try:
            await _send_json(browser, {"type": "status", "state": "idle"})
        except Exception:
            pass
