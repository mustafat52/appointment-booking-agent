from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func
from datetime import date, time, datetime

from db.database import SessionLocal
from db.models import Doctor, Patient, Appointment , DoctorCalendarCredential, DoctorAuth


# -------------------------
# Session helper
# -------------------------

def get_db_session() -> Session:
    return SessionLocal()


# -------------------------
# Doctor queries
# -------------------------

def get_doctor_by_slug(slug: str) -> Doctor | None:
    db = get_db_session()
    try:
        stmt = select(Doctor).where(
            Doctor.slug == slug,
            Doctor.is_active == True
        )
        return db.execute(stmt).scalars().first()
    finally:
        db.close()


def doctor_exists() -> bool:
    db = get_db_session()
    try:
        return db.execute(select(Doctor).limit(1)).first() is not None
    finally:
        db.close()


def create_doctor(
    *,
    name: str,
    email: str,
    clinic_email,
    whatsapp_number,
    slug : str,
    working_days: list[int],
    work_start_time: time,
    work_end_time: time,
    avg_consult_minutes: int,
    buffer_minutes: int,
) -> Doctor:
    db = get_db_session()
    try:
        doctor = Doctor(
            slug=slug,
            name=name,
            clinic_email=clinic_email,
            whatsapp_number=whatsapp_number,
            email=email,
            calendar_id="",
            working_days=",".join(map(str, working_days)),
            work_start_time=work_start_time,
            work_end_time=work_end_time,
            avg_consult_minutes=avg_consult_minutes,
            buffer_minutes=buffer_minutes,
            is_active=True,
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        return doctor
    finally:
        db.close()


# -------------------------
# Patient queries
# -------------------------

def get_or_create_patient(name: str, phone: str) -> Patient:
    db = get_db_session()
    try:
        patient = db.execute(
            select(Patient).where(Patient.phone == phone)
        ).scalars().first()

        if patient:
            patient.last_seen_at = func.now()
            db.commit()
            db.refresh(patient)
            return patient

        patient = Patient(name=name, phone=phone)
        db.add(patient)
        db.commit()
        db.refresh(patient)
        return patient
    finally:
        db.close()

def create_patient(
    db: Session,
    *,
    name: str,
    phone: str
) -> Patient:
    patient = Patient(
        name=name,
        phone=phone,
    )
    db.add(patient)
    db.flush()  # ensures patient.id is available
    return patient


# 🔹 NEW (Phase 6.5): fetch patient WITHOUT creating
def get_patients_by_phone(phone: str) -> list[Patient]:
    db = get_db_session()
    try:
        stmt = select(Patient).where(Patient.phone == phone)
        return db.execute(stmt).scalars().all()
    finally:
        db.close()



# -------------------------
# Appointment queries
# -------------------------

def create_appointment(
    db: Session,
    *,
    doctor_id,
    patient_id,
    appointment_date,
    appointment_time,
    status,
    calendar_event_id,
):
    appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        status=status,
        calendar_event_id=calendar_event_id,
    )
    db.add(appointment)
    db.flush()
    return appointment



def get_appointment_by_event_id(event_id: str) -> Appointment | None:
    db = get_db_session()
    try:
        stmt = select(Appointment).where(
            Appointment.calendar_event_id == event_id,
            Appointment.status == "BOOKED"
        )
        return db.execute(stmt).scalars().first()
    finally:
        db.close()


def cancel_appointment_db(appointment_id) -> None:
    db = get_db_session()
    try:
        appt = db.get(Appointment, appointment_id)
        if not appt:
            return
        appt.status = "CANCELLED"
        appt.updated_at = func.now()
        db.commit()
    finally:
        db.close()


def reschedule_appointment_db(
    *,
    appointment_id,
    new_date: date,
    new_time: time,
    new_calendar_event_id: str | None,
) -> Appointment:
    db = get_db_session()
    try:
        appt = db.get(Appointment, appointment_id)
        if not appt:
            raise RuntimeError("Appointment not found")

        appt.appointment_date = new_date
        appt.appointment_time = new_time
        if new_calendar_event_id is not None:
            appt.calendar_event_id = new_calendar_event_id

        appt.updated_at = func.now()

        db.commit()
        db.refresh(appt)
        return appt
    finally:
        db.close()


# 🔹 NEW (Phase 6.5): get all ACTIVE appointments for patient
def get_active_appointments_by_phone(
    *,
    phone,
    doctor_id,
) -> list[Appointment]:

    db = get_db_session()
    try:
        # 1️⃣ get all patients with this phone
        patients = db.execute(
            select(Patient).where(Patient.phone == phone)
        ).scalars().all()

        if not patients:
            return []

        patient_ids = [p.patient_id for p in patients]

        # 2️⃣ fetch appointments for all those IDs
        stmt = (
            select(Appointment)
            .where(
                Appointment.patient_id.in_(patient_ids),
                Appointment.doctor_id == doctor_id,
                Appointment.status == "BOOKED",
            )
            .order_by(Appointment.appointment_date, Appointment.appointment_time)
        )

        return db.execute(stmt).scalars().all()

    finally:
        db.close()



