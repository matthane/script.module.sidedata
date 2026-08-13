"""service.py, the sidedata addon's Kodi service: publishes parse_sidedata's
output as Home window properties so skins and other non-python consumers can
read the same fields the python module exposes. See README.md's "From a skin"
section for the naming rules this mirrors from FIELDS.md.

The flattening functions (flatten_sidedata and its helpers) take a plain
dict and return a plain {property_name: string_value} dict; they touch no
xbmc API and are unit-tested directly against representative dicts. The run
loop below is the only part that talks to xbmc/xbmcgui.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import sidedata  # noqa: E402

import xbmc  # noqa: E402
import xbmcgui  # noqa: E402

_WINDOW_ID = 10000
_INFO_LABEL = 'Player.Process(video.sidedata)'
# 100ms so property updates track scene cuts; the unchanged-json skip below
# keeps idle ticks cheap
_POLL_INTERVAL = 0.1


def _format_float(value):
    if not math.isfinite(value):
        return None
    text = repr(value)
    if 'e' in text or 'E' in text:
        text = format(value, '.10f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('', '-', '-0'):
        text = '0'
    return text


def _format_scalar(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _flatten_dict(prefix, value, out):
    for key, val in value.items():
        _flatten_value(prefix + '.' + key, val, out)


def _flatten_value(prop, value, out):
    if value is None:
        return
    if isinstance(value, dict):
        _flatten_dict(prop, value, out)
        return
    if isinstance(value, tuple):
        if len(value) == 2:
            _flatten_value(prop + '.x', value[0], out)
            _flatten_value(prop + '.y', value[1], out)
        return
    if isinstance(value, list):
        if not value:
            return
        formatted = [_format_scalar(v) for v in value]
        if all(f is not None for f in formatted):
            out[prop] = ' '.join(formatted)
        return
    formatted = _format_scalar(value)
    if formatted is not None:
        out[prop] = formatted


# target nits snapping (convert.py) and duplicate target_display_index
# blocks both let two entries land on the same key; later ones get a -N
# ordinal suffix instead of silently overwriting the first entry's fields
def _ordinal_key(base, counts):
    counts[base] = counts.get(base, 0) + 1
    ordinal = counts[base]
    if ordinal == 1:
        return str(base)
    return '%s-%d' % (base, ordinal)


def _flatten_trim_list(prefix, entries, index_prop, out):
    if not entries:
        return
    out[prefix + '.count'] = str(len(entries))
    tokens = []
    counts = {}
    for entry in entries:
        nits = entry.get('nits')
        if nits is None:
            continue
        key = _ordinal_key(nits, counts)
        tokens.append(key)
        _flatten_dict(prefix + '.' + key, entry, out)
    if tokens:
        out[index_prop] = ' '.join(tokens)
    _flatten_dict(prefix + '.first', entries[0], out)
    _flatten_dict(prefix + '.last', entries[-1], out)


def _flatten_l10(prefix, entries, index_prop, out):
    if not entries:
        return
    out[prefix + '.count'] = str(len(entries))
    tokens = []
    counts = {}
    for entry in entries:
        index = entry.get('target_display_index')
        if index is None:
            continue
        key = _ordinal_key(index, counts)
        tokens.append(key)
        _flatten_dict(prefix + '.' + key, entry, out)
    if tokens:
        out[index_prop] = ' '.join(tokens)


def _flatten_distribution(prefix, entries, out):
    if not entries:
        return
    out[prefix + '.count'] = str(len(entries))
    tokens = []
    counts = {}
    for entry in entries:
        percentage = entry.get('percentage')
        if percentage is None:
            continue
        key = _ordinal_key(percentage, counts)
        tokens.append(key)
        _flatten_value(prefix + '.' + key, entry.get('nits'), out)
    if tokens:
        out[prefix + '.percentages'] = ' '.join(tokens)


def _flatten_rpu(prefix, rpu, out):
    if rpu is None:
        return
    for key, value in rpu.items():
        if key == 'l2':
            _flatten_trim_list(prefix + '.l2', value, prefix + '.l2.nits', out)
        elif key == 'l8':
            _flatten_trim_list(prefix + '.l8', value, prefix + '.l8.nits', out)
        elif key == 'l10':
            _flatten_l10(prefix + '.l10', value, prefix + '.l10.indexes', out)
        else:
            _flatten_value(prefix + '.' + key, value, out)


def _flatten_hdr10plus(prefix, hdr10plus, out):
    if hdr10plus is None:
        return
    for key, value in hdr10plus.items():
        if key == 'distribution':
            _flatten_distribution(prefix + '.distribution', value, out)
        else:
            _flatten_value(prefix + '.' + key, value, out)


def _is_present(value):
    if value is None:
        return False
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _flatten_presence(parsed, out):
    config = parsed.get('config')
    rpu = parsed.get('rpu')
    hdr10plus = parsed.get('hdr10plus')
    mdcv = parsed.get('mdcv')
    cll = parsed.get('cll')

    sections = (parsed.get('flags'), parsed.get('structure'), config, rpu, hdr10plus, mdcv, cll)
    if any(_is_present(section) for section in sections):
        out['sidedata.present'] = 'true'
    if _is_present(config) or _is_present(rpu):
        out['sidedata.dovi.present'] = 'true'
    if _is_present(hdr10plus):
        out['sidedata.hdr10plus.present'] = 'true'
    if _is_present(mdcv):
        out['sidedata.mdcv.present'] = 'true'
    if _is_present(cll):
        out['sidedata.cll.present'] = 'true'


def flatten_sidedata(parsed):
    out = {}
    if not isinstance(parsed, dict):
        return out
    _flatten_value('sidedata.flags', parsed.get('flags'), out)
    _flatten_value('sidedata.structure', parsed.get('structure'), out)
    _flatten_value('sidedata.config', parsed.get('config'), out)
    _flatten_rpu('sidedata.rpu', parsed.get('rpu'), out)
    _flatten_hdr10plus('sidedata.hdr10plus', parsed.get('hdr10plus'), out)
    _flatten_value('sidedata.mdcv', parsed.get('mdcv'), out)
    _flatten_value('sidedata.cll', parsed.get('cll'), out)
    _flatten_presence(parsed, out)
    return out


def _clear_keys(window, published, keys):
    # published must track exactly what's really on the window at every
    # step, not just at the end, so a setProperty/clearProperty raising
    # partway through never orphans a key that _clear later forgets about
    for key in keys:
        try:
            window.clearProperty(key)
        except Exception:
            continue
        published.pop(key, None)


def _publish(window, published, flat):
    for key, value in flat.items():
        if published.get(key) != value:
            window.setProperty(key, value)
            published[key] = value
    _clear_keys(window, published, [key for key in published if key not in flat])


def _clear(window, published):
    _clear_keys(window, published, list(published))


def _read_label(player):
    if not player.isPlayingVideo():
        return ''
    return xbmc.getInfoLabel(_INFO_LABEL)


def _tick(player, window, state):
    try:
        label = _read_label(player)
        if label == state['label']:
            return
        state['label'] = label

        if not label:
            if state['published']:
                _clear(window, state['published'])
            return

        flat = flatten_sidedata(sidedata.parse_sidedata(label))
        _publish(window, state['published'], flat)
    except Exception:
        try:
            _clear(window, state['published'])
        except Exception:
            pass
        state['label'] = None
        raise


def run():
    monitor = xbmc.Monitor()
    player = xbmc.Player()
    window = xbmcgui.Window(_WINDOW_ID)
    state = {'label': None, 'published': {}}
    # only warn on the first tick of a failing run, not every 100ms of it
    tick_failed = False

    while not monitor.abortRequested():
        try:
            _tick(player, window, state)
        except Exception:
            if not tick_failed:
                xbmc.log('script.module.sidedata: service tick failed, clearing properties',
                         xbmc.LOGWARNING)
            tick_failed = True
        else:
            tick_failed = False
        if monitor.waitForAbort(_POLL_INTERVAL):
            break

    # best-effort so a service stopped independently of Kodi doesn't leave
    # frozen properties behind
    _clear(window, state['published'])


if __name__ == '__main__':
    run()
