"""Reject duplicate keys and broken container boundaries; never complete/fix JSON.

This is an early streaming guard, not a replacement for strict JSON parsing or
schema/domain validation. In particular, never accept a valid prefix and discard
trailing model output: that can silently lose required fields or teaching claims.
"""
import json


class JSONKeyGuard:
    def __init__(self):
        self.stack = []
        self.string = None
        self.key_frame = None
        self.escaped = False
        self.started = False
        self.finished = False

    def feed(self, text):
        for char in text:
            if self.finished:
                if char not in " \t\r\n":
                    raise ValueError("Extra data after the root JSON object. The root was closed too early or another value was appended. Keep ALL top-level fields inside ONE outer { ... } object; after an array field closes with ], use a comma for the next field, not }. Do not append fields or another object after the final }.")
                continue
            if not self.started:
                if char in " \t\r\n":
                    continue
                if char == "`":
                    raise ValueError("Markdown fences are not JSON. Return the raw JSON object only, starting with {, without any backticks or commentary.")
                if char != "{":
                    raise ValueError("Return exactly one JSON object, starting with {, without commentary or an outer array.")
                self.started = True
            if self.string is not None:
                if self.key_frame is not None:
                    self.string += char
                if self.escaped:
                    self.escaped = False
                elif char == "\\":
                    self.escaped = True
                elif char == '"':
                    if self.key_frame is not None:
                        key = json.loads(self.string)
                        if key in self.key_frame["keys"]:
                            raise ValueError(f"Output repeats the JSON field {key[:80]!r} in the same object. Return each field exactly once, then close the object and finish.")
                        self.key_frame["keys"].add(key)
                        self.key_frame["key"] = False
                    self.string = self.key_frame = None
                continue
            if char == '"':
                self.string = '"'
                self.key_frame = self.stack[-1] if self.stack and self.stack[-1]["kind"] == "object" and self.stack[-1]["key"] else None
            elif char == "{":
                self.stack.append({"kind": "object", "keys": set(), "key": True})
            elif char == "[":
                self.stack.append({"kind": "array", "key": False})
            elif char in "}]":
                expected = "}" if self.stack and self.stack[-1]["kind"] == "object" else "]"
                if not self.stack or char != expected:
                    raise ValueError(f"Mismatched JSON container: expected {expected}, received {char}. Close objects with }} and arrays with ] in nesting order. Keep all top-level fields inside the single root object.")
                self.stack.pop()
                if not self.stack:
                    self.finished = True
            elif char == "," and self.stack and self.stack[-1]["kind"] == "object":
                self.stack[-1]["key"] = True
