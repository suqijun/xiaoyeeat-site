"""挂机后从录音稿生成拜访小记：优先 LLM（.env），失败则回退规则抽取。"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent
ENUMS_PATH = ROOT / "knowledge" / "visit_enums.json"
logger = logging.getLogger(__name__)


def load_enums() -> dict[str, Any]:
    if ENUMS_PATH.exists():
        return json.loads(ENUMS_PATH.read_text(encoding="utf-8"))
    return {}


def _llm_config() -> dict[str, str] | None:
    api_key = (os.getenv("LLM_API_KEY") or "").strip()
    base_url = (os.getenv("LLM_BASE_URL") or "").strip().rstrip("/")
    model = (os.getenv("LLM_MODEL") or "").strip()
    if not api_key or not base_url or not model:
        return None
    if not base_url.endswith("/v1"):
        # OpenAI 兼容：多数网关接受 /v1；DeepSeek 官方 base 也可直接 /chat/completions
        chat_url = f"{base_url}/v1/chat/completions"
        alt_url = f"{base_url}/chat/completions"
    else:
        chat_url = f"{base_url}/chat/completions"
        alt_url = chat_url
    return {
        "api_key": api_key,
        "model": model,
        "chat_url": chat_url,
        "alt_url": alt_url,
    }


def _join_role(transcript: list[dict], role: str) -> str:
    return "".join(
        (t.get("text") or "") for t in transcript if (t.get("role") or "") == role
    )


def _merge_transcript(transcript: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for row in transcript or []:
        role = row.get("role") or ""
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        if merged and merged[-1]["role"] == role:
            a = merged[-1]["text"]
            glue = (
                " "
                if re.search(r"[A-Za-z0-9]$", a) and re.match(r"[A-Za-z0-9]", text)
                else ""
            )
            merged[-1]["text"] = a + glue + text
        else:
            merged.append({"role": role, "text": text})
    return merged


def _format_transcript(merged: list[dict]) -> str:
    lines: list[str] = []
    for row in merged:
        role = row.get("role") or ""
        label = "用户" if role == "user" else ("坐席" if role == "bot" else role)
        lines.append(f"{label}：{row.get('text') or ''}")
    return "\n".join(lines) if lines else "（无有效转写）"


def _pick_enum(value: Any, options: list[str], default: str = "") -> str:
    text = str(value or "").strip()
    if text in options:
        return text
    return default


def _normalize_destinations(raw: Any, options: list[str]) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[、,，/|]+", raw)
    elif isinstance(raw, list):
        parts = [str(x) for x in raw]
    else:
        parts = [str(raw)]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        v = p.strip()
        if v in options and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _dest_label(destinations: list[str]) -> str:
    if not destinations:
        return ""
    return destinations[0] if len(destinations) == 1 else "、".join(destinations)


def _pack_note(
    *,
    enums: dict[str, Any],
    judgment_source: str,
    ai_result: str,
    ai_invalid_reason: str,
    ai_intent: str,
    ai_followable: bool,
    has_shipping_need: str,
    origin: str,
    destinations: list[str],
    monthly_volume: str,
    contact_alt: str,
    next_action: str,
    communication_summary: str,
) -> dict[str, Any]:
    dest_label = _dest_label(destinations)
    visit_method = (enums.get("visit_methods") or ["电话拜访"])[0]
    return {
        "judgment_source": judgment_source,
        "visit_method": visit_method,
        "ai_result": ai_result,
        "ai_invalid_reason": ai_invalid_reason,
        "ai_intent": ai_intent,
        "ai_followable": ai_followable,
        "slots": {
            "has_shipping_need": has_shipping_need,
            "origin": origin,
            "destinations": destinations,
            "destination": dest_label,
            "destination_or_route": dest_label,
            "monthly_volume": monthly_volume,
            "contact_alt": contact_alt,
            "next_action": next_action,
        },
        "communication_summary": communication_summary,
        "enums": {
            "origins": enums.get("origins"),
            "destinations": enums.get("destinations"),
            "next_actions": enums.get("next_actions"),
            "visit_methods": enums.get("visit_methods"),
            "intents": enums.get("intents"),
            "invalid_reasons": enums.get("invalid_reasons"),
            "shipping_need": enums.get("shipping_need"),
        },
        "result": ai_result,
        "intent": ai_intent,
        "followable": "是" if ai_followable else "否",
        "invalid_reason": ai_invalid_reason,
        "route": dest_label,
        "destinations": destinations,
        "monthly_volume": monthly_volume,
        "next_action": next_action,
        "summary": communication_summary,
    }


def _build_llm_messages(
    merged: list[dict], lead: dict, enums: dict[str, Any]
) -> list[dict[str, str]]:
    origins = enums.get("origins") or []
    destinations = enums.get("destinations") or []
    intents = enums.get("intents") or []
    results = enums.get("results") or ["有效", "无效"]
    shipping = enums.get("shipping_need") or ["是", "否"]
    invalid_reasons = enums.get("invalid_reasons") or []
    next_actions = enums.get("next_actions") or []

    contact = lead.get("contact") or {}
    lead_bits = {
        "lead_id": lead.get("lead_id"),
        "name": contact.get("name") or lead.get("name"),
        "shop": contact.get("shop") or lead.get("shop_name"),
        "city": contact.get("city"),
        "source": lead.get("source"),
    }

    system = f"""你是链驿速递线索清洗外呼的挂机质检助手。根据录音稿填写结构化拜访小记。
