import streamlit as st
import database as db
from jira_client import JiraClient

# Initialize database
db.init_db()

st.set_page_config(page_title="Incident Management", layout="wide")

# Tab display names mapping
TAB_DISPLAY_NAMES = {
    "impacted_region": "Impacted Region",
    "impact_type": "Impact Type",
    "audience": "Audience",
    "observation_method": "Observation Method",
    "root_cause": "Root Cause",
    "severity": "Severity",
    "application": "Application",
    "team": "Team",
    "year": "Year",
    "quarter": "Quarter",
}


def render_field_page(table_name: str, display_name: str):
    """Render a page for managing field values."""
    st.header(f"Manage {display_name}")

    # Add new value
    col1, col2 = st.columns([3, 1])
    with col1:
        new_value = st.text_input(
            f"New {display_name}",
            key=f"new_{table_name}",
            label_visibility="collapsed",
            placeholder=f"Enter new {display_name.lower()}...",
        )
    with col2:
        if st.button("Add", key=f"add_{table_name}", use_container_width=True):
            if new_value.strip():
                result = db.add_field_value(table_name, new_value.strip())
                if result:
                    st.success(f"Added '{new_value}'")
                    st.rerun()
                else:
                    st.error(f"'{new_value}' already exists")
            else:
                st.warning("Please enter a value")

    # Display existing values
    values = db.get_field_values(table_name)
    if values:
        st.write("**Existing values:**")
        for value_id, name in values:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"[{value_id}] {name}")
            with col2:
                if st.button("Delete", key=f"del_{table_name}_{value_id}"):
                    db.delete_field_value(table_name, value_id)
                    st.rerun()
    else:
        st.info(f"No {display_name.lower()} values yet. Add one above.")


def render_all_incidents():
    """Render all incidents in a formatted view."""
    st.subheader("All Incidents")
    incidents = db.get_incidents()
    if incidents:
        for incident in incidents:
            with st.expander(f"#{incident['id']} - {incident['jira_ticket']}: {incident['summary'][:50]}..."):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**JIRA Ticket:** {incident['jira_ticket']}")
                    st.write(f"**Summary:** {incident['summary']}")
                    st.write(f"**Downtime:** {incident['downtime_mins']} mins")
                    st.write(f"**Severity:** {incident['severity'] or 'N/A'}")
                    st.write(f"**Impact Type:** {incident['impact_type'] or 'N/A'}")
                with col2:
                    st.write(f"**Application:** {incident['application'] or 'N/A'}")
                    st.write(f"**Team:** {incident['team'] or 'N/A'}")
                    st.write(f"**Impacted Region:** {incident['impacted_region'] or 'N/A'}")
                    st.write(f"**Root Cause:** {incident['root_cause'] or 'N/A'}")
                    st.write(f"**Year:** {incident['year'] or 'N/A'}, **Quarter:** {incident['quarter'] or 'N/A'}")
    else:
        st.info("No incidents yet.")


