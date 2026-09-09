import unittest
from vocab_persistence import _row_value


class PersistenceShapeTests(unittest.TestCase):
    def test_row_value_supports_dict_and_tuple_rows(self):
        self.assertEqual(_row_value({'id': 7}, 'id', 0), 7)
        self.assertEqual(_row_value((7,), 'id', 0), 7)


if __name__ == '__main__':
    unittest.main()