只输出一个 JSON 对象，不要 Markdown，不要解释。

字段与枚举（必须遵守）：
- ai_result: 仅 {results}
- ai_invalid_reason: 有效时为空字符串；无效时取 {invalid_reasons}
- ai_intent: 仅 {intents}
- has_shipping_need: 「是」「否」或空字符串（本通未确认则空）
- origin: 空或 {origins}
- destinations: 数组，元素只能来自 {destinations}；可多选
- monthly_volume: 文本；口语区间保留区间（如三五百→300–500），勿臆造精确单值；未提则空
- contact_alt: 文本；同手机号微信写「微信（同手机号）」；未提则空
- next_action: 仅 {next_actions}
- communication_summary: 一两句中文，必须依据本通事实（另约时间、发货地、到达地、月单量、联系方式等），禁止与录音不符的套话

判定规则：
1) 明确拒绝继续通话 → 无效 / 明确拒绝 / 意愿无 / 寄件诉求否 / 无需跟进
2) 明确无寄件需求，且不是另约 → 无效 / 无寄件需求 / 意愿无 / 寄件诉求否 / 无需跟进
3) 现在不方便并约定再联系（如明天上午9点）→ 有效；next_action=另约时间联系；寄件诉求未确认则空；摘要写清约定时间。不要判成无效拒绝。
4) 确认有寄件且可大致承接 → 有效；无法承接 → 无效 / 需求无法满足
5) 信息不足但未否认需求 → 有效，意愿可偏低，寄件诉求可空；摘要写「未完整确认」并引用用户要点
6) 不得编造录音中没有的地点、单量、微信号

线索侧参考（非用户口述，仅作城市映射提示）：{json.dumps(lead_bits, ensure_ascii=False)}
"""

    user = f"""录音稿：
{_format_transcript(merged)}

请输出 JSON，键为：
ai_result, ai_invalid_reason, ai_intent, has_shipping_need, origin, destinations,
monthly_volume, contact_alt, next_action, communication_summary
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM 返回非对象 JSON")
    return data


