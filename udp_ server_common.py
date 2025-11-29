import json, hashlib, time

PROTO_VERSION = "1.0"

def now_ms() -> int:
    return int(time.time() * 1000)

def pack_message(kind, sender, text="", target=None, seq=None, extra=None):
    msg = {
        "v": PROTO_VERSION,
        "ts": now_ms(),
        "kind": kind,
        "sender": sender,
        "text": text,
        "target": target,
        "seq": seq,
        "extra": extra or {},
    }
    raw = json.dumps(msg, separators=(',', ':'), ensure_ascii=False)
    chk = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    wrapper = {"msg": msg, "sha256": chk}
    return (json.dumps(wrapper) + "\n").encode("utf-8")

def unpack_message(b: bytes):
    try:
        wrapper = json.loads(b.decode("utf-8").strip())
        raw = json.dumps(wrapper["msg"], separators=(',', ':'), ensure_ascii=False)
        chk = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        ok = (chk == wrapper.get("sha256"))
        return ok, wrapper, None if ok else "checksum mismatch"
    except Exception as e:
        return False, None, str(e)

def pretty(sender, msg):
    ts = msg["msg"]["ts"]
    kind = msg["msg"]["kind"]
    text = msg["msg"]["text"]
    target = msg["msg"].get("target")
    t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts/1000))
    if kind == "whisper":
        return f"[{t}] (whisper) {sender} → {target}: {text}"
    elif kind == "system":
        return f"[{t}] * {text}"
    else:
        return f"[{t}] {sender}: {text}"
