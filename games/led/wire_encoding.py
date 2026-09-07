"""Clamp logical RGB to wire-safe payload channels (0..254).

255 is reserved by the controller frame header ([255, 255]), so payload
channels must never equal 255.
"""


def encode_wire_color(color):
    return (
        max(0, min(254, int(color[0]))),
        max(0, min(254, int(color[1]))),
        max(0, min(254, int(color[2]))),
    )