def _note_from_llm_payload(
    data: dict[str, Any], enums: dict[str, Any]
) -> dict[str, Any]:
    results = enums.get("results") or ["有效", "无效"]
    intents = enums.get("intents") or ["高", "中", "低", "无"]
    invalid_reasons = enums.get("invalid_reasons") or []
    origins = enums.get("origins") or []
    dest_opts = enums.get("destinations") or []
    next_actions = enums.get("next_actions") or []
    shipping_opts = list(enums.get("shipping_need") or ["是", "否"]) + [""]

    ai_result = _pick_enum(data.get("ai_result"), results, "有效")
    ai_intent = _pick_enum(data.get("ai_intent"), intents, "低")
    next_action = _pick_enum(
        data.get("next_action"), next_actions, next_actions[0] if next_actions else ""
    )
    has_shipping_need = str(data.get("has_shipping_need") or "").strip()
    if has_shipping_need not in shipping_opts:
        has_shipping_need = ""

    if ai_result == "有效":
        ai_invalid_reason = ""
    else:
        ai_invalid_reason = _pick_enum(
            data.get("ai_invalid_reason"), invalid_reasons, "其他"
        )

    origin = _pick_enum(data.get("origin"), origins, "")
    destinations = _normalize_destinations(data.get("destinations"), dest_opts)
    monthly_volume = str(data.get("monthly_volume") or "").strip()
    contact_alt = str(data.get("contact_alt") or "").strip()
    summary = str(data.get("communication_summary") or "").strip()
    if not summary:
        summary = "本通未形成可核对的沟通摘要，需人工根据录音稿确认。"

    ai_followable = next_action != "无需跟进" and ai_result == "有效"
    if next_action == "无需跟进":
        ai_followable = False

    return _pack_note(
        enums=enums,
        judgment_source="llm_transcript_extract",
        ai_result=ai_result,
        ai_invalid_reason=ai_invalid_reason,
        ai_intent=ai_intent,
        ai_followable=ai_followable,
        has_shipping_need=has_shipping_need,
        origin=origin,
        destinations=destinations,
        monthly_volume=monthly_volume,
        contact_alt=contact_alt,
        next_action=next_action,
        communication_summary=summary,
    )


async def _chat_completions(
    cfg: dict[str, str], messages: list[dict[str, str]]
) -> str:
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    urls = [cfg["chat_url"]]
    if cfg["alt_url"] not in urls:
        urls.append(cfg["alt_url"])

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for url in urls:
            try:
                resp = await client.post(url, headers=headers, json=body)
                if resp.status_code == 404 and url != urls[-1]:
                    continue
                # 部分模型不支持 response_format，去掉再试一次
                if resp.status_code >= 400 and "response_format" in (resp.text or ""):
                    body.pop("response_format", None)
                    resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                payload = resp.json()
                content = (
                    ((payload.get("choices") or [{}])[0].get("message") or {}).get(
                        "content"
                    )
                    or ""
                )
                if not content:
                    raise ValueError("LLM 返回空 content")
                return content
            except Exception as exc:  # noqa: BLE001 — 多 URL 试探后统一抛
                last_err = exc
                logger.warning("LLM 请求失败 url=%s err=%s", url, exc)
    assert last_err is not None
    raise last_err


# ---------- 规则回退（LLM 未配置或调用失败时） ----------


def _parse_monthly_volume(text: str) -> str:
    if not text:
        return ""
    oral = [
        (r"三五百|三百到五百|300\s*[-~到至]\s*500", "300–500"),
        (r"两三千|二千到三千|2000\s*[-~到至]\s*3000", "2000–3000"),
        (r"七八百|七百到八百|700\s*[-~到至]\s*800", "700–800"),
        (r"一千多|一千左右|1000左右", "约1000"),
        (r"几百单|几百票", "数百"),
    ]
    for pat, val in oral:
        if re.search(pat, text):
            return val
    m = re.search(
        r"(?:每月|一个月|月均|一个月大概|一个月大约|一个月差不多)?\s*"
        r"(\d{2,5})\s*[-~到至]\s*(\d{2,5})\s*(?:单|票|件)?",
        text,
    )
    if m:
        return f"{m.group(1)}–{m.group(2)}"
    m = re.search(
        r"(?:每月|一个月|月均|一个月大概|一个月大约|一个月差不多)?\s*"
        r"(约|大概|左右)?\s*(\d{2,5})\s*(?:单|票|件)",
        text,
    )
    if m:
        n = m.group(2)
        return f"约{n}" if m.group(1) else n
    return ""


