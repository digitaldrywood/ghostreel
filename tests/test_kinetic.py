#!/usr/bin/env python3
import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KineticStylesTests(unittest.TestCase):
    def test_outgoing_scene_stops_painting_during_incoming_fade(self):
        css = (ROOT / "src" / "kinetic.css").read_text()

        hidden_scene = re.search(r"\.scene\{([^}]*)\}", css)
        visible_scene = re.search(r"\.scene\.on\{([^}]*)\}", css)

        self.assertIsNotNone(hidden_scene)
        self.assertIsNotNone(visible_scene)
        transition = re.search(r"(?:^|;)transition:([^;]+)", hidden_scene.group(1))

        self.assertIsNotNone(transition)
        self.assertIn("visibility:hidden", hidden_scene.group(1))
        self.assertEqual("opacity .34s ease", transition.group(1))
        self.assertIn("visibility:visible", visible_scene.group(1))


if __name__ == "__main__":
    unittest.main()
