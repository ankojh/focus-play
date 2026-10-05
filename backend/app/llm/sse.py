"""Bounded incremental SSE decoding (including UTF-8 and CR/LF boundaries)."""
import codecs


class SSEDecoder:
    def __init__(self, limit=65536, total_limit=2_000_000):
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.limit, self.total_limit = limit, total_limit
        self.total = 0
        self.line = ""
        self.data = []
        self.frame_size = 0
        self.after_cr = False

    def feed(self, chunk: bytes):
        self.total += len(chunk)
        if self.total > self.total_limit:
            raise ValueError("Model SSE stream is too large.")
        frames = []
        for char in self.decoder.decode(chunk):
            if self.after_cr and char == "\n":
                self.after_cr = False
                continue
            self.after_cr = char == "\r"
            if char in "\r\n":
                line, self.line = self.line, ""
                self.frame_size += len(line) + 1
                if self.frame_size > self.limit:
                    raise ValueError("Model SSE frame is too large.")
                if not line:
                    if self.data:
                        frames.append("\n".join(self.data))
                    self.data = []
                    self.frame_size = 0
                elif line.startswith("data:"):
                    value = line[5:]
                    self.data.append(value[1:] if value.startswith(" ") else value)
                # comments/id/event/retry are not content
            else:
                self.line += char
                if len(self.line) + self.frame_size > self.limit:
                    raise ValueError("Model SSE frame is too large.")
        return frames

    def finish(self):
        self.decoder.decode(b"", final=True)
        if self.line or self.data:
            raise ValueError("The SSE stream ended inside a frame.")
