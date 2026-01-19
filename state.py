# state.py

class BookingState:
    def __init__(self):
        self.intent = None

        self.date = None
        self.time = None
        self.patient_name = None
        self.patient_phone = None

        self.doctor_id = None

        self.last_event_id = None
        self.last_doctor_id = None

        self.reschedule_date = None
        self.reschedule_time = None

        self.awaiting_confirmation = False
        self.awaiting_clarification = False
        
        self.expecting = None  # date | time | name | phone | confirm

        self.confirmed = False

    def reset(self):
        print("🔄 [State] Resetting state")

        self.intent = None
        self.date = None
        self.time = None
        self.patient_name = None
        self.patient_phone = None
        self.reschedule_date = None
        self.reschedule_time = None
        self.awaiting_confirmation = False
        self.awaiting_clarification = False
        self.confirmed = False
