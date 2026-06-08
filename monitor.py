import time
import json as _json
import functools
from datetime import datetime
from config import LOG_FILE, log
from http_client import _ctx_api_calls

_STATS_START: float = time.monotonic()
_STATS: dict[str, dict] = {}


def _monitor(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        api_calls: list = []
        token = _ctx_api_calls.set(api_calls)
        t0 = time.monotonic()
        result, error = None, None
        try:
            result = await fn(*args, **kwargs)
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            _ctx_api_calls.reset(token)
            elapsed = round((time.monotonic() - t0) * 1000)
            result_str = _json.dumps(result, ensure_ascii=False, default=str) if result else ""
            entry = {
                "ts":             datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "tool":           fn.__name__,
                "args":           {k: v for k, v in kwargs.items() if v is not None},
                "tokens_out_est": len(result_str) // 4,
                "elapsed_ms":     elapsed,
                "api_calls":      api_calls,
                "error":          error,
            }
            try:
                if LOG_FILE:
                    with open(LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
                else:
                    log.info("CALL %s", _json.dumps(entry, ensure_ascii=False, default=str))
            except Exception:
                pass
            s = _STATS.setdefault(fn.__name__, {
                "calls": 0, "errors": 0, "total_ms": 0, "total_tokens": 0, "last_called": None,
            })
            s["calls"]        += 1
            s["errors"]       += 1 if error else 0
            s["total_ms"]     += elapsed
            s["total_tokens"] += entry["tokens_out_est"]
            s["last_called"]   = entry["ts"]
    return wrapper
