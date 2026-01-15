class BookingState:
    def __init__(self):
        # Phase 1
        self.intent = None
        self.date = None
        self.time = None

        # Phase 2 / 3
        self.patient_name = None
        self.patient_phone = None
        self.pending_time = None

        # Phase 3 (multi-doctor)
        self.doctor_id = None

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

        # DO NOT reset doctor_id here
        # It comes from the URL (/book/{doctor_id})
        self.confirmed = False
