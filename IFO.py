import streamlit as st
import requests
import pandas as pd
import os
from dotenv import load_dotenv
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import io

# Load .env file
load_dotenv()

# Metabase credentials
METABASE_URL = os.getenv("METABASE_URL")
METABASE_USERNAME = os.getenv("METABASE_USERNAME")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD")

# Function to authenticate with Metabase
def get_metabase_session():
    login_url = f"{METABASE_URL}/api/session"
    credentials = {"username": METABASE_USERNAME, "password": METABASE_PASSWORD}
    
    try:
        response = requests.post(login_url, json=credentials)
        response.raise_for_status()
        return response.json().get("id")
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Authentication Failed! Error: {e}")
        return None

# Function to fetch data from Metabase query
def fetch_metabase_data(query_id):
    session_token = get_metabase_session()
    if not session_token:
        return None

    query_url = f"{METABASE_URL}/api/card/{query_id}/query/json"
    headers = {"X-Metabase-Session": session_token}

    try:
        response = requests.post(query_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            st.warning(f"⚠️ Query {query_id} returned no data.")
            return None
        return pd.DataFrame(data)  # Convert to DataFrame
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error fetching data for Query {query_id}: {e}")
        return None

# Function to convert DataFrame to image using matplotlib
def dataframe_to_image(df):
    # Create a figure and axis
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.axis('off')  # Hide axes

    # Create a table and add it to the axis
    table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        loc='center',
        cellLoc='center'
    )

    # Style the table
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.2)

    # Save the figure to a BytesIO buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buf.seek(0)
    return buf

# Streamlit UI
st.title("📊 Metabase Order Analysis")
st.sidebar.header("🔍 Filter Data")

# Select Date to Filter Orders
selected_date = st.sidebar.date_input("Select Date", pd.Timestamp.today())

# Delivery Hub Filter
delivery_hubs = [
    "Hebbal [ BH Micro warehouse ]",
    "Banashankari [ BH Micro warehouse ]",
    "Koramangala NGV [ BH Micro warehouse ]",
    "Mahadevapura [ BH Micro warehouse ]",
    "Chandra Layout [ BH Micro warehouse ]",
    "Kudlu [ BH Micro warehouse ]"
]
selected_hub = st.sidebar.selectbox("Select Delivery Hub", delivery_hubs)

# Metabase Query ID
query_id = 2904  # Replace with actual query ID

# Fetch Data
df = fetch_metabase_data(query_id)

if df is not None:
    # Convert date columns to datetime
    df['Delivered on'] = pd.to_datetime(df['Delivered on'])
    df['Latest Out-For-Delivery on'] = pd.to_datetime(df['Latest Out-For-Delivery on'])
    df['Last Delivery Unable-To'] = pd.to_datetime(df['Last Delivery Unable-To'])
    df['Returned Datetime on'] = pd.to_datetime(df['Returned Datetime on'])

    # Check if 'Status' column exists
    status_column = 'Status'  # Default column name
    if status_column not in df.columns:
        st.error(f"❌ Column '{status_column}' not found in DataFrame. Available columns: {df.columns.tolist()}")
        st.stop()  # Stop execution if the column is missing

    # Filter data based on selected date and hub
    filtered_df = df[
        (df['Delivered on'].dt.date == selected_date) &  # Filter by delivered date
        (df['Delivery Hub'] == selected_hub)  # Filter by selected hub
    ]

    # Filter for 'Out-For-Delivery' status and matching date
    out_on_road_df = df[
        (df[status_column] == 'Out-For-Delivery') &  # Filter by status
        (df['Latest Out-For-Delivery on'].dt.date == selected_date) &  # Filter by date
        (df['Delivery Hub'] == selected_hub)  # Filter by selected hub
    ]

    # Group 'Out-For-Delivery' data by Driver Vehicle
    out_on_road_grouped = out_on_road_df.groupby('Driver Vehicle').size().reset_index(name='Out_on_road')

    # Group filtered data by Driver Vehicle and Vehicle Model
    grouped_df = filtered_df.groupby(['Driver Vehicle', 'Vehicle Model', 'Delivery Hub']).agg(
        Delivered=('Delivered on', lambda x: x[
            (filtered_df.loc[x.index, status_column] == 'Delivered') &
            (filtered_df.loc[x.index, 'Delivered on'].dt.date == selected_date)
        ].count()),
        Unable_to_delivery=('Last Delivery Unable-To', 'count'),
        Returned=('Returned Datetime on', 'count')
    ).reset_index()

    # Merge 'Out_on_road' counts into the grouped DataFrame
    grouped_df = grouped_df.merge(out_on_road_grouped, on='Driver Vehicle', how='left')

    # Fill NaN values in 'Out_on_road' with 0
    grouped_df['Out_on_road'] = grouped_df['Out_on_road'].fillna(0).astype(int)

    # Ensure that the columns contain only integer values
    grouped_df['Delivered'] = grouped_df['Delivered'].astype(int)
    grouped_df['Unable_to_delivery'] = grouped_df['Unable_to_delivery'].astype(int)
    grouped_df['Returned'] = grouped_df['Returned'].astype(int)

    # Calculate Total Order Count and Delivered %
    grouped_df['Total order count'] = (
    grouped_df['Delivered'] + 
    grouped_df['Unable_to_delivery'] + 
    grouped_df['Returned'] + 
    grouped_df['Out_on_road']
)
grouped_df['Delivered %'] = (
    grouped_df['Delivered'] / grouped_df['Total order count'] * 100
)  # Multiply by 100 to get percentage
grouped_df['Delivered %'] = grouped_df['Delivered %'].fillna(0).astype(int).astype(str) + '%'

