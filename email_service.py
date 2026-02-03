import os
import resend 

resend.api_key = os.environ["RESEND_API_KEY"]


FROM_EMAIL = os.getenv("FROM_EMAIL", "MedSchedule AI <onboarding@resend.dev>")


def send_daily_appointments_email(clinic_email, doctor_name, appointments):
    if not appointments:
        return

    rows = ""
    for a in appointments:
        rows += f"""
        <tr>
            <td>{a.patient.name}</td>
            <td>{a.patient.phone}</td>
            <td>{a.appointment_time}</td>
        </tr>
        """

    html = f"""
    <h2>Today's Appointments – {doctor_name}</h2>
    <table border="1" cellpadding="8" cellspacing="0">
        <tr>
            <th>Patient</th>
            <th>Time</th>
        </tr>
        {rows}
    </table>
    """

    resend.emails.send({
        "from": FROM_EMAIL,-+

        "to": [clinic_email],
        "subject": f"Today's Appointments – {doctor_name}",
        "html": html,
    })
