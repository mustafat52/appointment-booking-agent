class BookingState:
    def __init__(self):
        # Phase 3 – doctor awareness
        self.doctor_id = None
        self.doctor_name = None

        # Existing booking fields
        self.intent = None
        self.date = None
        self.time = None
        self.confirmed = False

    def is_complete(self):
        return (
            self.intent == "BOOK"
            and self.date is not None
            and self.time is not None
        )

    def reset(self):
        # DO NOT reset doctor info (important)
        self.intent = None
        self.date = None
        self.time = None
        self.confirmed = False
