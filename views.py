
from datetime import date, datetime, timedelta, timezone
import sqlite3

from models import Expense, BaseExpense
from services import ExpenseService

import pandas as pd
import streamlit as st
import streamlit_pydantic as sp
import plotly.graph_objects as go
import plotly.express as px

def display_timestamp(timestamp: int) -> datetime:
    """Return python datetime from utc timestamp"""
    return datetime.fromtimestamp(timestamp, timezone.utc)


def utc_timestamp() -> int:
    """Return current utc timestamp rounded to nearest int"""
    return int(datetime.utcnow().timestamp())


def render_expense(expense: Expense) -> None:
    """Show a expense with streamlit display functions"""
    st.subheader(f"By {expense.purchased_by} at {expense.purchased_date}")
    st.caption(f"Expense #{expense.rowid}")
    st.write(f"{expense.price_in_cents / 100 :.2f}")


def do_create(connection: sqlite3.Connection, expense: BaseExpense) -> None:
    """Streamlit callback for creating a expense and showing confirmation"""
    st.warning("Creating your Expense")
    ExpenseService.create_expense(connection, expense)
    st.success(
        f"Successfully Created your Expense! Check the Read Expense Feed page to see it"
    )


def render_create(connection: sqlite3.Connection) -> None:
    """Show the form for creating a new Expense"""
    data = sp.pydantic_form(key="create_form", model=BaseExpense, clear_on_submit=True)
    if data:
        do_create(connection, data)

def prep_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    return df.divide(100).reset_index().melt("purchased_date")

@st.cache()
def get_data(connection, start_date: date, end_date: date, selections: list[str]) -> pd.DataFrame:
    expense_rows = ExpenseService.list_all_expenses(connection, start_date, end_date, selections)
    expenses = [Expense(**row) for row in expense_rows]
    return pd.DataFrame([x.dict() for x in expenses])

def render_read(connection: sqlite3.Connection) -> None:
    """Show all of the expenses in the database in a feed"""
    st.success("Reading Expense Feed")

    render_create(connection)
    purchasers = ExpenseService.list_all_purchasers(connection)
    selections = st.multiselect("Show Spending For:", [*purchasers, 'All'], default=purchasers)
    start_date = st.date_input("Start Date", value=date.today() - timedelta(days=30*6))
    end_date = st.date_input("End Date", value=date.today())
    with st.expander("Show Raw Data"), st.echo():
        raw_df = get_data(connection, start_date, end_date, selections)
        st.write(raw_df)

    with st.expander("Data Cleaning"), st.echo():
        # Take needed columns
        df = raw_df[["purchased_date", "purchased_by", "price_in_cents"]]
        # Pivot data into columns of each purchased_by person, summing any dupes for a given day
        pivot_df = df.pivot_table(
            index="purchased_date", columns="purchased_by", aggfunc="sum", fill_value=0
        )
        # Ignore multiindex that doesn't give much in this case
        pivot_df.columns = pivot_df.columns.droplevel(0)
        # Avoid doing summation with floats and money
        if 'All' in selections:
            pivot_df["All"] = pivot_df.sum(axis=1)

        # Fill in date gaps
        min_date = pivot_df.index.min()
        max_date = pivot_df.index.max()
        all_dates = pd.date_range(min_date, max_date, freq="D", name="purchased_date")
        pivot_df = pivot_df.reindex(all_dates, fill_value=0)

        # All spending days
        spend_df = prep_df_for_display(pivot_df)

        # Cumulative spend over time for each person
        cum_df = pivot_df.cumsum()
        # Percent of contributions over time (ignore All)
        cum_pct_df = cum_df[cum_df.columns.drop('All', errors='ignore')].divide(cum_df.sum(axis=1), axis=0).multiply(100)

        cum_df = prep_df_for_display(cum_df)
        cum_pct_df = cum_pct_df.reset_index().melt("purchased_date")

        # Sum of each spender
        totals = pivot_df.sum()
        totals.index.name = "purchased_by"
        totals.name = "value"
        totals = totals.div(100).reset_index()

        # 7 Day cumulative spending
        rolling_df = pivot_df.rolling(7, min_periods=1).sum()
        rolling_df = prep_df_for_display(rolling_df)

        # 30 Day daily maxes
        maxes_df = pivot_df.rolling(30, min_periods=1).max()
        maxes_df = prep_df_for_display(maxes_df)

    st.header("Total Spending Per Person")
    spending_per_person = px.bar(totals, x='value', y='purchased_by', color='purchased_by', labels={'purchased_by': 'Purchased By', 'value':'Total Dollars Spent'})
    st.plotly_chart(spending_per_person, use_container_width=True)

    st.header("Percentage of Spending")
    spending_pct = px.area(cum_pct_df, x='purchased_date', y='value', color='purchased_by')
    st.plotly_chart(spending_pct, use_container_width=True)

    spending_per_day = px.bar(spend_df, x='purchased_date', y='value',
              color='purchased_by',
             labels={'value':'Dollars spent per day'}, height=500)
    st.plotly_chart(spending_per_day)

    st.header("Cumulative Spending Per Person")

    if selections:
        st.header("Cumulative Spending To Date")
        multi_line = lambda x: px.line(x, x="purchased_date", y="value", color='purchased_by')
        fig = multi_line(cum_df)
        st.plotly_chart(fig, use_container_width=True)

        rolling_chart = multi_line(rolling_df)
        st.header("Weekly Spending Per Person")
        st.plotly_chart(rolling_chart, use_container_width=True)

        maxes_chart = multi_line(maxes_df)
        st.header("Monthly Biggest Purchase Per Person")
        st.plotly_chart(maxes_chart, use_container_width=True)
    else:
        st.warning("Select at least one person to see the charts")

    expenses = ExpenseService.list_all_expenses(connection)
    st.header("Expense Feed")
    for expense in expenses:
        render_expense(Expense(**expense))


