import sqlite3

import streamlit as st

from services import create_expenses_table, seed_expenses_table
from views import render_create, render_delete, render_read, render_update

CHAR_LIMIT = 140
DATABASE_URI = "expenses.db"
# DATABASE_URI = ":memory:"


def main() -> None:
    """Main Streamlit App Entry"""
    connection = get_connection(DATABASE_URI)
    init_db(connection)

    st.header("Roommate Expense Tracker")
    st.subheader("Enter your spending to track who owes what to whom!")
    render_sidebar(connection)


def render_sidebar(connection: sqlite3.Connection) -> None:
    """Provides Selectbox Drop Down for which view to render"""
    views = {
        "Main Expense Feed": render_read,  # Read first for display default
        "Create an Expense": render_create,
        "Update an Expense": render_update,
        "Delete an Expense": render_delete,
    }
    choice = st.sidebar.radio("Go To Page:", views.keys())
    render_func = views.get(choice)
    render_func(connection)


@st.cache(hash_funcs={sqlite3.Connection: id}, suppress_st_warning=True)
def get_connection(connection_string: str = ":memory:") -> sqlite3.Connection:
    """Make a connection object to sqlite3 with key-value Rows as outputs
    Threading in Streamlit / Python with sqlite:
    - https://discuss.streamlit.io/t/prediction-analysis-and-creating-a-database/3504/2
    - https://stackoverflow.com/questions/48218065/programmingerror-sqlite-objects-created-in-a-thread-can-only-be-used-in-that-sa
    """
    st.error("Get Connection")
    connection = sqlite3.connect(connection_string, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


@st.cache(hash_funcs={sqlite3.Connection: id}, suppress_st_warning=True)
def init_db(connection: sqlite3.Connection) -> None:
    """Create table and seed data as needed for initialization"""
    st.warning("Init DB")
    create_expenses_table(connection)
    seed_expenses_table(connection)


if __name__ == "__main__":
    main()
