class BookingState:
    def __init__(self):
        # Phase 1: booking basics
        self.intent = None
        self.date = None
        self.time = None

        # Phase 2: patient info
        self.patient_name = None
        self.patient_phone = None
        self.pending_time = None

        # Phase 3: multi-doctor
        self.doctor_id = None

        # Phase 4.2: last appointment memory
        self.last_event_id = None
        self.last_doctor_id = None

        self.confirmed = False

    def is_complete(self):
        return (
            self.intent == "BOOK"
            and self.date is not None
            and self.time is not None
            and self.patient_name is not None
            and self.patient_phone is not None
        )

    def reset(self):
        # Reset only conversation-specific fields
        self.intent = None
        self.date = None
        self.time = None

        self.patient_name = None
        self.patient_phone = None
        self.pending_time = None

        # ❗ DO NOT reset:
        # - doctor_id (comes from URL)
        # - last_event_id / last_doctor_id (needed for cancel/reschedule)

        self.confirmed = False
