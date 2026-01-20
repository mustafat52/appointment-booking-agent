# state.py

class BookingState:
    def __init__(self):
        # Intent
        self.intent = None  # BOOK | CANCEL | RESCHEDULE

        # Current booking (in-progress)
        self.date = None
        self.time = None
        self.patient_name = None
        self.patient_phone = None

        # Doctor context
        self.doctor_id = None

        # Last confirmed appointment (PHASE-4 SNAPSHOT)
        self.last_event_id = None
        self.last_doctor_id = None
        self.last_date = None
        self.last_time = None
        self.last_patient_name = None
        self.last_patient_phone = None

        # Reschedule flow
        self.reschedule_date = None
        self.reschedule_time = None

        # Conversation helpers
        self.expecting = None

    def reset(self):
        """
        Reset ONLY the active conversation.
        DO NOT clear last appointment snapshot.
        """
        self.intent = None
        self.date = None
        self.time = None
        self.patient_name = None
        self.patient_phone = None
        self.reschedule_date = None
        self.reschedule_time = None
        self.expecting = None
