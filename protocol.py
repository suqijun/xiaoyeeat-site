"""火山端到端实时语音 · 二进制协议编解码。"""
from __future__ import annotations

import gzip
import json
from typing import Any

PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_AUDIO_ONLY_RESPONSE = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

MSG_WITH_EVENT = 0b0100
NO_SERIALIZATION = 0b0000
JSON = 0b0001
NO_COMPRESSION = 0b0000
GZIP = 0b0001


def generate_header(
    message_type: int = CLIENT_FULL_REQUEST,
    message_type_specific_flags: int = MSG_WITH_EVENT,
    serial_method: int = JSON,
    compression_type: int = GZIP,
) -> bytearray:
    header = bytearray()
    header.append((PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE)
    header.append((message_type << 4) | message_type_specific_flags)
    header.append((serial_method << 4) | compression_type)
    header.append(0x00)
    return header


def _pack_event(event: int, session_id: str | None, payload: bytes, *, audio: bool = False) -> bytes:
    msg_type = CLIENT_AUDIO_ONLY_REQUEST if audio else CLIENT_FULL_REQUEST
    serial = NO_SERIALIZATION if audio else JSON
    frame = bytearray(generate_header(message_type=msg_type, serial_method=serial))
    frame.extend(int(event).to_bytes(4, "big"))
    if session_id is not None:
        sid = session_id.encode("utf-8")
        frame.extend(len(sid).to_bytes(4, "big"))
        frame.extend(sid)
    compressed = gzip.compress(payload)
    frame.extend(len(compressed).to_bytes(4, "big"))
    frame.extend(compressed)
    return bytes(frame)


def build_start_connection() -> bytes:
    return _pack_event(1, None, b"{}")


def build_finish_connection() -> bytes:
    return _pack_event(2, None, b"{}")


def build_start_session(session_id: str, payload: dict[str, Any]) -> bytes:
    return _pack_event(100, session_id, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def build_finish_session(session_id: str) -> bytes:
    return _pack_event(102, session_id, b"{}")


def build_task_request(session_id: str, audio: bytes) -> bytes:
    return _pack_event(200, session_id, audio, audio=True)


def build_say_hello(session_id: str, content: str) -> bytes:
    return _pack_event(300, session_id, json.dumps({"content": content}, ensure_ascii=False).encode("utf-8"))


def build_client_interrupt(session_id: str) -> bytes:
    return _pack_event(515, session_id, b"{}")


def parse_response(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}

    header_size = raw[0] & 0x0F
    message_type = raw[1] >> 4
    flags = raw[1] & 0x0F
    serialization = raw[2] >> 4
    compression = raw[2] & 0x0F
    payload = raw[header_size * 4 :]
    result: dict[str, Any] = {"message_type": message_type, "flags": flags}

    if message_type == SERVER_ERROR_RESPONSE:
        result["code"] = int.from_bytes(payload[:4], "big")
        size = int.from_bytes(payload[4:8], "big")
        body = payload[8 : 8 + size]
        if compression == GZIP:
            body = gzip.decompress(body)
        result["payload_msg"] = json.loads(body.decode("utf-8")) if serialization == JSON else body
        return result

    offset = 0
    if flags & MSG_WITH_EVENT:
        result["event"] = int.from_bytes(payload[offset : offset + 4], "big")
        offset += 4

    # Connect / Session 响应均带 session_id 长度字段（Connect 时可能为 0）
    if offset + 4 <= len(payload):
        sid_size = int.from_bytes(payload[offset : offset + 4], "big")
        offset += 4
        if sid_size > 0 and offset + sid_size <= len(payload):
            result["session_id"] = payload[offset : offset + sid_size].decode("utf-8", errors="ignore")
            offset += sid_size

    if offset + 4 > len(payload):
        return result

    size = int.from_bytes(payload[offset : offset + 4], "big")
    offset += 4
    body = payload[offset : offset + size]
    if compression == GZIP and body:
        body = gzip.decompress(body)

    if serialization == JSON:
        result["payload_msg"] = json.loads(body.decode("utf-8")) if body else {}
    else:
        result["payload_msg"] = body
    result["payload_size"] = size
    return result