# Select and reorder columns
final_df = grouped_df[[
    'Driver Vehicle', 'Vehicle Model', 'Delivered', 'Unable_to_delivery', 
    'Returned', 'Out_on_road', 'Total order count', 'Delivered %'
]]

# Rename columns for display
final_df = final_df.rename(columns={
    'Driver Vehicle': 'Delivery Associate Name',
    'Vehicle Model': 'Vehicle Model',
    'Unable_to_delivery': 'Unable to delivery',
    'Out_on_road': 'Out on road'
})

# Add Grand Total row
grand_total = final_df.sum(numeric_only=True)
grand_total['Delivery Associate Name'] = 'Grand Total'
grand_total['Vehicle Model'] = ''

if grand_total['Total order count'] > 0:
    grand_total['Delivered %'] = (
        str(int((grand_total['Delivered'] / grand_total['Total order count']) * 100)) + '%'
    )
else:
    grand_total['Delivered %'] = '0%'

# Convert to integer, then to string, and add '%'
final_df = pd.concat([final_df, grand_total.to_frame().T], ignore_index=True)


# Display the final table
st.write("### Driver-wise Summary")
st.dataframe(final_df)

# Convert DataFrame to PNG
img_buffer = dataframe_to_image(final_df)

# PNG Download Button
st.download_button(
    label="📷 Download Table as PNG",
    data=img_buffer,
    file_name="Driver-wise Summary.png",
    mime="image/png"
)



# Hub Wise Summary Table
# Hub Wise Summary Table
# Hub Wise Summary Table
st.write("### Hub Wise Summary")

# Function to calculate Number of Vehicle for each hub
def calculate_number_of_vehicle(df, selected_date):
    # Filter rows where 'Latest Out-For-Delivery on' matches the selected date
    filtered_df = df[df['Latest Out-For-Delivery on'].dt.date == selected_date]
    
    # Group by Driver Vehicle and Delivery Hub, and count the number of deliveries per hub for each driver
    driver_hub_counts = filtered_df.groupby(['Driver Vehicle', 'Delivery Hub'])['Delivered on'].count().reset_index()
    driver_hub_counts.columns = ['Driver Vehicle', 'Delivery Hub', 'Delivery_Count']
    
    # Determine the primary hub for each driver (hub with the maximum deliveries)
    primary_hub = driver_hub_counts.loc[
        driver_hub_counts.groupby('Driver Vehicle')['Delivery_Count'].idxmax()
    ]
    
    # Count the number of unique drivers per hub based on their primary hub
    number_of_vehicle = primary_hub.groupby('Delivery Hub')['Driver Vehicle'].nunique().reset_index()
    number_of_vehicle.columns = ['Delivery Hub', 'Number_of_vehicle']
    
    return number_of_vehicle

# Calculate Number of Vehicle for each hub
number_of_vehicle_df = calculate_number_of_vehicle(df, selected_date)

# Group data by Delivery Hub
hub_wise_df = df.groupby('Delivery Hub').agg(
    Total_order_count=('Status', 'size'),  # Total orders based on Status
    Delivered=('Delivered on', lambda x: x[
        (df.loc[x.index, status_column] == 'Delivered') &
        (df.loc[x.index, 'Delivered on'].dt.date == selected_date)
    ].count()),
    Unable_to_delivery=('Last Delivery Unable-To', lambda x: x[
        (df.loc[x.index, 'Last Delivery Unable-To'].dt.date == selected_date)
    ].count()),
    Returned=('Returned Datetime on', lambda x: x[
        (df.loc[x.index, 'Returned Datetime on'].dt.date == selected_date)
    ].count()),
    Out_on_road=('Latest Out-For-Delivery on', lambda x: x[
        (df.loc[x.index, status_column] == 'Out-For-Delivery') &
        (df.loc[x.index, 'Latest Out-For-Delivery on'].dt.date == selected_date)
    ].count())
).reset_index()

