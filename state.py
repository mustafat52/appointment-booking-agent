# state.py

class BookingState:
    def __init__(self):
        # Core intent
        self.intent = None  # BOOK | CANCEL | RESCHEDULE

        # Booking details
        self.date = None
        self.time = None
        self.patient_name = None
        self.patient_phone = None

        # Doctor context
        self.doctor_id = None

        # Temporary helpers
        self.pending_time = None

        # Last appointment tracking (Phase 4)
        self.last_event_id = None
        self.last_doctor_id = None

        # Reschedule flow
        self.reschedule_date = None
        self.reschedule_time = None

        # Compatibility with main.py
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
        self.intent = None
        self.date = None
        self.time = None
        self.patient_name = None
        self.patient_phone = None
        self.pending_time = None
        self.reschedule_date = None
        self.reschedule_time = None
        self.confirmed = False
