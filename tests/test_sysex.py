"""Decode the KThd/KTrk SysEx blob — strings, tracks, effects-locked, amp gain."""

import unittest

from _payloads import (
    AMP_SHAPES,
    amp_msg,
    make_blob,
    param_msg,
    performance_blob,
    rig_track,
    string_msg,
)

from kemperrig import _sysex
from kemperrig._sysex_edit import replace_string


class StringDecodeTest(unittest.TestCase):
    def test_extracts_string_params_in_order(self):
        blob = make_blob([[
            string_msg("PC_MesaDR_D01", 1),
            string_msg("Profile Co", 2),
            string_msg("2016-07-18", 3),
            param_msg(b"\x00\x04\x00", b"\x00\x40"),  # a numeric param — not a string
        ]])
        got = _sysex.decode_strings(_sysex.iter_messages(blob))
        self.assertEqual(got, ["PC_MesaDR_D01", "Profile Co", "2016-07-18"])


class TrackTest(unittest.TestCase):
    def test_performance_splits_into_header_plus_slots(self):
        header = [string_msg("Test Perf", 1)]
        slot = [param_msg(b"\x00\x04\x00", b"\x00\x40")]
        blob = make_blob([header, slot, slot, slot])
        self.assertEqual(len(_sysex.tracks(blob)), 4)

    def test_parses_standard_midi_magic(self):
        # some performances use real-MIDI MThd/MTrk chunks, not Kemper's KThd/KTrk
        blob = make_blob([[string_msg("X", 1)], [param_msg(b"\x00\x04\x00", b"\x00\x40")]], magic="M")
        self.assertEqual(len(_sysex.tracks(blob)), 2)
        self.assertEqual(_sysex.decode_strings(_sysex.iter_messages(blob)), ["X"])


class TruncatedBlobTest(unittest.TestCase):
    """A payload cut short is a ValueError naming the damage, not an IndexError."""

    def _blob(self) -> bytes:
        return make_blob([[string_msg("Rig", 1), amp_msg(5.0)]])

    def test_a_chunk_cut_short_is_a_value_error(self):
        for cut in (1, 10, 30):
            with self.subTest(cut=cut), self.assertRaisesRegex(ValueError, "truncated"):
                _sysex.iter_messages(self._blob()[:-cut])

    def test_an_event_overrunning_its_track_is_a_value_error(self):
        blob = bytearray(self._blob())
        blob[-2 - len(amp_msg(5.0))] += 8   # the last event's length byte, before payload + F7
        with self.assertRaisesRegex(ValueError, "truncated"):
            _sysex.iter_messages(bytes(blob))

    def test_a_whole_blob_still_parses(self):
        self.assertEqual(len(_sysex.iter_messages(self._blob())), 2)

    def test_bytes_after_the_last_chunk_are_a_value_error(self):
        for extra in (b"\x00", b"KTrk\x00\x00\x00"):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "after the last"):
                _sysex.tracks(self._blob() + extra)

    def test_a_header_chunk_overrunning_the_blob_is_a_value_error(self):
        with self.assertRaisesRegex(ValueError, "a KThd chunk declares 6 bytes, 4 present"):
            _sysex.tracks(self._blob()[:12])

    def test_a_tag_that_is_not_text_is_named_in_hex_on_one_line(self):
        with self.assertRaises(ValueError) as caught:
            _sysex.tracks(b"\n\x00\x01\x02" + (99).to_bytes(4, "big"))
        self.assertIn("a 0a 00 01 02 chunk", str(caught.exception))
        self.assertNotIn("\n", str(caught.exception))


class PerformanceTracksTest(unittest.TestCase):
    def test_a_performance_holds_a_header_and_five_slot_tracks(self):
        self.assertEqual(len(_sysex.performance_tracks(performance_blob(rig_track("A")))), 6)

    def test_any_other_count_is_a_value_error(self):
        blob = performance_blob(rig_track("A"))
        short = blob[:blob.rfind(b"KTrk")]
        with self.assertRaisesRegex(ValueError, "holds 5 tracks, not 6"):
            _sysex.performance_tracks(short)
        self.assertIsNone(_sysex.parse_performance(short))
        self.assertEqual(len(_sysex.tracks(short)), 5)

    def test_an_empty_payload_has_no_tracks(self):
        self.assertEqual(_sysex.performance_tracks(b""), [])