def render_raw_data():
    """Render raw incidents data and Jira import."""
    st.subheader("Raw Data")

    # Jira Import Section
    with st.expander("Import from Jira", expanded=False):
        st.write("**Jira Server Configuration**")
        col1, col2 = st.columns(2)
        with col1:
            jira_url = st.text_input(
                "Jira URL",
                placeholder="https://jira.company.com",
                key="jira_url",
            )
            jira_username = st.text_input(
                "Username",
                key="jira_username",
            )
        with col2:
            jira_password = st.text_input(
                "Password / API Token",
                type="password",
                key="jira_password",
            )
            max_results = st.number_input(
                "Max Results",
                min_value=1,
                max_value=1000,
                value=100,
                key="jira_max_results",
            )

        jql_query = st.text_area(
            "JQL Query",
            placeholder='project = "INCIDENT" AND status = "Done" ORDER BY created DESC',
            key="jql_query",
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("Import from Jira", type="primary", use_container_width=True):
                if not all([jira_url, jira_username, jira_password, jql_query]):
                    st.error("Please fill in all Jira configuration fields")
                else:
                    try:
                        with st.spinner("Connecting to Jira..."):
                            client = JiraClient(jira_url, jira_username, jira_password)
                            if not client.test_connection():
                                st.error("Failed to connect to Jira. Check credentials.")
                            else:
                                with st.spinner("Fetching issues..."):
                                    issues = client.search_issues(jql_query, max_results)
                                    if issues:
                                        count = db.upsert_raw_jira_data(issues)
                                        st.success(f"Imported {count} issues from Jira")
                                        st.rerun()
                                    else:
                                        st.warning("No issues found matching the JQL query")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    # Display raw Jira data
    st.divider()
    st.write("**Imported Jira Data**")
    raw_data = db.get_raw_jira_data()
    if raw_data:
        # Remove raw_json from display
        display_data = [
            {k: v for k, v in row.items() if k != "raw_json"}
            for row in raw_data
        ]
        st.dataframe(display_data, use_container_width=True)
    else:
        st.info("No Jira data imported yet. Use the import section above.")

    # Display incidents data
    st.divider()
    st.write("**Incidents Data**")
    incidents = db.get_incidents()
    if incidents:
        st.dataframe(incidents, use_container_width=True)
    else:
        st.info("No incidents yet.")


def render_add_incident():
    """Render the add new incident form."""
    st.subheader("Add New Incident")

    # Get unimported Jira tickets for selection
    unimported_jira = db.get_unimported_jira_data()

    if not unimported_jira:
        st.info("No unimported Jira tickets available. Import tickets from Jira in the Raw Data tab.")
        return

    jira_options = {j["jira_ticket_id"]: j for j in unimported_jira}

    # Get all field options
    field_options = {}
    for table in db.FIELD_TABLES:
        values = db.get_field_values(table)
        field_options[table] = {name: id for id, name in values}

    with st.form("incident_form"):
        # Dropdown for Jira ticket selection
        selected_ticket = st.selectbox(
            "JIRA Ticket",
            options=list(jira_options.keys()),
            format_func=lambda x: f"{x} - {jira_options[x]['summary'][:60]}..." if jira_options[x]['summary'] else x,
            key="select_jira",
        )

        # Get selected Jira data
        jira_data = jira_options[selected_ticket]
        default_summary = jira_data["summary"] or ""

        summary = st.text_area("Summary", value=default_summary)
        downtime_mins = st.number_input("Downtime (mins)", min_value=0, value=0)

        # Checkbox to mark as imported
        mark_imported = st.checkbox(
            "Mark as imported",
            value=True,
            help="Mark the Jira ticket as imported after creating the incident",
        )

        st.divider()

        # Dropdowns for each field (single select for now - will update based on user input)
        selected_values = {}
        cols = st.columns(2)
        for i, table in enumerate(db.FIELD_TABLES):
            display_name = TAB_DISPLAY_NAMES[table]
            options = list(field_options[table].keys())
            with cols[i % 2]:
                selected = st.selectbox(
                    display_name,
                    options=[""] + options,
                    key=f"incident_{table}",
                )
                if selected:
                    selected_values[table] = field_options[table][selected]
                else:
                    selected_values[table] = None

        submitted = st.form_submit_button("Create Incident", use_container_width=True)
        if submitted:
            if selected_ticket and summary.strip():
                incident_id = db.add_incident(
                    selected_ticket,
                    summary.strip(),
                    downtime_mins,
                    selected_values,
                )
                # Mark Jira ticket as imported if checkbox is checked
                if mark_imported:
                    db.set_jira_imported(selected_ticket, True)
                st.success(f"Created incident #{incident_id}")
                st.rerun()
            else:
                st.error("Summary is required")


def render_incidents_page():
    """Render the incidents page with horizontal tabs."""
    st.header("Incidents")

    tab1, tab2, tab3 = st.tabs(["All Incidents", "Raw Data", "Add New Incident"])

    with tab1:
        render_all_incidents()

    with tab2:
        render_raw_data()

    with tab3:
        render_add_incident()


# Initialize session state for navigation
if "selected_page" not in st.session_state:
    st.session_state.selected_page = "Incidents"

# Compact sidebar styling
st.markdown("""
<style>
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(> .nav-item) {
        padding: 0;
        margin: 0;
    }
    .nav-item {
        padding: 0.3rem 0.5rem;
        margin: 0.1rem 0;
        border-radius: 0.3rem;
        cursor: pointer;
    }
    .nav-selected {
        background-color: #262730;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar navigation
with st.sidebar:
    st.title("Incident Management")
    st.divider()

    # Navigation options
    nav_options = ["Incidents"] + [TAB_DISPLAY_NAMES[t] for t in db.FIELD_TABLES]

    for option in nav_options:
        is_selected = st.session_state.selected_page == option
        prefix = "▸ " if is_selected else "  "
        css_class = "nav-item nav-selected" if is_selected else "nav-item"
        if st.button(f"{prefix}{option}", key=f"nav_{option}", type="tertiary"):
            st.session_state.selected_page = option
            st.rerun()

# Main content area
if st.session_state.selected_page == "Incidents":
    render_incidents_page()
else:
    # Find the corresponding table name
    table_name = None
    for table, display in TAB_DISPLAY_NAMES.items():
        if display == st.session_state.selected_page:
            table_name = table
            break
    if table_name:
        render_field_page(table_name, st.session_state.selected_page)
