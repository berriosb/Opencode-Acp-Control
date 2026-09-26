#!/usr/bin/env python3
"""Small nd-JSON process used to exercise the FIFO transport."""

from __future__ import annotations

import json
import sys


def response(message: dict) -> dict:
    method = message.get("method")
    message_id = message.get("id")
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {}}
    elif method == "session/new":
        result = {"sessionId": "fake-session"}
    else:
        result = {"echoMethod": method}
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


for line in sys.stdin:
    incoming = json.loads(line)
    if "id" not in incoming:
        continue
    print(json.dumps(response(incoming), separators=(",", ":")), flush=True)
