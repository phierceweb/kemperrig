"""`replace_string`: one string parameter rewritten in place, every other byte kept."""

import unittest

from _payloads import _track_body, amp_msg, make_blob, performance_blob, rig_track, string_msg

from kemperrig import _sysex
from kemperrig._sysex_edit import replace_string

NAME = b"\x00\x00\x01"


def _names(blob: bytes) -> list[str | None]:
    return [_sysex.addressed_strings(t).get(NAME) for t in _sysex.tracks(blob)]


class ReplaceStringTest(unittest.TestCase):
    def test_a_rig_name_is_rewritten_and_nothing_else_moves(self):
        blob = make_blob([rig_track("Old", cab="Cab") + [amp_msg(6.0)]])
        out, n = replace_string(blob, NAME, "Old", "Brand New")
        self.assertEqual(n, 1)
        self.assertEqual(_names(out), ["Brand New"])
        self.assertEqual(_sysex.amp_gain(_sysex.iter_messages(out)), _sysex.amp_gain(
            _sysex.iter_messages(blob)))
        self.assertEqual(_sysex.addressed_strings(_sysex.iter_messages(out))[b"\x00\x00\x20"],
                         "Cab")

    def test_renaming_back_restores_the_exact_bytes(self):
        blob = make_blob([rig_track("Old") + [amp_msg(6.0)]])
        there, _ = replace_string(blob, NAME, "Old", "A much longer name than before")
        back, _ = replace_string(there, NAME, "A much longer name than before", "Old")
        self.assertEqual(back, blob)

    def test_no_match_returns_the_blob_untouched(self):
        blob = make_blob([rig_track("Other")])
        out, n = replace_string(blob, NAME, "Old", "New")
        self.assertEqual((out, n), (blob, 0))

    def test_only_the_named_address_is_rewritten(self):
        blob = make_blob([[string_msg("Old", 0x01), string_msg("Old", 0x02)]])
        out, _ = replace_string(blob, NAME, "Old", "New")
        self.assertEqual(_sysex.addressed_strings(_sysex.iter_messages(out))[b"\x00\x00\x02"],
                         "Old")

    def test_tracks_limits_the_rewrite_to_those_slots(self):
        blob = performance_blob(rig_track("Old"), rig_track("Old"), rig_track("Keep"))
        out, n = replace_string(blob, NAME, "Old", "New", tracks={2})
        self.assertEqual(n, 1)
        self.assertEqual(_names(out), [None, "Old", "New", "Keep", None, None])

    def test_bytes_after_the_sysex_events_survive(self):
        tail = b"\x00\xff\x2f\x00"                     # an end-of-track meta event
        body = _track_body([string_msg("Old", 0x01)]) + tail
        head = make_blob([[]])[:14]
        blob = head + b"KTrk" + len(body).to_bytes(4, "big") + body
        out, _ = replace_string(blob, NAME, "Old", "Newer")
        self.assertTrue(out.endswith(tail))
        self.assertEqual(int.from_bytes(out[18:22], "big"), len(out) - 22)
        self.assertEqual(_names(out), ["Newer"])

    def test_standard_midi_chunk_tags_too(self):
        blob = make_blob([rig_track("Old")], magic="M")
        self.assertEqual(_names(replace_string(blob, NAME, "Old", "New")[0]), ["New"])

    def test_a_truncated_blob_is_a_value_error(self):
        blob = make_blob([rig_track("Old")])
        with self.assertRaises(ValueError):
            replace_string(blob[:-3], NAME, "Old", "New")


if __name__ == "__main__":
    unittest.main()