def do_update(connection: sqlite3.Connection, new_expense: Expense) -> None:
    """Streamlit callback for updating a expense and showing confirmation"""
    st.warning(f"Updating Expense #{new_expense.rowid}")
    ExpenseService.update_expense(connection, new_expense)
    st.success(
        f"Updated Expense #{new_expense.rowid}, go to the Read Expenses Feed to see it!"
    )


def render_update(connection: sqlite3.Connection) -> None:
    """Show the form for updating an existing Expense"""
    st.success("Reading Expenses")
    expense_rows = ExpenseService.list_all_expenses(connection)
    expense_map = {row["rowid"]: Expense(**row) for row in expense_rows}
    expense_id = st.selectbox(
        "Which Expense to Update?",
        expense_map.keys(),
        format_func=lambda x: f"{expense_map[x].rowid} - by {expense_map[x].username} on {display_timestamp(expense_map[x].created_timestamp)}",
    )
    expense_to_update = expense_map[expense_id]
    with st.form("update_form"):
        st.write("Update Purchase Info")
        price = st.number_input(
            "Price",
            value=expense_to_update.price,
            min_value=0,
            max_value=1_000,
            help="Enter the Price of the expense",
        )
        purchased_date = st.date_input(
            "Purchase Date",
            value=expense_to_update.purchased_date,
            help="Enter the Purchase Date",
        )

        st.caption(
            f"Expense #{expense_id} - by {expense_to_update.price} on {display_timestamp(expense_to_update.purchased_date)}"
        )

        submitted = st.form_submit_button(
            "Submit",
            help="This will change the body of the expense, the username, or both. It also updates the updated at time.",
        )
        if submitted:
            new_expense = Expense(
                purchased_date,
                price,
                expense_to_update.rowid,
            )
            do_update(connection, new_expense)


def do_delete(connection: sqlite3.Connection, expense_to_delete: Expense) -> None:
    """Streamlit callback for deleting a expense and showing confirmation"""
    st.warning(f"Deleting Expense #{expense_to_delete.rowid}")
    ExpenseService.delete_expense(connection, expense_to_delete)
    st.success(f"Deleted Expense #{expense_to_delete.rowid}")


def render_delete(connection: sqlite3.Connection) -> None:
    """Show the form for deleting an existing Expense"""
    st.success("Reading Expenses")
    expense_rows = ExpenseService.list_all_expenses(connection)
    expense_map = {row["rowid"]: Expense(**row) for row in expense_rows}
    expense_id = st.selectbox("Which Expense to Delete?", expense_map.keys())
    expense_to_delete = expense_map[expense_id]

    render_expense(expense_to_delete)

    st.button(
        "Delete Expense (This Can't Be Undone!)",
        help="I hope you know what you're getting into!",
        on_click=do_delete,
        args=(connection, expense_to_delete),
    )
