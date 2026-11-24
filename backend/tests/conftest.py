import os

os.environ["REALTIME_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
