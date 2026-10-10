#!/usr/bin/env python3
"""Reminders: add / list / del / done / undone / shift / tick / test / now.

Only the standard library. State lives in one JSON file in the data folder
(REMIND_PANE_DATA, default ~/.local/share/remind-pane). Delivery to Telegram is
optional (REMIND_PANE_TELEGRAM_TOKEN + REMIND_PANE_TELEGRAM_CHAT).
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
TEXT_MAX = 1000
MAX_ATTEMPTS = 1440
LATE_AFTER = timedelta(minutes=2)
REPEAT = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
REL = re.compile(r"^\+(\d+)([mhd])$")
SHIFT = re.compile(r"^([+-])(\d+)([mhd])$")
UNIT = {"m": "minutes", "h": "hours", "d": "days"}
ABS_FORMATS = ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M")
DEFAULTS = {"repeat": None, "attempts": 0, "failed": False, "last_error": None}


def data_dir():
    raw = os.environ.get("REMIND_PANE_DATA", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".local" / "share" / "remind-pane"


def data_file():
    return data_dir() / "reminders.json"


def zone():
    """The configured time zone, or None for the system's (DST-aware)."""
    name = os.environ.get("REMIND_PANE_TZ", "").strip()
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        raise ValueError(f"unknown time zone '{name}' (use an IANA name, e.g. Europe/Berlin)")


def local(dt):
    return dt.astimezone(zone())


def fmt(dt):
    return local(dt).strftime("%Y-%m-%d %H:%M %Z").strip()


def parse_when(raw, now):
    raw = raw.strip()
    m = REL.match(raw)
    if m:
        return now + timedelta(**{UNIT[m[2]]: int(m[1])})
    tz = zone()
    for f in ABS_FORMATS:
        try:
            naive = datetime.strptime(raw, f)
        except ValueError:
            continue
        # naive.astimezone() reads it as system local time, with the right DST
        return (naive.replace(tzinfo=tz) if tz else naive).astimezone(UTC)
    raise ValueError(f"cannot parse time '{raw}': use 'YYYY-MM-DD HH:MM', 'DD.MM.YYYY HH:MM' or '+30m' / '+2h' / '+1d'")


