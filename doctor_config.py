# doctor_config.py

DOCTORS = {
    "dr-mukesh": {
        "id": "dr-mukesh",
        "name": "Dr Mukesh",
        "calendar_id": "primary",  # existing calendar for now
        "working_days": [0, 1, 2, 3, 4],  # Mon–Fri
        "working_hours": {
            "start": "10:00",
            "end": "18:00",
        },
        "slot_duration_minutes": 30,
        "buffer_minutes": 10,
    },

    # Future doctors (examples – not active yet)
    # "dr-anita": {
    #     "id": "dr-anita",
    #     "name": "Dr Anita",
    #     "calendar_id": "anita_calendar_id",
    #     "working_days": [1, 2, 3, 4, 5],
    #     "working_hours": {
    #         "start": "09:00",
    #         "end": "17:00",
    #     },
    #     "slot_duration_minutes": 20,
    #     "buffer_minutes": 5,
    # },
}

# Backward compatibility
DEFAULT_DOCTOR_ID = "dr-mukesh"

# For Phase 2 compatibility (temporary)
DOCTOR_CONFIG = DOCTORS[DEFAULT_DOCTOR_ID]
