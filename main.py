import streamlit as st
from database import init_db
from driver_portal import render_driver_portal
from admin_portal import render_admin_portal

# Initialize SQLite database and check migrations
init_db()

st.set_page_config(page_title="Green Tea Procurement System", layout="wide")

st.title("🌱 Green Tea Leaf Procurement System")

app_mode = st.sidebar.selectbox("Select System Portal", ["📱 Driver Mobile App Portal", "💻 Admin Dashboard Portal"])

if app_mode == "📱 Driver Mobile App Portal":
    render_driver_portal()
elif app_mode == "💻 Admin Dashboard Portal":
    render_admin_portal()