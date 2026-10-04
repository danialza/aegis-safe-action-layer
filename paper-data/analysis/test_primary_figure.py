"""Verify a layout-only redraw preserves every displayed observation and mean."""
import json
import statistics
import unittest
from unittest.mock import patch

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np

import build_hardware_figures as builder


class PrimaryFigureTest(unittest.TestCase):
    def test_all_values_and_means_survive_layout_change(self):
        summary = json.loads((builder.HERE / 'hardware_summary.json').read_text())
        primary = [r for r in summary['all_included_records'] if r['campaign'] == builder.PRIMARY]
        self.assertEqual(len(primary), 24)
        with patch.object(Figure, 'savefig'), patch.object(plt, 'close'):
            builder.plot_primary(primary)
            fig = plt.gcf()
        try:
            self.assertEqual(len(fig.axes), 3)
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            boxes = [ax.get_position() for ax in fig.axes]
            self.assertAlmostEqual(boxes[0].y0 - boxes[1].y1, boxes[1].y0 - boxes[2].y1)
            self.assertLess((boxes[0].y0 - boxes[1].y1) * fig.get_figheight(), .5)
            for upper, lower in zip(fig.axes, fig.axes[1:]):
                lower_title = lower._left_title.get_window_extent(renderer)
                lowest_tick = min(t.get_window_extent(renderer).y0 for t in upper.get_xticklabels())
                self.assertGreater(lowest_tick - lower_title.y1, 5)
            metrics = ('min_command_estimated_edge_separation_mm', 'carry_to_delivery_s',
                       'moving_age_above_0p6_percent')
            for ax, metric in zip(fig.axes, metrics):
                self.assertEqual(len(ax.collections), 12)
                group = 0
                for rate in builder.RATES:
                    for method in builder.METHODS:
                        runs = sorted((r for r in primary if r['rate'] == rate and r['method'] == method),
                                      key=lambda r: r['run'])
                        values = [r[metric] for r in runs]
                        np.testing.assert_array_equal(ax.collections[group * 2].get_offsets()[:, 1], values)
                        self.assertEqual(ax.collections[group * 2 + 1].get_offsets()[0, 1], statistics.mean(values))
                        self.assertIn(f'{statistics.mean(values):.1f}', [t.get_text() for t in ax.texts])
                        self.assertEqual(ax.texts[group].get_position(), (0, 4))
                        group += 1
                for text in ax.texts + ax.get_xticklabels() + ax.get_yticklabels() + [ax.title, ax._left_title]:
                    self.assertEqual(text.get_fontweight(), 'normal')
                    self.assertLessEqual(text.get_fontsize(), 10)
                    self.assertIn(text.get_fontfamily()[0], ('Palatino', 'STIXGeneral'))
                self.assertLess(ax.get_ylim()[0], 0)
                self.assertEqual(len(ax.patches), 0)
                self.assertEqual(len(ax.lines), 0)
                self.assertFalse(any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()))
                self.assertNotIn('\n', ax._left_title.get_text())
                for points in ax.collections:
                    for color in list(points.get_edgecolors()) + list(points.get_facecolors()):
                        self.assertEqual(color[0], color[1])
                        self.assertEqual(color[1], color[2])
        finally:
            plt.close(fig)


if __name__ == '__main__':
    unittest.main()
