# udp_client.py
import socket
import threading
import sys
import time
import collections

from common import pack_message, unpack_message, pretty  # or udp_server_common

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6000

# --------- Global state for this client --------- #

seq_lock = threading.Lock()
next_seq_value = 0  # we start from 0 so "join" can be seq=0

# Incoming ordering detection (per-sender)
INCOMING_WINDOW = 128
incoming_seq_seen = {}    # sender -> deque of recent seqs
incoming_last_seq = {}    # sender -> highest contiguous seq seen
incoming_gap_count = {}   # sender -> consecutive gaps/olds seen
INCOMING_GAP_ALERT_GRACE = 3

# Simple metrics for client
metrics = {
    "rx_total": 0,
    "rx_bad_checksum": 0,
    "rx_duplicates": 0,
    "rx_out_of_order": 0,
    "tx_total": 0,
}

metrics_lock = threading.Lock()


def metric_inc(key: str):
    with metrics_lock:
        metrics[key] += 1


def next_seq() -> int:
    """Return the next sequence number for outgoing messages."""
    global next_seq_value
    with seq_lock:
        next_seq_value += 1
        return next_seq_value


def note_incoming_seq(sender: str, seq: int) -> str:
    """
    Track incoming sequence numbers from a given sender.
    Returns one of: 'no-seq', 'duplicate', 'in-order', 'gap', 'old'
    """
    if seq is None:
        return "no-seq"

    deq = incoming_seq_seen.setdefault(sender, collections.deque(maxlen=INCOMING_WINDOW))
    if seq in deq:
        return "duplicate"

    last = incoming_last_seq.get(sender, -1)
    if seq == last + 1:
        # Perfectly in order
        incoming_last_seq[sender] = seq
        incoming_gap_count[sender] = 0
        deq.append(seq)
        return "in-order"
    elif seq > last + 1:
        # Forward jump: there is a gap
        # We treat seq as "highest seen" even if some are missing.
        incoming_last_seq[sender] = max(last, seq)
        deq.append(seq)
        incoming_gap_count[sender] = incoming_gap_count.get(sender, 0) + 1
        return "gap"
    else:
        # seq <= last, out-of-order / old
        deq.append(seq)
        incoming_gap_count[sender] = incoming_gap_count.get(sender, 0) + 1
        return "old"


def recv_loop(sock: socket.socket):
    """
    Receive loop running in a thread.
    Verifies checksum, detects ordering issues, and prints formatted messages.
    """
    while True:
        try:
            data, addr = sock.recvfrom(65535)
        except OSError:
            # Socket likely closed because user quit
            break

        metric_inc("rx_total")

        ok, obj, err = unpack_message(data)
        if not ok or obj is None:
            metric_inc("rx_bad_checksum")
            print(f"[client] Dropped bad message from {addr}: {err}")
            continue

        msg = obj["msg"]
        kind = msg.get("kind")
        sender = msg.get("sender", "unknown")
        seq = msg.get("seq")

        # For integrity: checksum verification already done via unpack_message (ok flag).
        # For ordering: we track all messages with a sequence number.
        if seq is not None:
            status = note_incoming_seq(sender, seq)
            if status == "duplicate":
                metric_inc("rx_duplicates")
                print(f"[client] Notice: duplicate seq from {sender}: {seq}")
                # still print it so user sees what arrived
            elif status in ("gap", "old"):
                metric_inc("rx_out_of_order")
                if incoming_gap_count.get(sender, 0) >= INCOMING_GAP_ALERT_GRACE:
                    print(
                        f"[client] Warning: sequence gaps/out-of-order from {sender} "
                        f"(last={incoming_last_seq.get(sender)}, got={seq})"
                    )
                    incoming_gap_count[sender] = 0

        # Use pretty() to format messages nicely
        if kind == "system":
            line = pretty("server", obj)
        else:
            line = pretty(sender, obj)

        print(line)


def send_join(sock: socket.socket, server_addr, username: str):
    """
    Send join message to server with seq=0.
    Subsequent calls to next_seq() will start from 1.
    """
    global next_seq_value
    with seq_lock:
        next_seq_value = 0
        join_seq = 0

    raw = pack_message("join", username, text=f"{username} joining via UDP", seq=join_seq)
    sock.sendto(raw, server_addr)
    metric_inc("tx_total")
    print(f"[client] Sent join (seq={join_seq})")


def input_loop(sock: socket.socket, server_addr, username: str):
    """
    Reads user input from stdin and sends chat/command messages.
    /quit will exit the client.
    """
    try:
        while True:
            try:
                line = input()
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                kind = "command"
                text = line
            else:
                kind = "chat"
                text = line

            seq = next_seq()
            raw = pack_message(kind, username, text=text, seq=seq)
            sock.sendto(raw, server_addr)
            metric_inc("tx_total")

            if line == "/quit":
                print("[client] Quitting...")
                break
    except KeyboardInterrupt:
        print("\n[client] Interrupted by user.")
    finally:
        # Give receiver thread a moment, then close socket
        time.sleep(0.2)
        sock.close()
        print_metrics()


def print_metrics():
    """Print a small summary of client-side reliability stats."""
    print("\n[client] === UDP Client Metrics ===")
    print(f"  TX total messages:      {metrics['tx_total']}")
    print(f"  RX total messages:      {metrics['rx_total']}")
    print(f"  RX bad checksum:        {metrics['rx_bad_checksum']}")
    print(f"  RX duplicates detected: {metrics['rx_duplicates']}")
    print(f"  RX out-of-order/gaps:   {metrics['rx_out_of_order']}")
    print("[client] ==========================\n")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <username> [host] [port]")
        print(f"Default host={DEFAULT_HOST}, port={DEFAULT_PORT}")
        sys.exit(1)

    username = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HOST
    port = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PORT
    server_addr = (host, port)

    print(f"[client] UDP chat client as '{username}' connecting to {host}:{port}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Start receiver thread
    t = threading.Thread(target=recv_loop, args=(sock,), daemon=True)
    t.start()

    # Send join message
    send_join(sock, server_addr, username)

    # Enter interactive loop
    input_loop(sock, server_addr, username)


if __name__ == "__main__":
    main()
