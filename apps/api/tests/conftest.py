import os

os.environ.setdefault("AAR_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AAR_ENVIRONMENT", "development")
