# Dolby Vision RPU parsing dispatch. All bit-level parsing is done by
# native.py's libdovi ctypes bindings (quietvoid's dovi_tool); see
# README.md. parse_hevc_nal62 takes the escaped HEVC NAL
# unit 62 whole (7C 01 header + payload, as delivered by the dovi.rpu
# sidedata key); parse_av1_t35 takes the Dolby Vision ITU-T T.35 metadata
# OBU payload from the country code (B5 00 3B...). Both return the resolved
# dict from native.py, or None on any failure, whether no libdovi is
# loadable, malformed input, or anything else. This layer never raises,
# but libdovi itself can still panic and abort the process; see README.md.

from . import native as _native


def parse_hevc_nal62(nal):
    return _native.native_parse_hevc_nal62(nal)


def parse_av1_t35(payload):
    return _native.native_parse_av1_t35(payload)
