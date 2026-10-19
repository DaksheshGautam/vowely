"""Friendly microphone choices, backed by Windows' current WASAPI endpoints."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Microphone:
    name: str
    index: int


def normalized(name):
    return re.sub(r'\s+', ' ', name).strip().casefold()


def is_microphone(name):
    value = normalized(name)
    return not any(x in value for x in ('stereo mix', 'what u hear', 'loopback',
                                         'sound mapper', 'primary sound capture',
                                         'pc speaker', 'wave out mix'))


def same_endpoint(canonical, device, host):
    a, b = normalized(canonical), normalized(device)
    return a == b or (host == 'MME' and len(b) >= 28 and a.startswith(b))


def microphones(sd, advanced=False, selected=None):
    """Query formats only; never open a capture stream or change the default mic.

    WASAPI enumerates active endpoints; WDM-KS/legacy host lists also contain
    aliases and disconnected drivers. Use WASAPI for names and one compatible
    16 kHz capture route per endpoint. Keep an explicit saved route unchanged.
    """
    devices = list(sd.query_devices())
    if not devices:
        return []
    hosts = list(sd.query_hostapis())
    inputs = [(i, d, hosts[d['hostapi']]['name']) for i, d in enumerate(devices)
              if d['max_input_channels'] > 0]
    if advanced:
        return [Microphone(f"{d['name']} — {host} (device {i})", i) for i, d, host in inputs]
    active = [(i, d, host) for i, d, host in inputs
              if host == 'Windows WASAPI' and is_microphone(d['name'])]
    # If WASAPI is unavailable, provide a deduplicated detected list without
    # pretending to know the devices' connection states.
    if not active:
        seen = set()
        for item in inputs:
            key = normalized(item[1]['name'])
            if is_microphone(key) and key not in seen:
                active.append(item)
                seen.add(key)
    result = []
    counts = {}
    for _, d, _ in active:
        key = normalized(d['name'])
        counts[key] = counts.get(key, 0) + 1
    for canonical_index, canonical, canonical_host in active:
        name = canonical['name']
        # Identically named physical endpoints cannot safely share a legacy
        # name-based route: retain their individual WASAPI indexes.
        candidates = [item for item in inputs if same_endpoint(name, item[1]['name'], item[2])]
        if counts[normalized(name)] > 1:
            candidates = [(canonical_index, canonical, canonical_host)]
        candidates.sort(key=lambda item: (item[0] != selected,
                                         {'Windows WASAPI': 0, 'MME': 1, 'Windows DirectSound': 2}.get(item[2], 9)))
        route = None
        for i, _, _ in candidates:
            try:
                sd.check_input_settings(device=i, channels=1, dtype='int16', samplerate=16000)
                route = i
                break
            except Exception:
                continue
        if route is not None:
            result.append(Microphone(name, route))
    return result


def default_input_label(sd):
    try:
        device = sd.query_devices(kind='input')
        return f"Windows default — {device['name']}"
    except Exception:
        return 'Windows default microphone'