def _map_origin(user: str, lead: dict, enums: dict) -> str:
    city_map: dict = enums.get("city_to_origin") or {}
    for city, region in city_map.items():
        if city in user:
            return region
    if re.search(r"江浙沪.*(发|寄|出)|从江浙沪|江浙沪一带.*(发|寄)", user):
        return "华东"
    lead_city = ((lead.get("contact") or {}).get("city") or "").strip()
    if lead_city and lead_city in city_map:
        if re.search(r"寄|发|出货|从", user) or lead_city in user:
            return city_map[lead_city]
    if lead_city in city_map and re.search(r"有需求|发货|寄", user):
        return city_map[lead_city]
    return ""


def _map_destinations(user: str, enums: dict) -> list[str]:
    keywords: dict = enums.get("dest_keywords") or {}
    found: list[str] = []
    seen: set[str] = set()
    for key in sorted(keywords.keys(), key=len, reverse=True):
        if key in user:
            val = keywords[key]
            if val and val not in seen:
                seen.add(val)
                found.append(val)
    for m in re.finditer(
        r"(?:发往|寄到|寄至|到|至)\s*([\u4e00-\u9fa5、，,和与及/]{2,24})", user
    ):
        chunk = m.group(1)
        for key, val in keywords.items():
            if key in chunk and val not in seen:
                seen.add(val)
                found.append(val)
        city_map: dict = enums.get("city_to_origin") or {}
        for city, region in city_map.items():
            if city in chunk:
                mapped = (
                    "江浙沪"
                    if region == "华东"
                    else ("西南" if region == "西南/西北" else region)
                )
                if mapped not in seen:
                    seen.add(mapped)
                    found.append(mapped)
    return found


