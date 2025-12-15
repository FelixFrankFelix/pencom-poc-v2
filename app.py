import streamlit as st

from src.utils import handle_email_function, extract_emails


# Page configuration
st.set_page_config(page_title="PENCOM-CM", page_icon="📧", layout="centered")

# Custom CSS for better styling
st.markdown("""
    <style>
    .stTextInput > div > div > input {
        font-size: 14px;
    }
    .stTextArea > div > div > textarea {
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

# App title with logo
col1, col2 = st.columns([1, 4])
with col1:
    st.image("images/logo.png", width=120)
with col2:
    st.title("PENCOM-CM")
st.markdown("---")

# Sender email input
sender_email = st.text_input(
    "From",
    placeholder="your.email@example.com",
    help="Enter your email address"
)

# Recipients input (can contain multiple emails)
# recipients_input = st.text_area(
#     "To",
#     placeholder="recipient1@example.com, recipient2@example.com",
#     height=80,
#     help="Enter recipient email addresses (comma-separated or space-separated)"
# )

# Subject input
subject = st.text_input(
    "Subject",
    placeholder="Enter email subject",
)

# Email body
email_body = st.text_area(
    "Message",
    placeholder="Compose your email here...",
    height=250
)

# Send button
col1, col2, col3 = st.columns([3, 1, 1])

with col2:
    if st.button("✉️ Send", type="primary", use_container_width=True):
        # Validation
        if not sender_email:
            st.error("Please enter sender email address")
        elif not subject:
            st.error("Please enter email subject")
        elif not email_body:
            st.error("Please enter email body")
        else:
            # Validate sender email
            sender_valid = extract_emails(sender_email)
            if not sender_valid:
                st.error("Invalid sender email address")
            else:
                # Run the send function
                with st.spinner("Sending email..."):
                    handle_email_function(sender_email, subject, email_body)
                st.success("Email sent successfully!")

with col3:
    if st.button("🗑️ Clear", use_container_width=True):
        st.rerun()

# Footer
st.markdown("---")
st.caption("QUCOON 2025")