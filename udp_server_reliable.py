import socket, threading, sys, collections
from common import pack_message, unpack_message

HOST = "0.0.0.0"
PORT = 6000
WINDOW = 128
GAP_ALERT_GRACE = 3

clients = {}          # addr -> username
reverse = {}          # username -> addr
seq_seen = {}         # addr -> deque of recent seqs
last_seq = {}         # addr -> highest contiguous seq seen
gap_count = {}        # addr -> consecutive gaps observed
metrics = {
    "rx_total": 0,
    "rx_bad_checksum": 0,
    "rx_duplicates": 0,
    "rx_out_of_order": 0,
    "tx_broadcast": 0,
    "tx_acks": 0,
}

lock = threading.Lock()

def sendto(sock, addr, raw):
    sock.sendto(raw, addr)

def note_seq(addr, seq):
    if seq is None:
        return "no-seq"
    deq = seq_seen.setdefault(addr, collections.deque(maxlen=WINDOW))
    if seq in deq:
        return "duplicate"
    last = last_seq.get(addr, -1)
    if seq == last + 1:
        last_seq[addr] = seq
        gap_count[addr] = 0
        deq.append(seq)
        return "in-order"
    elif seq > last + 1:
        last_seq[addr] = max(last, seq)
        deq.append(seq)
        gap_count[addr] = gap_count.get(addr, 0) + 1
        return "gap"
    else:
        deq.append(seq)
        gap_count[addr] = gap_count.get(addr, 0) + 1
        return "old"

def ack(sock, addr, username, seq):
    if seq is None:
        return
    sendto(sock, addr, pack_message("ack", "server", f"ack {seq}", target=username, seq=seq))
    metrics["tx_acks"] += 1

def broadcast(sock, raw):
    with lock:
        for addr in list(clients.keys()):
            try:
                sendto(sock, addr, raw)
                metrics["tx_broadcast"] += 1
            except Exception:
                pass

def handle_packet(sock, data, addr):
    metrics["rx_total"] += 1
    ok, obj, err = unpack_message(data)
    if not ok:
        metrics["rx_bad_checksum"] += 1
        sendto(sock, addr, pack_message("system", "server", f"Bad message: {err}"))
        return

    msg = obj["msg"]
    kind = msg.get("kind")
    username = msg.get("sender")
    seq = msg.get("seq")

    if kind != "join":
        status = note_seq(addr, seq)
        if status == "duplicate":
            metrics["rx_duplicates"] += 1
            ack(sock, addr, username, seq)
            return
        elif status in ("gap", "old"):
            metrics["rx_out_of_order"] += 1
            if gap_count.get(addr, 0) >= GAP_ALERT_GRACE:
                sendto(sock, addr, pack_message("system", "server", f"Notice: sequence gaps seen (last={last_seq.get(addr)}, got={seq})"))
                gap_count[addr] = 0

    if kind == "join":
        with lock:
            clients[addr] = username
            reverse[username] = addr
            seq_seen.pop(addr, None)
            last_seq.pop(addr, None)
            gap_count.pop(addr, None)
        broadcast(sock, pack_message("system", "server", f"{username} joined (UDP)."))
        ack(sock, addr, username, seq)
        return

    if kind == "command":
        cmd = msg["text"].strip()
        if cmd == "/list":
            with lock:
                names = ", ".join(sorted(reverse.keys()))
            sendto(sock, addr, pack_message("system", "server", f"Online: {names}"))
        elif cmd.startswith("/whisper"):
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                sendto(sock, addr, pack_message("system", "server", "Usage: /whisper <user> <msg>"))
            else:
                target, text = parts[1], parts[2]
                with lock:
                    taddr = reverse.get(target)
                if taddr:
                    sendto(sock, addr, pack_message("system", "server", f"(you → {target}) {text}"))
                    sendto(sock, taddr, pack_message("whisper", username, text, target=target, seq=seq))
                else:
                    sendto(sock, addr, pack_message("system", "server", f"User '{target}' not found"))
        elif cmd == "/quit":
            with lock:
                reverse.pop(username, None)
                clients.pop(addr, None)
            broadcast(sock, pack_message("system", "server", f"{username} left."))
        else:
            sendto(sock, addr, pack_message("system", "server", f"Unknown command '{cmd}'"))
        ack(sock, addr, username, seq)
        return

    if kind == "chat":
        broadcast(sock, pack_message("chat", username, msg["text"], seq=seq, extra=msg.get("extra")))
        ack(sock, addr, username, seq)
        return

    sendto(sock, addr, pack_message("system", "server", f"Unhandled kind '{kind}'"))
    ack(sock, addr, username, seq)

def main():
    global PORT
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    print(f"Reliable-ish UDP server on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((HOST, PORT))
        while True:
            data, addr = s.recvfrom(65535)
            handle_packet(s, data, addr)

if __name__ == "__main__":
    main()
