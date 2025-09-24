import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# ---------- CONFIG ----------
st.set_page_config(page_title="Fever Follow-up Tool", layout="wide")

# ---------- THEME COLORS ----------
PRIMARY_COLOR = "#1E1E1E"  # Dark Black for main headings
ACCENT_COLOR = "#FF4081"   # Pink accent
BACKGROUND_COLOR = "#FFFFFF"  # White background for main app
ALERT_COLOR = "#FF1744"  # Red for alerts
TEXT_COLOR = "#000000"  # Black text
BUTTON_COLOR = "#2979FF"  # Blue buttons
BUTTON_HOVER_COLOR = "#00E5FF"  # Cyan hover for buttons
LOGIN_BG_COLOR = "#FFFFFF"  # White background for login page

# ---------- DATABASE ----------
conn = sqlite3.connect("fever_followup.db", check_same_thread=False)
c = conn.cursor()

# Create tables
c.execute('''CREATE TABLE IF NOT EXISTS hospitals (
                hospital_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS patients (
                patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                age INTEGER,
                gender TEXT,
                created_at TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                temp REAL,
                symptoms TEXT,
                notes TEXT,
                created_at TEXT)''')
conn.commit()

# Default hospital
c.execute("SELECT * FROM hospitals WHERE username=?", ("hospital1",))
if not c.fetchone():
    c.execute("INSERT INTO hospitals (username, password) VALUES (?, ?)", ("hospital1", "pass123"))
    conn.commit()

# ---------- AUTH ----------
def login(username, password):
    c.execute("SELECT * FROM hospitals WHERE username=? AND password=?", (username, password))
    return c.fetchone() is not None

def register(username, password):
    try:
        c.execute("INSERT INTO hospitals (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

# ---------- SIDEBAR ----------
def sidebar_menu():
    st.sidebar.markdown(f"""
        <h2 style='color:{PRIMARY_COLOR};'>Navigation</h2>
    """, unsafe_allow_html=True)
    return st.sidebar.radio("Go to:", ["Patient Registration", "Symptom Check-in", "Patient Timeline", "Overview", "Alert Dashboard", "Logout"])

# ---------- RISK SCORING ----------
def calculate_risk(temp, symptoms):
    risk = 'Low'
    if temp >= 102 or any(cs in symptoms.lower() for cs in ['difficulty breathing','chest pain','persistent high fever']):
        risk = 'High'
    elif temp >= 100.4:
        risk = 'Medium'
    return risk

# ---------- PAGES ----------
def patient_registration():
    st.markdown(f"<h2 style='color:{ACCENT_COLOR};'>Patient Registration</h2>", unsafe_allow_html=True)
    with st.form('register_form'):
        name = st.text_input("Patient Name")
        age = st.number_input("Age", 0, 120, 25)
        gender = st.selectbox("Gender", ['Prefer not to say', 'Female', 'Male', 'Other'])
        submitted = st.form_submit_button("Submit")
        if submitted:
            c.execute('INSERT INTO patients (name, age, gender, created_at) VALUES (?, ?, ?, ?)',
                      (name, age, gender, datetime.utcnow().isoformat()))
            conn.commit()
            st.success(f"Patient '{name}' registered successfully")


def symptom_checkin():
    st.markdown(f"<h2 style='color:{ACCENT_COLOR};'>Symptom Check-in</h2>", unsafe_allow_html=True)
    patients_df = pd.read_sql_query('SELECT * FROM patients ORDER BY patient_id DESC', conn)
    if patients_df.empty:
        st.warning('No patients registered yet.')
        return
    patient_id = st.selectbox('Select Patient', options=patients_df['patient_id'].tolist(),
                              format_func=lambda x: f"{patients_df[patients_df['patient_id']==x]['name'].values[0]}")

    with st.form('checkin_form'):
        temp_f = st.number_input("Temperature (°F)", 90.0, 110.0, 98.6)
        symptoms = st.text_area("Symptoms (comma separated)")
        notes = st.text_area("Additional notes (optional)")
        submitted = st.form_submit_button("Submit")

        if submitted:
            c.execute('INSERT INTO entries (patient_id, temp, symptoms, notes, created_at) VALUES (?, ?, ?, ?, ?)',
                      (patient_id, temp_f, symptoms, notes, datetime.utcnow().isoformat()))
            conn.commit()

            risk = calculate_risk(temp_f, symptoms)
            st.success(f"Symptom check-in submitted. Risk Level: {risk}")

            if risk == 'High':
                st.error(f"⚠ HIGH RISK ALERT for patient {patients_df[patients_df['patient_id']==patient_id]['name'].values[0]}")


def patient_timeline():
    st.markdown(f"<h2 style='color:{ACCENT_COLOR};'>Patient Timeline</h2>", unsafe_allow_html=True)
    patients_df = pd.read_sql_query('SELECT * FROM patients ORDER BY patient_id DESC', conn)
    if patients_df.empty:
        st.warning('No patients registered yet.')
        return
    patient_id = st.selectbox('Select Patient', options=patients_df['patient_id'].tolist(),
                              format_func=lambda x: f"{patients_df[patients_df['patient_id']==x]['name'].values[0]}")
    entries_df = pd.read_sql_query('SELECT * FROM entries WHERE patient_id=? ORDER BY created_at', conn, params=(patient_id,))
    if entries_df.empty:
        st.info('No check-ins yet for this patient.')
    else:
        def highlight_row(row):
            return ['color: red;' if row['temp'] >= 100.4 else '' for _ in row]
        st.dataframe(entries_df[['created_at','temp','symptoms','notes']].style.apply(highlight_row, axis=1))
        st.line_chart(entries_df.set_index('created_at')['temp'])
        csv = entries_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="Download Patient Report CSV", data=csv, file_name=f"patient_{patient_id}_report.csv", mime='text/csv')