@contextmanager
def locked():
    data_dir().mkdir(parents=True, exist_ok=True)
    with open(data_dir() / "lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def load():
    path = data_file()
    if not path.exists():
        return {"version": 1, "items": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        # damaged file (disk, hand edit): use the previous copy instead of failing forever
        print("reminders.json is damaged, reading reminders.bak", file=sys.stderr)
        bak = path.with_suffix(".bak")
        state = json.loads(bak.read_text(encoding="utf-8"))
        shutil.copy2(bak, path)  # otherwise the next save() would overwrite the good copy with the bad file
    for i in state["items"]:
        for k, v in DEFAULTS.items():
            i.setdefault(k, v)
        i.setdefault("due", None)
    return state


def save(state):
    path = data_file()
    tmp = path.with_suffix(".tmp")
    if path.exists():
        shutil.copy2(path, path.with_suffix(".bak"))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def telegram_configured():
    return bool(os.environ.get("REMIND_PANE_TELEGRAM_TOKEN", "").strip() and os.environ.get("REMIND_PANE_TELEGRAM_CHAT", "").strip())


def tg_send(text):
    token = os.environ.get("REMIND_PANE_TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("REMIND_PANE_TELEGRAM_CHAT", "").strip()
    if not token or not chat:
        raise RuntimeError("Telegram is not configured: set REMIND_PANE_TELEGRAM_TOKEN and REMIND_PANE_TELEGRAM_CHAT")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        body = json.load(e)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", "unknown Telegram error"))


def render(item, now):
    due = datetime.fromisoformat(item["due"])
    msg = f"Reminder: {item['text']}"
    if now - due > LATE_AFTER:
        msg += f"\n(late, was due {fmt(due)})"
    return msg


def tick():
    if not telegram_configured():
        raise RuntimeError("nothing to deliver with: Telegram is not configured (reminders stay in the list and the pane)")
    now = datetime.now(UTC)
    with locked():
        state = load()
        for item in list(state["items"]):
            if item["due"] is None:
                continue
            due = datetime.fromisoformat(item["due"])
            if due > now or item["failed"] or item.get("done_at"):
                continue
            try:
                tg_send(render(item, now))
            except Exception as e:
                item["attempts"] += 1
                item["last_error"] = f"{type(e).__name__}: {e}"[:300]
                item["failed"] = item["attempts"] >= MAX_ATTEMPTS
                print(f"not sent {item['id']}: {item['last_error']}", file=sys.stderr)
                save(state)
                continue
            print(f"sent {item['id']}")
            if item["repeat"]:
                nxt = due + REPEAT[item["repeat"]]
                while nxt <= now:
                    nxt += REPEAT[item["repeat"]]
                item.update(due=nxt.isoformat(), attempts=0, last_error=None)
            else:
                state["items"].remove(item)
            save(state)


def cmd_add(a):
    now = datetime.now(UTC)
    when = None
    if a.when is not None:
        when = parse_when(a.when, now)
        if when <= now:
            raise ValueError("that time has already passed")
    elif a.repeat:
        raise ValueError("a repeat needs a date: add --when")
    text = a.text.strip()
    if not text or len(text) > TEXT_MAX:
        raise ValueError(f"text is empty or longer than {TEXT_MAX} characters")
    item = {
        "id": "",
        "text": text,
        "due": when.isoformat() if when else None,
        "repeat": a.repeat,
        "attempts": 0,
        "failed": False,
        "last_error": None,
    }
    with locked():
        state = load()
        taken = {i["id"] for i in state["items"]}
        while not item["id"] or item["id"] in taken:
            item["id"] = uuid.uuid4().hex[:8]
        state["items"].append(item)
        save(state)
    due_txt = fmt(when) if when else "no date"
    rep = f", repeat: {a.repeat}" if a.repeat else ""
    print(f"added {item['id']}: {due_txt}{rep}")


def by_due(state):
    return sorted(state["items"], key=lambda i: (i["due"] is None, i["due"] or ""))


def resolve(state, ref):
    for i in state["items"]:
        if i["id"] == ref:
            return i
    items = by_due(state)
    if ref.isdigit() and 1 <= int(ref) <= len(items):
        return items[int(ref) - 1]
    raise ValueError(f"no reminder {ref}")


def purge_done(state):
    """Reminders marked done on an earlier local date are removed."""
    today = datetime.now(zone()).date()
    keep = [i for i in state["items"]
            if not i.get("done_at") or local(datetime.fromisoformat(i["done_at"])).date() >= today]
    changed = len(keep) != len(state["items"])
    state["items"] = keep
    return changed


def cmd_list(a):
    with locked():
        state = load()
        if purge_done(state):
            save(state)
    items = by_due(state)
    if a.json:
        print(json.dumps([{
            "id": i["id"], "text": i["text"], "repeat": i["repeat"], "failed": i["failed"],
            "due": fmt(datetime.fromisoformat(i["due"])) if i["due"] else None,
            "done": bool(i.get("done_at")),
        } for i in items], ensure_ascii=False))
        return
    if not items:
        print("no reminders")
        return
    for n, i in enumerate(items, 1):
        due = fmt(datetime.fromisoformat(i["due"])) if i["due"] else "no date"
        rep = f" [{i['repeat']}]" if i["repeat"] else ""
        if i["failed"]:
            status = f"  (NOT DELIVERED: {i['last_error']})"
        elif i["attempts"]:
            status = f"  (attempts: {i['attempts']}, error: {i['last_error']})"
        else:
            status = ""
        if i.get("done_at"):
            print(f"{n}. {i['id']}  {due}{rep}  ~~{i['text']}~~ ✓")
        else:
            print(f"{n}. {i['id']}  {due}{rep}  {i['text']}{status}")


def cmd_del(a):
    with locked():
        state = load()
        item = resolve(state, a.ref)
        state["items"].remove(item)
        save(state)
    print(f"deleted {item['id']}")


def cmd_done(a):
    with locked():
        state = load()
        purge_done(state)
        for ref in a.refs:
            item = resolve(state, ref)
            item["done_at"] = datetime.now(UTC).isoformat()
        save(state)
    print("marked done: " + ", ".join(a.refs))


def cmd_undone(a):
    with locked():
        state = load()
        for ref in a.refs:
            resolve(state, ref).pop("done_at", None)
        save(state)
    print("unmarked: " + ", ".join(a.refs))


def cmd_shift(a):
    now = datetime.now(UTC)
    m = SHIFT.match(a.delta.strip())
    if not m:
        raise ValueError(f"cannot parse shift '{a.delta}': '+2h', '-30m', '+1d'")
    delta = timedelta(**{UNIT[m[3]]: int(m[2])})
    if m[1] == "-":
        delta = -delta
    with locked():
        state = load()
        item = resolve(state, a.ref)
        if item["due"] is None:
            raise ValueError("a reminder without a date has nothing to shift")
        new_due = datetime.fromisoformat(item["due"]) + delta
        if new_due <= now:
            raise ValueError("the new time has already passed")
        item.update(due=new_due.isoformat(), attempts=0, failed=False, last_error=None)
        save(state)
    print(f"moved {item['id']}: {fmt(new_due)}")


def cmd_now(_):
    print(local(datetime.now(UTC)).strftime("%Y-%m-%d %H:%M %Z, %a").replace("  ", " "))


def cmd_test(_):
    tg_send("Test: reminders work")
    print("test sent")


def main():
    p = argparse.ArgumentParser(prog="remind")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="add a reminder")
    a.add_argument("--when", help="'YYYY-MM-DD HH:MM' (your time zone) or '+30m' / '+2h' / '+1d'; without it the reminder has no date")
    a.add_argument("--text", required=True)
    a.add_argument("--repeat", choices=sorted(REPEAT))
    a.set_defaults(fn=cmd_add)

    ls = sub.add_parser("list", help="show reminders")
    ls.add_argument("--json", action="store_true", help="machine-readable output (for the pane)")
    ls.set_defaults(fn=cmd_list)

    d = sub.add_parser("del", help="delete a reminder by its number in list, or id")
    d.add_argument("ref")
    d.set_defaults(fn=cmd_del)

    dn = sub.add_parser("done", help="mark done (shown struck through until the end of the day, then gone)")
    dn.add_argument("refs", nargs="+", help="numbers from list, or ids")
    dn.set_defaults(fn=cmd_done)

    ud = sub.add_parser("undone", help="remove the done mark")
    ud.add_argument("refs", nargs="+", help="numbers from list, or ids")
    ud.set_defaults(fn=cmd_undone)

    s = sub.add_parser("shift", help="move a reminder by its number in list, or id")
    s.add_argument("ref")
    s.add_argument("--by", required=True, dest="delta", help="'+2h', '-30m', '+1d'; write it as --by=-30m")
    s.set_defaults(fn=cmd_shift)

    sub.add_parser("tick", help="send overdue reminders to Telegram (run it from a timer)").set_defaults(fn=lambda _: tick())
    sub.add_parser("test", help="send a test message to Telegram").set_defaults(fn=cmd_test)
    sub.add_parser("now", help="current time in the configured time zone").set_defaults(fn=cmd_now)

    args = p.parse_args()
    try:
        args.fn(args)
    except (ValueError, OverflowError, RuntimeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
