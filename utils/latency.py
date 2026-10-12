import json, time
from contextlib import contextmanager
from utils.logger import logger


class TurnTrace:
    # name -> (start_mark, end_mark). None is logged when either mark is missing.
    GAPS = {
        "loop_scheduling_delay": ("stt_final", "turn_task_started"),
        "stt_format_wait":       ("eos", "stt_final"),
        "pre_llm_overhead":      ("lock_acquired", "llm_request_sent"),
        "llm_first_chunk":       ("llm_request_sent", "llm_first_chunk"),
        "llm_total":             ("llm_request_sent", "llm_done"),
        "llm2_first_chunk":      ("llm2_request_sent", "llm2_first_chunk"),
        "llm2_total":            ("llm2_request_sent", "llm2_done"),
        "tts_connect":           ("tts_request_sent", "murf_connected"),
        "tts_first_byte":        ("murf_text_sent", "tts_first_byte"),
        "first_audio_send":      ("tts_first_byte", "first_audio_sent"),
        "EOS_TO_FIRST_AUDIO":    ("eos", "first_audio_sent"),
        "lock_wait":             ("turn_task_started", "lock_acquired"),
    }

    def __init__(self, session_id: str, turn_id: int):
        self.session_id, self.turn_id = session_id, turn_id
        self.marks: dict[str, float] = {}
        self.spans: list[dict] = []
        self.meta: dict = {}
        self.interrupted = False

    def mark(self, name: str, t: float | None = None) -> None:
        # setdefault: the FIRST time a mark is hit is the one that sticks
        self.marks.setdefault(name, time.perf_counter() if t is None else t)

    @contextmanager
    def span(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.spans.append({"name": name,
                               "ms": round((time.perf_counter() - start) * 1000, 1)})

    def _gap(self, a: str, b: str):
        if a in self.marks and b in self.marks:
            return round((self.marks[b] - self.marks[a]) * 1000, 1)
        return None

    def log(self) -> None:
        record = {
            "event": "turn_latency",
            "session_id": self.session_id,
            "turn": self.turn_id,
            "interrupted": self.interrupted,
            "ms": {k: self._gap(a, b) for k, (a, b) in self.GAPS.items()},
            "spans": self.spans,
            **self.meta,
        }
        logger.info(json.dumps(record))