def _extract_callback_time(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"明天\s*(早上|上午|中午|下午|晚上)?\s*(\d{1,2})\s*[点时]",
        r"后天\s*(早上|上午|中午|下午|晚上)?\s*(\d{1,2})\s*[点时]",
        r"(周[一二三四五六日天]|星期[一二三四五六日天])\s*(早上|上午|中午|下午|晚上)?\s*(\d{1,2})\s*[点时]",
        r"(下午|上午|早上|晚上)\s*(\d{1,2})\s*[点时]",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        return re.sub(r"\s+", "", m.group(0))
    if re.search(r"明天|后天|改天|回头|晚点|换个时间|另约", text):
        if "明天" in text:
            return "明天"
        if "后天" in text:
            return "后天"
        return "另约时间"
    return ""


def _is_reschedule(user: str, bot: str) -> bool:
    text = user + bot
    return bool(
        re.search(
            r"换个时间|不太方便|现在忙|现在不方便|不方便接|另约|改天|"
            r"回头再|晚点打|稍后再打|明天.{0,8}(打|联系|电话)|"
            r"上午\s*\d{1,2}\s*点|下午\s*\d{1,2}\s*点",
            text,
        )
    )


def _build_summary(
    *,
    merged: list[dict],
    reject: bool,
    deny: bool,
    reschedule: bool,
    callback_time: str,
    has_shipping_need: str,
    origin: str,
    dest_label: str,
    monthly_volume: str,
    contact_alt: str,
    lead_city: str,
    user: str,
) -> str:
    parts: list[str] = []
    if reject:
        parts.append("用户明确拒绝继续通话")
    elif deny:
        parts.append("用户表示没有寄件/发货需求")
    elif reschedule or callback_time:
        if callback_time and callback_time not in ("另约时间", "明天", "后天"):
            parts.append(f"用户现在不方便，约定{callback_time}再联系")
        elif callback_time:
            parts.append(f"用户现在不方便，约定{callback_time}再联系")
        else:
            parts.append("用户现在不方便，要求另约时间再联系")
        if has_shipping_need == "是":
            parts.append("寄件诉求待下次通话继续确认或跟进")
        else:
            parts.append("寄件诉求尚未在本通确认完毕")
    elif has_shipping_need == "是":
        parts.append("确认用户有寄件诉求")
        if origin and dest_label:
            from_label = origin
            if lead_city and lead_city in user:
                from_label = f"{lead_city}（{origin}）"
            parts.append(f"一般从{from_label}发往{dest_label}一带")
        elif origin:
            parts.append(f"发货地为{origin}")
        elif dest_label:
            parts.append(f"到达地为{dest_label}一带")
        if monthly_volume:
            parts.append(f"每月约{monthly_volume}单")
        if contact_alt:
            parts.append(f"其他联系方式：{contact_alt}")
    else:
        user_lines = [r["text"] for r in merged if r["role"] == "user"]
        if user_lines:
            snippet = user_lines[0]
            if len(snippet) > 48:
                snippet = snippet[:48] + "…"
            parts.append(f"本通未完整确认寄件诉求，用户主要表示：{snippet}")
        else:
            parts.append("本通未形成明确寄件诉求结论，需后续跟进确认")
    if contact_alt and contact_alt not in "，".join(parts):
        parts.append(f"其他联系方式：{contact_alt}")
    return "，".join(parts) + "。"


def _extract_via_rules(
    transcript: list[dict], lead: dict | None = None
) -> dict[str, Any]:
    lead = lead or {}
    enums = load_enums()
    merged = _merge_transcript(transcript)
    user = _join_role(merged, "user")
    bot = _join_role(merged, "bot")
    text_all = user + bot

    reject = bool(re.search(r"别打了|烦不烦|滚|不要再打电话|不要打电话给我", user))
    deny = bool(
        re.search(
            r"没有?(这个)?需求|不需要|没兴趣|打错了|不要再联系|没寄件|不寄|"
            r"没有发货|没有寄件",
            user,
        )
    )
    cannot_serve = bool(
        re.search(r"接不住|无法承接|暂时(做)?不了|覆盖不了|满足不了", text_all)
    )
    has_need = bool(
        re.search(
            r"有需求|有寄件|要寄|有寄|发货|在找快递|快递合作|需要寄|要发货|"
            r"有的.*寄|可以合作",
            user,
        )
    ) or bool(
        re.search(r"(月|每月|一个月).{0,8}(单|票|件)|三五百|两三千|寄到|发往", user)
    )

    reschedule = _is_reschedule(user, bot)
    callback_time = _extract_callback_time(text_all)

    if reject:
        ai_result = "无效"
        ai_invalid_reason = "明确拒绝"
        has_shipping_need = "否"
        ai_intent = "无"
        ai_followable = False
    elif deny and not reschedule:
        ai_result = "无效"
        ai_invalid_reason = "无寄件需求"
        has_shipping_need = "否"
        ai_intent = "无"
        ai_followable = False
    elif reschedule or callback_time:
        ai_result = "有效"
        ai_invalid_reason = ""
        has_shipping_need = "是" if has_need else ""
        ai_intent = "中"
        ai_followable = True
    elif cannot_serve and has_need:
        ai_result = "无效"
        ai_invalid_reason = "需求无法满足"
        has_shipping_need = "是"
        ai_intent = "无"
        ai_followable = False
    elif has_need:
        ai_result = "有效"
        ai_invalid_reason = ""
        has_shipping_need = "是"
        if re.search(r"微信|加一下|可以合作|签约|尽快联系|方便联系", text_all):
            ai_intent = "高"
        elif re.search(r"再看看|考虑|犹豫|以后|回头|不一定", user):
            ai_intent = "低"
        else:
            ai_intent = "中"
        ai_followable = True
    else:
        ai_result = "有效"
        ai_invalid_reason = ""
        has_shipping_need = ""
        ai_intent = "低"
        ai_followable = True

    origin = _map_origin(user, lead, enums)
    destinations = _map_destinations(user, enums)
    dest_label = _dest_label(destinations)
    if not origin:
        lead_city = ((lead.get("contact") or {}).get("city") or "").strip()
        city_map = enums.get("city_to_origin") or {}
        if has_shipping_need == "是" and lead_city in city_map:
            origin = city_map[lead_city]

    monthly_volume = _parse_monthly_volume(user) or _parse_monthly_volume(text_all)

    contact_alt = ""
    if re.search(
        r"同手机号|同手机|跟手机一样|和手机一样|微信号?(就?是|同|跟|与).{0,8}(手机|电话)号?",
        text_all,
    ):
        contact_alt = "微信（同手机号）"
    else:
        wechat_match = re.search(
            r"(微信|wx|WeChat)[：:\s]*([A-Za-z0-9_\-]{4,})", text_all, re.I
        )
        if wechat_match:
            contact_alt = wechat_match.group(0)
        elif re.search(r"(我的)?微信是|微信号|加我微信|加您微信|留(一下)?微信", text_all):
            contact_alt = "微信"

    next_actions = enums.get("next_actions") or []
    if not ai_followable:
        next_action = "无需跟进"
    elif reschedule or callback_time or re.search(
        r"另约|不方便|回头再|改天|现在忙|换个时间|明天|上午|下午", text_all
    ):
        next_action = "另约时间联系"
    elif re.search(r"没打通|未接通|重新打|稍后再打|再打一次", text_all):
        next_action = "重新拨打电话"
    else:
        next_action = "待销售主动联系"
    if next_action not in next_actions and next_actions:
        next_action = next_actions[0]

    lead_city = ((lead.get("contact") or {}).get("city") or "").strip()
    communication_summary = _build_summary(
        merged=merged,
        reject=reject,
        deny=deny and not reschedule,
        reschedule=reschedule or bool(callback_time),
        callback_time=callback_time,
        has_shipping_need=has_shipping_need,
        origin=origin,
        dest_label=dest_label,
        monthly_volume=monthly_volume,
        contact_alt=contact_alt,
        lead_city=lead_city,
        user=user,
    )

    return _pack_note(
        enums=enums,
        judgment_source="rule_transcript_extract",
        ai_result=ai_result,
        ai_invalid_reason=ai_invalid_reason,
        ai_intent=ai_intent,
        ai_followable=ai_followable,
        has_shipping_need=has_shipping_need,
        origin=origin,
        destinations=destinations,
        monthly_volume=monthly_volume,
        contact_alt=contact_alt,
        next_action=next_action,
        communication_summary=communication_summary,
    )


async def extract_visit_note(
    transcript: list[dict], lead: dict | None = None
) -> dict[str, Any]:
    """优先用 .env 中 LLM_* 归纳；未配置或失败时回退规则抽取。"""
    lead = lead or {}
    enums = load_enums()
    merged = _merge_transcript(transcript)
    cfg = _llm_config()
    if cfg:
        try:
            content = await _chat_completions(
                cfg, _build_llm_messages(merged, lead, enums)
            )
            data = _parse_llm_json(content)
            return _note_from_llm_payload(data, enums)
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM 抽取失败，回退规则：%s", exc)
    else:
        logger.warning("未配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，使用规则抽取")
    return _extract_via_rules(transcript, lead)


# 兼容旧同步调用
def extract_visit_note_sync(
    transcript: list[dict], lead: dict | None = None
) -> dict[str, Any]:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(extract_visit_note(transcript, lead))
    return _extract_via_rules(transcript, lead)
