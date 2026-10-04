"""Synthetic/exact arithmetic checks; no annotation generation or edits."""
from math import comb
import unittest
from build_semantic_paper import finite_upper


class FinitePopulationTests(unittest.TestCase):
    def test_complete_sample_zero_errors(self):
        self.assertEqual(finite_upper(10, 10)['upper_K'], 0)

    def test_actual_design_boundary(self):
        r = finite_upper(2032, 300)
        self.assertEqual(r['upper_K'], 18)
        self.assertGreaterEqual(r['p_zero_at_upper'], .05)
        self.assertLess(r['p_zero_at_next'], .05)

    def test_small_design_matches_enumeration(self):
        from itertools import combinations
        N, n = 8, 3
        r = finite_upper(N, n, .20)
        for K in (r['upper_K'], r['upper_K'] + 1):
            observed_zero = sum(not set(s).intersection(range(K)) for s in combinations(range(N), n))
            p = observed_zero / comb(N, n)
            self.assertEqual(p >= .20, K == r['upper_K'])


if __name__ == '__main__':
    unittest.main()