# Merge the Number of Vehicle data into the hub_wise_df
hub_wise_df = hub_wise_df.merge(number_of_vehicle_df, on='Delivery Hub', how='left')

# Fill NaN values in 'Number_of_vehicle' with 0 (if any hub has no vehicles)
hub_wise_df['Number_of_vehicle'] = hub_wise_df['Number_of_vehicle'].fillna(0).astype(int)

# Calculate Total Order Count (sum of Delivered, Unable_to_delivery, Returned, Out_on_road)
hub_wise_df['Total_order_count'] = (
    hub_wise_df['Delivered'] + 
    hub_wise_df['Unable_to_delivery'] + 
    hub_wise_df['Returned'] + 
    hub_wise_df['Out_on_road']
)

# Calculate Attempt % and Delivered %
hub_wise_df['Attempt %'] = (
    (hub_wise_df['Delivered'] + hub_wise_df['Unable_to_delivery'] + hub_wise_df['Returned']) /
    hub_wise_df['Total_order_count']
).fillna(0).apply(lambda x: f"{int(x * 100)}%")

hub_wise_df['Delivered %'] = (
    hub_wise_df['Delivered'] / hub_wise_df['Total_order_count']
).fillna(0).apply(lambda x: f"{int(x * 100)}%")

# Add Backlogs column (blank for now)
hub_wise_df['Backlogs'] = ''

# Rename columns for display
hub_wise_df = hub_wise_df.rename(columns={
    'Delivery Hub': 'Hub Name',
    'Number_of_vehicle': 'Number of Vehicle',
    'Unable_to_delivery': 'Unable to Delivery',
    'Out_on_road': 'Out on Road'
})

# Reorder columns
hub_wise_df = hub_wise_df[[
    'Hub Name', 'Number of Vehicle', 'Total_order_count', 'Delivered', 
    'Unable to Delivery', 'Returned', 'Out on Road', 'Attempt %', 'Delivered %', 'Backlogs'
]]

# Add Grand Total row
grand_total_hub = hub_wise_df.sum(numeric_only=True)
grand_total_hub['Hub Name'] = 'Grand Total'
grand_total_hub['Attempt %'] = f"{int((grand_total_hub['Delivered'] + grand_total_hub['Unable to Delivery'] + grand_total_hub['Returned']) / grand_total_hub['Total_order_count'] * 100)}%"
grand_total_hub['Delivered %'] = f"{int(grand_total_hub['Delivered'] / grand_total_hub['Total_order_count'] * 100)}%"
grand_total_hub['Backlogs'] = ''

# Append Grand Total row to the DataFrame
hub_wise_df = pd.concat([hub_wise_df, grand_total_hub.to_frame().T], ignore_index=True)

# Display the Hub Wise Summary table
st.dataframe(hub_wise_df)

# Convert DataFrame to PNG
hub_img_buffer = dataframe_to_image(hub_wise_df)

# PNG Download Button
st.download_button(
    label="📷 Download Hub Wise Summary as PNG",
    data=hub_img_buffer,
    file_name="Hub_Wise_Summary.png",
    mime="image/png"
)

# Vehicle Utilization Table
st.write("### Vehicle Utilization")