def alert_dashboard():
    st.markdown(f"<h2 style='color:{ALERT_COLOR};'>Alert Dashboard</h2>", unsafe_allow_html=True)
    entries_df = pd.read_sql_query('SELECT e.*, p.name FROM entries e JOIN patients p ON e.patient_id=p.patient_id ORDER BY e.created_at DESC', conn)
    if entries_df.empty:
        st.info('No check-ins submitted yet.')
        return
    entries_df['risk'] = entries_df.apply(lambda x: calculate_risk(x['temp'], x['symptoms']), axis=1)
    high_risk_df = entries_df[entries_df['risk']=='High']
    if high_risk_df.empty:
        st.success('No high-risk patients currently.')
    else:
        st.dataframe(high_risk_df[['created_at','name','temp','symptoms','risk']])


def overview():
    st.markdown(f"<h2 style='color:{ACCENT_COLOR};'>Overview</h2>", unsafe_allow_html=True)
    patients_df = pd.read_sql_query('SELECT * FROM patients', conn)
    st.metric("Patients Registered", len(patients_df))
    entries_df = pd.read_sql_query('SELECT * FROM entries', conn)
    st.metric("Check-ins Submitted", len(entries_df))

# ---------- LOGIN / REGISTER ----------
def login_page():
    st.markdown(f"""
        <div style='background-color:{LOGIN_BG_COLOR}; padding:20px; border-radius:10px;'>
            <h2 style='color:{PRIMARY_COLOR}; text-align:center;'>SymptoTrack</h2>
        </div>
    """, unsafe_allow_html=True)

    option = st.radio("Select Action", ['Login', 'Register'], index=0, horizontal=True)

    if option == 'Login':
        username_input = st.text_input("Username", key="login_username")
        password_input = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key='login_btn'):
            if login(username_input, password_input):
                st.session_state['login_success'] = True
            else:
                st.error("Invalid credentials")

    else:  # Register
        new_username = st.text_input("New Username", key="reg_username")
        new_password = st.text_input("New Password", type="password", key="reg_password")
        if st.button("Register", key='reg_btn'):
            if register(new_username, new_password):
                st.success(f"Hospital '{new_username}' registered successfully. You can now login.")
            else:
                st.error("Username already exists. Choose a different one.")
        if st.button("Go Back", key='go_back_btn'):
            st.session_state['login_success'] = False
            st.stop()

# ---------- MAIN ----------
def main():
    if 'login_success' not in st.session_state:
        st.session_state['login_success'] = False

    if not st.session_state['login_success']:
        login_page()
    else:
        choice = sidebar_menu()
        if choice == "Patient Registration":
            patient_registration()
        elif choice == "Symptom Check-in":
            symptom_checkin()
        elif choice == "Patient Timeline":
            patient_timeline()
        elif choice == "Overview":
            overview()
        elif choice == "Alert Dashboard":
            alert_dashboard()
        elif choice == "Logout":
            st.session_state['login_success'] = False
            st.stop()

if __name__ == "__main__":
    main()