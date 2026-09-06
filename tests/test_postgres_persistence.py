import os
import unittest
from importlib.util import find_spec
from unittest.mock import Mock, patch

from vocab_persistence import PostgresPersistence


class PostgresPersistenceTests(unittest.TestCase):
    @unittest.skipUnless(find_spec("psycopg"), "psycopg is installed in the runtime image")
    def test_connection_factory_uses_external_database_configuration(self):
        connection = Mock()
        with patch("psycopg.connect", return_value=connection) as connect:
            with patch.dict(
                os.environ,
                {
                    "VOCAB_DB_HOST": "db",
                    "VOCAB_DB_PORT": "5432",
                    "VOCAB_DB_NAME": "vocab",
                    "VOCAB_DB_USER": "vocab",
                    "VOCAB_DB_PASSWORD": "test-only",
                },
            ):
                persistence = PostgresPersistence.from_env()

        self.assertIs(persistence.connection, connection)
        self.assertEqual(connect.call_args.kwargs["host"], "db")
        self.assertEqual(connect.call_args.kwargs["dbname"], "vocab")

    def test_boundary_can_be_constructed_with_a_connection(self):
        connection = Mock()
        persistence = PostgresPersistence(connection)
        self.assertIs(persistence.connection, connection)


if __name__ == "__main__":
    unittest.main()
