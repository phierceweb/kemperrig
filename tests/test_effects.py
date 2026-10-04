"""Effect-chain decode: stomp/delay/reverb module Type (param 0) + On/Off (param 3, stomp pages)."""

import contextlib
import io
import os
import tempfile
import unittest

from _fixture import build_rmbackup
from _payloads import f08_msg, make_blob, module_msg

from kemperrig import _enums, _sysex, _sysex_effects


def _chain(*module_msgs):
    return _sysex_effects.effect_chain(_sysex.iter_messages(make_blob([list(module_msgs)])))


class EffectChainTest(unittest.TestCase):
    """`_enums` holds the active table in module state, so pin it — otherwise a sibling test
    that runs the CLI (which installs the real Rig Manager table) changes these results."""

    def setUp(self):
        _enums.install(None)

    def tearDown(self):
        _enums.install(None)

    def test_stomp_type_and_onoff(self):
        # page 0x32 = Stomp A: param0=Type(33=Green Scream), param1,2 filler, param3=On
        fx = _chain(module_msg(0x32, [33, 0, 0, 1]))
        self.assertEqual(len(fx), 1)
        self.assertEqual(fx[0].slot, "A")
        self.assertEqual(fx[0].type_value, 33)
        self.assertEqual(fx[0].type_name, "Green Scream")
        self.assertTrue(fx[0].on)

    def test_block_values_stay_14_bit_when_a_high_byte_is_not_7_bit_data(self):
        msg = bytearray(module_msg(0x32, [33, 0, 0, 1]))
        msg[3 + 6] |= 0x80   # the type value's high byte
        values = _sysex_effects.blocks(_sysex.iter_messages(make_blob([[bytes(msg)]])))
        self.assertEqual(values[(0x32, 0)][0], 33)

    def test_empty_slot_skipped(self):
        # type 0 = empty slot -> not in the chain
        self.assertEqual(_chain(module_msg(0x32, [0, 0, 0, 0])), [])

    def test_unknown_type_value_has_no_name(self):
        fx = _chain(module_msg(0x33, [9999, 0, 0, 1]))
        self.assertEqual(fx[0].slot, "B")
        self.assertEqual(fx[0].type_value, 9999)
        self.assertIsNone(fx[0].type_name)

    def test_modern_reverb_is_page_0x3d_on_the_global_enum(self):
        """0x3d carries the REV module and indexes the same enum as every other slot
        (evidence in docs/format.md)."""
        fx = _chain(module_msg(0x3d, [177, 0, 0, 1]))
        self.assertEqual(fx[0].slot, "REV")
        self.assertEqual(fx[0].type_value, 177)
        self.assertEqual(fx[0].type_name, "Legacy Reverb")
        self.assertTrue(fx[0].on)

    def test_legacy_reverb_is_page_0x4b_on_its_own_index_based_list(self):
        """Pre-2019 rigs put the reverb on 0x4b, where the value is a room size, not a type.

        Naming it from the global enum would call value 1 "Wah Wah"."""
        fx = _chain(module_msg(0x4b, [1, 0, 0, 1]))
        self.assertEqual(fx[0].slot, "REV")
        self.assertEqual(fx[0].type_value, 1)
        self.assertIsNone(fx[0].type_name)      # no legacy list without Stomps.xml installed
        self.assertNotEqual(fx[0].type_name, "Wah Wah")

    def test_the_two_reverb_pages_are_generations_not_siblings(self):
        """The two never co-occur (docs/format.md). If one ever does, prefer the modern page."""
        fx = _chain(module_msg(0x3d, [178, 0, 0, 1]), module_msg(0x4b, [1, 0, 0, 1]))
        self.assertEqual([e.slot for e in fx], ["REV"])
        self.assertEqual(fx[0].type_name, "Natural Reverb")

    def test_deprecated_delay_module_ignored(self):
        # Delay page 0x4a is dead since OS 4.0 ("addressing results in no action") -> not a slot
        self.assertEqual(_chain(module_msg(0x4a, [146, 0, 0, 1])), [])

    def test_chain_order_is_signal_flow(self):
        fx = _chain(module_msg(0x3d, [177, 0, 0, 0]), module_msg(0x32, [33, 0, 0, 1]))
        self.assertEqual([e.slot for e in fx], ["A", "REV"])  # A before REV regardless of order

    def test_cli_rig_shows_effects(self):
        from kemperrig.cli import main
        blob = make_blob([[module_msg(0x32, [33, 0, 0, 1]), module_msg(0x3d, [177, 0, 0, 0])]])
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "fx.rmbackup"),
            rigs=[{"name": "FXRig", "amp_model": "Recto", "blob": blob}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["rig", path, "FXRig"])   # installs whatever table this machine has
        out = buf.getvalue()
        self.assertIn("A=Green Scream", out)        # stomp: named from the global enum
        self.assertIn("REV=Legacy Reverb", out)     # REV: the same enum, on page 0x3d


class UndecodedSlotTest(unittest.TestCase):
    """A slot present only in the function-08 framing has an unknown type — possibly empty —
    so it is reported as undecoded rather than dropped or guessed."""

    def setUp(self):
        _enums.install(None)

    def _undecoded(self, slot):
        return _sysex_effects.Effect(slot=slot, type_value=None, type_name=None, on=None,
                                     category=None, decoded=False)

    def test_a_legacy_reverb_page_only_in_function_08(self):
        self.assertEqual(_chain(f08_msg(0x4b)), [self._undecoded("REV")])

    def test_a_modern_reverb_page_only_in_function_08(self):
        self.assertEqual(_chain(f08_msg(0x3d)), [self._undecoded("REV")])

    def test_a_stomp_page_only_in_function_08(self):
        self.assertEqual(_chain(f08_msg(0x32)), [self._undecoded("A")])

    def test_a_function_02_empty_slot_wins_over_function_08(self):
        self.assertEqual(_chain(module_msg(0x32, [0, 0, 0, 0]), f08_msg(0x32)), [])

    def test_a_function_02_loaded_slot_wins_over_function_08(self):
        (fx,) = _chain(module_msg(0x32, [33, 0, 0, 1]), f08_msg(0x32))
        self.assertTrue(fx.decoded)
        self.assertEqual(fx.type_value, 33)

    def test_a_function_02_reverb_wins_over_a_function_08_one(self):
        (fx,) = _chain(module_msg(0x4b, [3, 0, 0, 0]), f08_msg(0x3d))
        self.assertTrue(fx.decoded)

    def test_a_function_02_block_with_no_params_is_an_empty_slot(self):
        self.assertEqual(_chain(module_msg(0x32, [])), [])

    def test_a_function_08_block_at_another_start_number_is_ignored(self):
        self.assertEqual(_chain(f08_msg(0x32, start=4)), [])

    def test_order_is_still_signal_flow(self):
        fx = _chain(f08_msg(0x4b), module_msg(0x3c, [164, 0, 0, 1]), f08_msg(0x32))
        self.assertEqual([e.slot for e in fx], ["A", "DLY", "REV"])

    def test_a_decoded_effect_says_so(self):
        (fx,) = _chain(module_msg(0x32, [33, 0, 0, 1]))
        self.assertTrue(fx.decoded)

    def test_the_text_label_marks_an_undecoded_slot(self):
        from kemperrig._views._library import _effect_label
        self.assertEqual(_effect_label(self._undecoded("REV")), "REV=?")


if __name__ == "__main__":
    unittest.main()
