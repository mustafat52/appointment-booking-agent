
from datetime import time

DOCTOR_CONFIG = {
    "working_days": [0, 1, 2, 3, 4],  # Mon–Fri (0 = Monday)
    "working_hours": {
        "start": time(10, 0),  # 10:00
        "end": time(18, 0)     # 18:00
    },
    "slot_duration_minutes": 30,
    "buffer_minutes": 15
}
