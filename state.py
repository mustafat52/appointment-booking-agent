class BookingState:
    def __init__(self):
        # persistent info across flows
        self.last_event_id = None
        self.last_doctor_id = None
        self.doctor_id = None
        self.reset()

    def reset(self):
        self.intent = None

        # booking flow
        self.date = None
        self.time = None
        self.pending_time = None
        self.patient_name = None
        self.patient_phone = None

        # reschedule flow (Phase 4.4)
        self.reschedule_date = None
        self.reschedule_time = None

    def is_complete(self):
        return (
            self.intent == "BOOK"
            and self.date
            and self.time
            and self.patient_name
            and self.patient_phone
        )
