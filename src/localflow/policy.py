from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    hwnd: int
    pid: int
    process: str
    runtime_id: tuple[int, ...]
    automation_id: str
    name: str
    password: bool
    editable: bool
    known: bool = True

def check_target(target, config):
    if target is None or not target.known:
        return False, "Focused field cannot be verified. Preview only."
    if target.password:
        return False, "Password field blocked."
    if target.process.lower() in [x.lower() for x in config.deny_processes]:
        return False, "Application is on the denylist."
    label = f"{target.name} {target.automation_id}".lower()
    if any(x.lower() in label for x in config.deny_name_fragments):
        return False, "Sensitive field blocked."
    if not target.editable or not target.runtime_id:
        return False, "Field is not an identifiable editable control. Preview only."
    return True, "Allowed"


def same_target(before, after):
    return (before is not None and after is not None and before.known and after.known
            and before.hwnd == after.hwnd and before.pid == after.pid
            and before.runtime_id == after.runtime_id
            and before.automation_id == after.automation_id)


def insertion_allowed(before, after, config):
    if not config.auto_insert:
        return False, "Automatic insertion is off. Preview ready."
    ok, why = check_target(before, config)
    if not ok:
        return ok, why
    if not same_target(before, after):
        return False, "Focus changed. Preview ready; no text inserted."
    return check_target(after, config)