# Function to calculate Count of Bikes and Autos for each hub
def calculate_vehicle_counts(df, selected_date):
    # Filter rows where 'Latest Out-For-Delivery on' matches the selected date
    filtered_df = df[df['Latest Out-For-Delivery on'].dt.date == selected_date]
    
    # Group by Driver Vehicle and Delivery Hub, and count the number of deliveries per hub for each driver
    driver_hub_counts = (
        filtered_df.groupby(['Driver Vehicle', 'Delivery Hub', 'Vehicle Model'])['Delivered on']
        .count()
        .reset_index()
    )
    driver_hub_counts.columns = ['Driver Vehicle', 'Delivery Hub', 'Vehicle Model', 'Delivery_Count']
    
    # Determine the primary hub for each driver (hub with the maximum deliveries)
    # If there's a tie, select the first hub alphabetically
    primary_hub = driver_hub_counts.loc[
        driver_hub_counts.groupby('Driver Vehicle')['Delivery_Count'].idxmax()
    ]
    
    # Count the number of unique drivers per hub based on their primary hub, split by Vehicle Model
    bikes_count = (
        primary_hub[primary_hub['Vehicle Model'] == 'Bike']
        .groupby('Delivery Hub')['Driver Vehicle']
        .nunique()
        .reset_index()
    )
    bikes_count.columns = ['Delivery Hub', 'Count_of_Bikes']
    
    autos_count = (
        primary_hub[primary_hub['Vehicle Model'] == 'Auto Rickshaw']
        .groupby('Delivery Hub')['Driver Vehicle']
        .nunique()
        .reset_index()
    )
    autos_count.columns = ['Delivery Hub', 'Count_of_Autos']
    
    # Merge Bike and Auto counts
    vehicle_counts = bikes_count.merge(autos_count, on='Delivery Hub', how='outer')
    
    # Fill NaN values with 0 (if any hub has no bikes or autos)
    vehicle_counts['Count_of_Bikes'] = vehicle_counts['Count_of_Bikes'].fillna(0).astype(int)
    vehicle_counts['Count_of_Autos'] = vehicle_counts['Count_of_Autos'].fillna(0).astype(int)
    
    return vehicle_counts


# Calculate Count of Bikes and Autos for each hub
vehicle_counts_df = calculate_vehicle_counts(df, selected_date)

# Group data by Delivery Hub
# Group data by Delivery Hub
# Group data by Delivery Hub
vehicle_utilization_df = df.groupby('Delivery Hub').agg(
    Total_count=('Driver Vehicle', 'nunique')  # Total unique vehicles (Bikes + Autos)
).reset_index()

# Merge the Vehicle Counts data into the vehicle_utilization_df
vehicle_utilization_df = vehicle_utilization_df.merge(vehicle_counts_df, on='Delivery Hub', how='left')

# Calculate Total Count (Bikes + Autos)
vehicle_utilization_df['Total_count'] = (
    vehicle_utilization_df['Count_of_Bikes'] + vehicle_utilization_df['Count_of_Autos']
)

# Calculate Ratio-Bikes and Ratio-Auto Rickshaw
vehicle_utilization_df['Ratio-Bikes'] = (
    vehicle_utilization_df['Count_of_Bikes'] / vehicle_utilization_df['Total_count']
).fillna(0).apply(lambda x: f"{round(x * 100, 2)}%")

vehicle_utilization_df['Ratio-Auto Rickshaw'] = (
    vehicle_utilization_df['Count_of_Autos'] / vehicle_utilization_df['Total_count']
).fillna(0).apply(lambda x: f"{round(x * 100, 2)}%")

# Rename 'Delivery Hub' to 'Hub Name' in vehicle_utilization_df BEFORE merging
vehicle_utilization_df = vehicle_utilization_df.rename(columns={'Delivery Hub': 'Hub Name'})

# Calculate Avg Productivity / Driver
# Fetch Delivered column from Hub Wise Summary table
vehicle_utilization_df = vehicle_utilization_df.merge(
    hub_wise_df[['Hub Name', 'Delivered']],  # Use 'Hub Name' instead of 'Delivery Hub'
    on='Hub Name',  # Merge on 'Hub Name'
    how='left'
)

# Calculate Avg Productivity / Driver
vehicle_utilization_df['Avg Productivity / Driver'] = (
    vehicle_utilization_df['Delivered'] / vehicle_utilization_df['Total_count']
).fillna(0).apply(lambda x: round(x, 2))

# Drop the temporary 'Delivered' column used for calculation
vehicle_utilization_df = vehicle_utilization_df.drop(columns=['Delivered'])

# Rename columns for display
vehicle_utilization_df = vehicle_utilization_df.rename(columns={
    'Count_of_Bikes': 'Count of Bikes',
    'Count_of_Autos': 'Count of Autos'
})

# Reorder columns
vehicle_utilization_df = vehicle_utilization_df[[
    'Hub Name', 'Count of Bikes', 'Count of Autos', 'Total_count', 
    'Ratio-Bikes', 'Ratio-Auto Rickshaw', 'Avg Productivity / Driver'
]]

# Display the Vehicle Utilization table
st.dataframe(vehicle_utilization_df)

# Convert DataFrame to PNG
vehicle_img_buffer = dataframe_to_image(vehicle_utilization_df)

# PNG Download Button
st.download_button(
    label="📷 Download Vehicle Utilization as PNG",
    data=vehicle_img_buffer,
    file_name="Vehicle_Utilization.png",
    mime="image/png"
)