# 🔹 NEW (Phase 6.5): filter active appointments by date
def get_active_appointments_by_date(
    *,
    patient_id,
    doctor_id,
    appointment_date: date,
) -> list[Appointment]:
    db = get_db_session()
    try:
        stmt = (
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.doctor_id == doctor_id,
                Appointment.status == "BOOKED",
                Appointment.appointment_date == appointment_date,
            )
            .order_by(Appointment.appointment_time)
        )
        return db.execute(stmt).scalars().all()
    finally:
        db.close()


def get_doctor_by_email(email: str) -> Doctor | None:
    db = get_db_session()
    try:
        stmt = select(Doctor).where(
            Doctor.email == email,
            Doctor.is_active == True
        )
        return db.execute(stmt).scalars().first()
    finally:
        db.close()



def get_upcoming_appointments_for_doctor(
    doctor_id,
    limit: int = 50
):
    db = get_db_session()
    try:
        stmt = (
            select(Appointment)
            .options(joinedload(Appointment.patient))  
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.status != "CANCELLED",
                Appointment.appointment_date >= date.today()
            )
            .order_by(
                Appointment.appointment_date,
                Appointment.appointment_time
            )
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()
    finally:
        db.close()



def get_appointment_by_id(appointment_id):
    db = get_db_session()
    try:
        return db.get(Appointment, appointment_id)
    finally:
        db.close()



# --------------------------------------------------
# Phase 8 – Doctor calendar credentials (OAuth)
# --------------------------------------------------

def save_doctor_calendar_credentials(
    *,
    doctor_id,
    provider: str,
    calendar_id: str,
    access_token: str,
    refresh_token: str,
    expires_at,
):
    """
    Insert or update calendar credentials for a doctor.
    One doctor = one active calendar connection.
    """
    db = get_db_session()
    try:
        creds = db.execute(
            select(DoctorCalendarCredential).where(
                DoctorCalendarCredential.doctor_id == doctor_id
            )
        ).scalars().first()

        if creds:
            creds.provider = provider
            creds.calendar_id = calendar_id
            creds.access_token = access_token
            creds.refresh_token = refresh_token
            creds.expires_at = expires_at
            creds.updated_at = datetime.utcnow()
        else:
            creds = DoctorCalendarCredential(
                doctor_id=doctor_id,
                provider=provider,
                calendar_id=calendar_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
            db.add(creds)

        db.commit()
        db.refresh(creds)
        return creds
    finally:
        db.close()


def get_doctor_calendar_credentials(doctor_id):
    """
    Fetch calendar credentials for a doctor.
    Returns None if not connected.
    """
    db = get_db_session()
    try:
        return db.execute(
            select(DoctorCalendarCredential).where(
                DoctorCalendarCredential.doctor_id == doctor_id
            )
        ).scalars().first()
    finally:
        db.close()


def get_doctor_by_id(db, doctor_id):
    return db.get(Doctor, doctor_id)


from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import joinedload

def get_todays_appointments_for_doctor(doctor_id):
    db = get_db_session()
    try:
        return (
            db.query(Appointment)
            .options(joinedload(Appointment.patient))
            .filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == date.today(),
                Appointment.status == "BOOKED"
            )
            .order_by(Appointment.appointment_time)
            .all()
        )
    finally:
        db.close()


def get_doctor_auth_by_email(email: str):
    db = SessionLocal()
    try:
        return (
            db.query(DoctorAuth)
            .filter(DoctorAuth.email == email, DoctorAuth.is_active == True)
            .first()
        )
    finally:
        db.close()


def create_doctor_auth(doctor_id, email: str, password_hash: str):
    db = SessionLocal()
    try:
        auth = DoctorAuth(
            doctor_id=doctor_id,
            email=email,
            password_hash=password_hash
        )
        db.add(auth)
        db.commit()
        db.refresh(auth)
        return auth
    finally:
        db.close()


def update_doctor_last_login(auth_id):
    db = SessionLocal()
    try:
        auth = db.get(DoctorAuth, auth_id)
        if auth:
            auth.last_login_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def get_doctor_auth_by_doctor_id(doctor_id):
    db = SessionLocal()
    try:
        return (
            db.query(DoctorAuth)
            .filter(
                DoctorAuth.doctor_id == doctor_id,
                DoctorAuth.is_active == True
            )
            .first()
        )
    finally:
        db.close()


def get_doctor_by_whatsapp_number(db: Session, whatsapp_number: str):
    return (
        db.query(Doctor)
        .filter(
            Doctor.whatsapp_number == whatsapp_number,
            Doctor.is_active == True
        )
        .first()
    )
