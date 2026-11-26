import os
import sys
import tempfile
from pathlib import Path

# Isolated, offline settings: must be set before the app (and its .env loading) is imported.
_tmp = tempfile.mkdtemp(prefix="hive_test_")
os.environ.update({
    "DB_PATH": str(Path(_tmp) / "test.db"),
    "ADMIN_KEY": "test-passkey",
    "NVIDIA_API_KEY": "",
    "MIXPANEL_TOKEN": "",
    "DEV_RESOLVE_PUBLIC_IP": "false",
    "ENABLE_RMET": "true",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
