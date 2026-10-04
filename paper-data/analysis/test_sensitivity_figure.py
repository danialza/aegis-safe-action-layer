"""Figure 4 restyling must preserve all six curves and both timing references."""
import json
import math
import unittest
from unittest.mock import patch

import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from matplotlib.text import Text
import numpy as np

import build_hardware_figures as builder


class SensitivityFigureTest(unittest.TestCase):
    def test_muted_serif_style_preserves_every_value(self):
        data = json.loads((builder.HERE / "hardware_summary.json").read_text())
        curves = data["threshold_sensitivity"]
        thresholds = curves[0]["thresholds_s"]
        with patch.object(Figure, "savefig"), patch.object(plt, "close"):
            builder.plot_sensitivity(thresholds, curves)
            fig = plt.gcf()
        try:
            fig.canvas.draw()
            self.assertEqual(len(fig.axes), 2)
            for ax, rate in zip(fig.axes, builder.RATES):
                self.assertEqual(len(ax.lines), 4)
                for line, method, marker, style in zip(
                        ax.lines[:3], builder.METHODS, ("o", "s", "^"), ("-", "--", ":")):
                    expected = next(c for c in curves if c["rate"] == rate and c["method"] == method)
                    self.assertEqual(len(line.get_xdata()), 101)
                    np.testing.assert_array_equal(line.get_xdata(), thresholds)
                    np.testing.assert_array_equal(line.get_ydata(), expected["mean_run_fraction_percent"])
                    self.assertEqual(line.get_marker(), marker)
                    self.assertEqual(line.get_linestyle(), style)
                    palette = {"AEGIS": "#204A72", "Trust12": "#B85C16", "Trust32": "#704098"}
                    self.assertEqual(to_rgba(line.get_color()), to_rgba(palette[method]))
                np.testing.assert_array_equal(ax.lines[3].get_xdata(), [.6, .6])
                self.assertEqual(len(ax.patches), 1)
                band = ax.patches[0]
                onsets = [.4 * math.log((.65 - h) / (.65 - .5)) for h in (.0325, 0)]
                self.assertAlmostEqual(band.get_x(), onsets[0])
                self.assertAlmostEqual(band.get_width(), onsets[1] - onsets[0])
                for color in [ax.lines[3].get_color(), band.get_facecolor()]:
                    r, g, b, _ = to_rgba(color)
                    self.assertEqual(r, g)
                    self.assertEqual(g, b)
                self.assertFalse(any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()))
            renderer = fig.canvas.get_renderer()
            self.assertEqual(len(fig.legends), 0)
            self.assertEqual([t.get_text() for t in fig.texts], ["Analysis threshold for evidence age (s)"])
            for text in fig.findobj(Text):
                if not text.get_visible() or not text.get_text():
                    continue
                self.assertEqual(text.get_fontweight(), "normal")
                self.assertIn(text.get_fontfamily()[0], ("Palatino", "STIXGeneral"))
                self.assertLessEqual(text.get_fontsize(), 10)
                box = text.get_window_extent(renderer)
                self.assertGreaterEqual(box.x0, 0)
                self.assertLessEqual(box.x1, fig.bbox.width)
                self.assertGreaterEqual(box.y0, 0)
                self.assertLessEqual(box.y1, fig.bbox.height)
        finally:
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
