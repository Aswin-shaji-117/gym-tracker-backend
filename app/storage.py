
import json
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.RLock()

DEFAULTS = {
    "users": [],
    "plans": [],
    "sessions": [],
    "body_metrics": [],
}

def _path(name: str) -> Path:
    if name not in DEFAULTS:
        raise ValueError("Unknown data collection")
    return DATA_DIR / f"{name}.json"

def read_all(name: str) -> list[dict[str, Any]]:
    path = _path(name)
    with _LOCK:
        if not path.exists():
            path.write_text("[]", encoding="utf-8")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            raise RuntimeError(f"{path.name} contains invalid JSON. Restore it from backup.")

def write_all(name: str, records: list[dict[str, Any]]) -> None:
    path = _path(name)
    with _LOCK:
        # Atomic replace helps avoid partially-written JSON if the process stops mid-write.
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

def add_record(name: str, record: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        records = read_all(name)
        records.append(record)
        write_all(name, records)
    return record

def update_record(name: str, record_id: str, user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    with _LOCK:
        records = read_all(name)
        for i, item in enumerate(records):
            if item.get("id") == record_id and item.get("user_id") == user_id:
                records[i] = {**item, **changes}
                write_all(name, records)
                return records[i]
    return None

def delete_record(name: str, record_id: str, user_id: str) -> bool:
    with _LOCK:
        records = read_all(name)
        filtered = [r for r in records if not (r.get("id") == record_id and r.get("user_id") == user_id)]
        if len(filtered) == len(records):
            return False
        write_all(name, filtered)
        return True
