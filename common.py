
import json
import hashlib
import time

PROTO_VERSION = "1.0"


def now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)


def pack_message(kind, sender, text: str = "", target=None, seq=None, extra=None) -> bytes:
    """
    Build a message with metadata and SHA-256 checksum.
    This must match what your UDP server expects.
    """
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
    # Same compact JSON style as in your teammate's code
    raw = json.dumps(msg, separators=(",", ":"), ensure_ascii=False)
    chk = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    wrapper = {"msg": msg, "sha256": chk}
    # Server sends newline-terminated JSON
    return (json.dumps(wrapper) + "\n").encode("utf-8")


def unpack_message(b: bytes):
    """
    Parse bytes into a message and verify checksum.

    Returns:
      (ok: bool, wrapper: dict | None, error: str | None)
    """
    try:
        wrapper = json.loads(b.decode("utf-8").strip())
        raw = json.dumps(wrapper["msg"], separators=(",", ":"), ensure_ascii=False)
        chk = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        ok = chk == wrapper.get("sha256")
        return ok, wrapper, None if ok else "checksum mismatch"
    except Exception as e:
        return False, None, str(e)


def pretty(sender: str, wrapper: dict) -> str:
    """
    Format a message for printing on client side.
    `wrapper` is the dict returned by unpack_message (with keys 'msg', 'sha256').
    """
    msg = wrapper["msg"]
    ts = msg["ts"]
    kind = msg["kind"]
    text = msg["text"]
    target = msg.get("target")

    t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))

    if kind == "whisper":
        return f"[{t}] (whisper) {sender} → {target}: {text}"
    elif kind == "system":
        return f"[{t}] * {text}"
    else:
        return f"[{t}] {sender}: {text}"
