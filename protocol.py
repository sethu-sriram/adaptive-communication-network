"""Application-level protocol for Project 30 (UDP, reliable-ish delivery with recovery).

Header (18 bytes, network byte order):
    magic(2)=0x5030 | type(1) | attempt(1) | client_id(2) | seq(4) | send_ts_ns(8)
Types:
    DATA    client -> server, header + payload
    ACK     server -> client, echoes the header of the DATA it acknowledges
    FIN     client -> server, end of session (server prints/records per-client stats)
    FINACK  server -> client
`attempt` is 0 for the first transmission and increments on every retransmission,
so the client can measure RTT per attempt (no retransmission ambiguity).
"""
import struct

MAGIC = 0x5030
DATA, ACK, FIN, FINACK = 1, 2, 3, 4
HDR = struct.Struct('!HBBHIQ')


def pack(msg_type, client_id, seq, attempt, ts_ns, payload=b''):
    return HDR.pack(MAGIC, msg_type, attempt, client_id, seq, ts_ns) + payload


def unpack(buf):
    """Return (type, attempt, client_id, seq, ts_ns, payload) or None if malformed."""
    if len(buf) < HDR.size:
        return None
    magic, t, attempt, cid, seq, ts = HDR.unpack_from(buf)
    if magic != MAGIC or t not in (DATA, ACK, FIN, FINACK):
        return None
    return t, attempt, cid, seq, ts, buf[HDR.size:]
