"""The revised primary figure must preserve all observations and readable spacing."""
import unittest

import matplotlib.pyplot as plt
import numpy as np

import build_review_figure as builder


class FigureTest(unittest.TestCase):
    def setUp(self):
        self.runs, _, _ = builder.load_runs()
        self.fig, _ = builder.draw(self.runs)

    def tearDown(self):
        plt.close(self.fig)

    def test_values_and_equal_run_means(self):
        self.assertEqual(len(self.fig.axes), 4)
        for ax, key in zip(self.fig.axes, builder.METRICS):
            self.assertEqual(len(ax.collections), 12)
            group = 0
            for rate in builder.RATES:
                for method in builder.METHODS:
                    rows = sorted((row for row in self.runs if (row["method"], row["rate"]) == (method, rate)),
                                  key=lambda row: row["run"])
                    values = [row[key] for row in rows]
                    np.testing.assert_array_equal(ax.collections[group * 2].get_offsets()[:, 1], values)
                    self.assertAlmostEqual(ax.collections[group * 2 + 1].get_offsets()[0, 1], sum(values) / 4)
                    group += 1

    def test_style_and_spacing(self):
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()
        self.assertFalse(self.fig.legends)
        self.assertFalse(self.fig.texts)
        for ax in self.fig.axes:
            self.assertFalse(ax.lines)
            self.assertFalse(ax.patches)
            for text in ax.texts + ax.get_xticklabels() + ax.get_yticklabels() + [ax._left_title]:
                self.assertEqual(text.get_fontweight(), "normal")
                self.assertLessEqual(text.get_fontsize(), 9.5)
                self.assertIn(text.get_fontfamily()[0], ("Palatino", "STIXGeneral"))
        for upper, lower in zip(self.fig.axes, self.fig.axes[1:]):
            lowest_tick = min(text.get_window_extent(renderer).y0 for text in upper.get_xticklabels())
            title_top = lower._left_title.get_window_extent(renderer).y1
            self.assertGreater(lowest_tick - title_top, 5)


if __name__ == "__main__":
    unittest.main()