class UnreadTest(unittest.TestCase):
    def test_a_track_whose_events_stop_early_reports_the_bytes_left(self):
        blob = make_blob([[string_msg("Rig", 1), amp_msg(5.0)]])
        body = blob.index(b"KTrk") + 8
        second = blob.index(b"\xf0", blob.index(b"\xf0", body) + 1)
        bad = blob[:second] + b"\x90" + blob[second + 1:]
        self.assertEqual(_sysex.walk(bad)[1], [(0, len(blob) - (second - 1), len(blob) - body)])
        self.assertEqual(len(_sysex.iter_messages(bad)), 1)
        self.assertEqual(_sysex.walk(blob)[1], [])

    def test_bytes_after_the_last_event_are_unread_whatever_their_high_bit(self):
        blob = make_blob([[string_msg("A", 1)], [string_msg("B", 1)]])
        for track in (0, 1):
            for tail in (b"\x81", b"\xff\xff", b"\x81\x00", b"\x05"):
                with self.subTest(track=track, tail=tail.hex()):
                    odd = _with_tail(blob, track, tail)
                    found, unread = _sysex.walk(odd)
                    self.assertEqual([len(t) for t in found], [1, 1])
                    self.assertEqual([(n, k) for n, k, _ in unread], [(track, len(tail))])
                    renamed, n = replace_string(odd, _sysex._RIG_NAME_ADDRESS, "A", "Z")
                    self.assertEqual(n, 1)
                    self.assertEqual(_sysex.walk(renamed)[1], unread)

    def test_an_event_cut_off_at_the_end_of_its_track_does_not_parse_in_any_track(self):
        blob = make_blob([[string_msg("A", 1)], [string_msg("B", 1)]])
        for track in (0, 1):
            for tail in (b"\x00\xf0\x81", b"\x00\xf0\x05\xf7"):   # its length cut; its body cut
                with self.subTest(track=track, tail=tail.hex()):
                    bad = _with_tail(blob, track, tail)
                    with self.assertRaisesRegex(ValueError, "past the end of its track"):
                        _sysex.tracks(bad)
                    with self.assertRaisesRegex(ValueError, "past the end of its track"):
                        replace_string(bad, _sysex._RIG_NAME_ADDRESS, "A", "Z")


def _with_tail(blob: bytes, track: int, tail: bytes) -> bytes:
    """`blob` with `tail` appended to the body of its `track`-th track chunk."""
    out, pos, n = bytearray(), 0, -1
    while pos < len(blob):
        tag, size = blob[pos:pos + 4], int.from_bytes(blob[pos + 4:pos + 8], "big")
        body = blob[pos + 8:pos + 8 + size]
        if tag == b"KTrk":
            n += 1
            body += tail if n == track else b""
        out += tag + len(body).to_bytes(4, "big") + body
        pos += 8 + size
    return bytes(out)


class EffectsLockedTest(unittest.TestCase):
    def _perf(self, amp_values):
        shared = [
            param_msg(b"\x00\x04\x00", b"\x00\x40"),
            param_msg(b"\x00\x04\x01", b"\x00\x20"),
            param_msg(b"\x00\x05\x00", b"\x01\x00"),
            param_msg(b"\x00\x06\x00", b"\x00\x10"),
        ]
        header = [string_msg("Perf", 1)]
        slots = [shared + [param_msg(b"\x00\x0a\x00", v)] for v in amp_values]
        return make_blob([header, *slots])

    def test_locked_when_only_amp_differs(self):
        blob = self._perf([b"\x00\x01", b"\x00\x02", b"\x00\x03"])
        locked, total, ratio = _sysex.effects_locked(_sysex.tracks(blob)[1:])
        self.assertEqual((locked, total), (4, 5))
        self.assertAlmostEqual(ratio, 0.8, places=3)

    def test_fully_locked_when_all_slots_identical(self):
        blob = self._perf([b"\x00\x01", b"\x00\x01", b"\x00\x01"])
        locked, total, _ = _sysex.effects_locked(_sysex.tracks(blob)[1:])
        self.assertEqual((locked, total), (5, 5))

    def test_no_ratio_with_fewer_than_two_tracks_or_an_empty_first(self):
        one = _sysex.tracks(self._perf([b"\x00\x01"]))[1:]
        self.assertIsNone(_sysex.effects_locked(one)[2])
        self.assertIsNone(_sysex.effects_locked([[], *one])[2])


class AmpGainTest(unittest.TestCase):
    def test_decodes_gain_from_amp_block(self):
        blob = make_blob([[string_msg("Rig", 1), amp_msg(6.4)]])
        self.assertAlmostEqual(_sysex.amp_gain(_sysex.iter_messages(blob)), 6.4, places=2)

    def test_decodes_every_verified_amp_block_shape(self):
        for func, length in AMP_SHAPES:
            with self.subTest(func=func, length=length):
                blob = make_blob([[amp_msg(3.7, func=func, length=length)]])
                self.assertAlmostEqual(_sysex.amp_gain(_sysex.iter_messages(blob)), 3.7, places=2)

    def test_unverified_block_length_decodes_to_none(self):
        blob = make_blob([[amp_msg(3.7, length=60)]])
        self.assertIsNone(_sysex.amp_gain(_sysex.iter_messages(blob)))

    def test_forty_byte_block_off_the_amp_page_is_not_the_amp(self):
        blob = make_blob([[amp_msg(3.7, page=0x09)]])
        self.assertIsNone(_sysex.amp_gain(_sysex.iter_messages(blob)))

    def test_amp_page_block_not_starting_at_param_zero_is_ignored(self):
        blob = make_blob([[amp_msg(3.7, start=4)]])
        self.assertIsNone(_sysex.amp_gain(_sysex.iter_messages(blob)))

    def test_returns_none_without_amp_block(self):
        blob = make_blob([[string_msg("Rig", 1), param_msg(b"\x00\x04\x00", b"\x00\x40")]])
        self.assertIsNone(_sysex.amp_gain(_sysex.iter_messages(blob)))

    def test_a_gain_byte_that_is_not_7_bit_data_decodes_to_none(self):
        """SysEx data bytes are 7-bit; with bit 7 set the value would read up to 20."""
        for offset in (0, 1):
            with self.subTest(offset=offset):
                msg = bytearray(amp_msg(9.9))
                msg[3 + 14 + offset] |= 0x80
                blob = make_blob([[bytes(msg)]])
                self.assertIsNone(_sysex.amp_gain(_sysex.iter_messages(blob)))


if __name__ == "__main__":
    unittest.main()
