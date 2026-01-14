# doctor_config.py

DOCTORS = {
    "dr-mukesh": {
        "id": "dr-mukesh",
        "name": "Dr Mukesh",
        "calendar_id": "6ae583b423add448601b7a0ec297739a82149b673723287d9aa76350636da6db@group.calendar.google.com",

        "working_days": [0, 1, 2, 3, 4],  # Mon–Fri
        "working_hours": {
            "start": "10:00",
            "end": "18:00",
        },
        "slot_duration_minutes": 30,
        "buffer_minutes": 10,
    },

    
    "dr-anita": {
        "id": "dr-anita",
        "name": "Dr Anita",
        "calendar_id": "96fc1577018a3e683f497057375d6ab0bacbadc36ea80c6bbd8b794e83e43edc@group.calendar.google.com",
        "working_days": [1, 2, 3, 4, 5],
        "working_hours": {
            "start": "09:00",
            "end": "17:00",
        },
        "slot_duration_minutes": 20,
        "buffer_minutes": 5,
    },
}

# Backward compatibility
DEFAULT_DOCTOR_ID = "dr-mukesh"

# For Phase 2 compatibility (temporary)
DOCTOR_CONFIG = DOCTORS[DEFAULT_DOCTOR_ID]
