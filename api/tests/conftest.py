import os

# Unit tests run without generated secrets.
os.environ.setdefault("NIYAN_ALLOW_INSECURE_DEFAULTS", "1")
