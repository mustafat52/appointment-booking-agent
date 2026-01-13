class BookingState:
    def __init__(self):
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
        self.intent = None
        self.date = None
        self.time = None
        self.confirmed = False
