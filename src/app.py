import streamlit as st
import pandas as pd
import os
import requests
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import leafmap.foliumap as leafmap
from streamlit_folium import st_folium
from dotenv import load_dotenv
from streamlit_geolocation import streamlit_geolocation

from data_access.pg_connect import (
    connect_postgres,
    is_pooler_supabase_environ,
    postgres_connection_cache_key,
)
from data_access.streamlit_env import (
    hydrate_secrets_into_environ,
    is_supabase_direct_db_url,
    looks_like_ipv6_routing_failure,
    streamlit_warn_supabase_direct_url,
)

# Load environment variables from .env file
load_dotenv()
hydrate_secrets_into_environ()

st.set_page_config(
    page_title="Fuel Up Plan",
    page_icon="⛽",
    layout="wide", # Changed to wide to allow side-by-side layout
    initial_sidebar_state="expanded",
)

st.title("⛽ Fuel Up Plan")
st.markdown("Plan your next fuel stop easily.")


@st.cache_resource(ttl=300)
def _cached_psycopg2_conn(cache_key: str):
    """Cache key includes URL or discrete host/user/password so secret updates apply."""
    if not cache_key:
        return None
    try:
        return connect_postgres()
    except ValueError as e:
        st.error(str(e))
        return None
    except Exception as e:
        st.error(f"Database connection error: {e}")
        err = str(e).lower()
        if "password authentication failed" in err and is_pooler_supabase_environ():
            st.info(
                "Use the **Database password** from Supabase → Project Settings → Database "
                "(not your Supabase login). You can set **separate** Streamlit Secrets "
                "(`POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, …) so the password "
                "does not need URL-encoding—see `.env.example`."
            )
        db_url = os.environ.get("POSTGRES_DB_URL") or ""
        if is_supabase_direct_db_url(db_url) and looks_like_ipv6_routing_failure(e):
            streamlit_warn_supabase_direct_url()
        return None


def get_db_connection():
    hydrate_secrets_into_environ()
    return _cached_psycopg2_conn(postgres_connection_cache_key())

def fetch_hybrid_prices(fuel_type):
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    query = """
        SELECT station_name, address, latitude, longitude, fuel_type, price, is_available, data_source
        FROM mart_hybrid_current_prices
        WHERE fuel_type = %s AND latitude IS NOT NULL AND longitude IS NOT NULL
    """
    try:
        df = pd.read_sql(query, conn, params=(fuel_type,))
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

def get_coordinates(location_name):
    import ssl
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    
    geolocator = Nominatim(user_agent="vic_fuel_app", ssl_context=ctx)
    try:
        location = geolocator.geocode(f"{location_name.strip()}, Victoria, Australia")
        if location:
            return (location.latitude, location.longitude), location.address
    except Exception as e:
        pass
    return None, None

def get_address_from_coords(lat, lon):
    import ssl
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    geolocator = Nominatim(user_agent="vic_fuel_app", ssl_context=ctx)
    try:
        location = geolocator.reverse((lat, lon))
        if location:
            return location.address
    except:
        pass
    return "Your Location"

def fetch_7_day_price_history():
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    query = """
        SELECT DATE(updated_at) as date, fuel_type, AVG(price) as avg_price
        FROM raw_prices
        WHERE updated_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(updated_at), fuel_type
        ORDER BY date ASC
    """
    try:
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        return pd.DataFrame()

def fetch_current_day_averages():
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    query = """
        SELECT fuel_type, AVG(price) as avg_price
        FROM mart_hybrid_current_prices
        GROUP BY fuel_type
        ORDER BY avg_price ASC
    """
    try:
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        return pd.DataFrame()

# Fallback function to automatically find location based on IP address immediately on load
@st.cache_data(ttl=3600)
def get_ip_location():
    try:
        res = requests.get('http://ip-api.com/json/', timeout=3).json()
        if res and res.get('status') == 'success':
            return (res.get('lat'), res.get('lon'))
    except:
        pass
    return (-37.8136, 144.9631) # Default to Melbourne CBD if IP check fails

fuel_types = {
    "Unleaded 91": "U91",
    "Premium 95": "P95",
    "Premium 98": "P98",
    "Diesel": "DSL",
    "Premium Diesel": "PDSL",
    "E10": "E10",
    "E85": "E85",
    "LPG": "LPG"
}

# --- SPLIT LAYOUT ---
# Left side for the Map (1.4 ratio), Right side for the Plan (1.0 ratio)
map_col, plan_col = st.columns([1.4, 1.0], gap="large")

# We create an empty placeholder for the map in the left column.
# This allows us to calculate the results in the right column first,
# and then draw the single map in the left column afterwards!
map_placeholder = map_col.empty()

with plan_col:
    st.subheader("1. What do you need?")
    selected_fuel_label = st.selectbox("I want petrol:", list(fuel_types.keys()))
    selected_fuel = fuel_types[selected_fuel_label]

    st.subheader("2. Where are you?")
    
    # Check if we should auto-locate based on IP first
    default_coords = get_ip_location()
    
    loc_col1, loc_col2 = st.columns([1, 1])
    with loc_col1:
        st.markdown("**My location:**")
        # streamlit_geolocation watches GPS continuously → reruns every update → screen flashing.
        # Only mount the component when the user opts in.
        use_live_gps = st.checkbox(
            "Use device GPS",
            value=False,
            help="Uses browser location. Can refresh often; use manual address to avoid.",
        )
        loc = streamlit_geolocation() if use_live_gps else None
    with loc_col2:
        st.markdown("**Or type manually:**")
        current_location = st.text_input("Place or postcode (e.g. '3121'):")

    st.subheader("3. Choose your plan")
    tab1, tab2, tab3 = st.tabs(["Cheapest Price", "Closest Station", "Best Value (Price + Distance)"])

    coords = None
    location_display = ""
    user_address = "You are here"

    # Determine coords based on user input, exact GPS, or IP auto-detect
    if current_location:
        coords, resolved_addr = get_coordinates(current_location)
        if coords:
            location_display = current_location
            user_address = resolved_addr
    elif loc and loc.get("latitude") is not None and loc.get("longitude") is not None:
        coords = (loc["latitude"], loc["longitude"])
        location_display = "Your Exact GPS Location"
        user_address = get_address_from_coords(coords[0], coords[1])
    else:
        coords = default_coords
        location_display = "Your Approximate Location (Auto)"
        user_address = get_address_from_coords(coords[0], coords[1])

    # Fetch and filter data
    df_nearby = pd.DataFrame()
    cheapest_df = pd.DataFrame()
    closest_df = pd.DataFrame()
    best_value_df = pd.DataFrame()

    if coords:
        # st.success(f"📍 Location found: **{user_address}**")  # Removed per request
        df = fetch_hybrid_prices(selected_fuel)
        
        if not df.empty:
            def calc_distance(row):
                station_coords = (row['latitude'], row['longitude'])
                return geodesic(coords, station_coords).km
                
            df['distance_km'] = df.apply(calc_distance, axis=1)
            df_nearby = df[df['distance_km'] <= 10].copy()

            if not df_nearby.empty:
                cheapest_df = df_nearby.sort_values(by=['price', 'distance_km']).head(5)
                closest_df = df_nearby.sort_values(by=['distance_km']).head(5)
                
                # Calculate "Best Value" score:
                # Every extra KM driven costs fuel. Assuming average car burns 8L/100km, 
                # that's 0.08L per km. If fuel is ~200 cents/L, 1km = ~16 cents of burned fuel.
                # So the "True Cost" per litre is roughly the raw price + (16 cents * (distance / 50L tank))
                # For simplicity, we just add a penalty factor to the price based on distance.
                # Penalty = distance_km * 0.5 (adds 0.5 cents to the "effective price" for every km driven)
                df_nearby['value_score'] = df_nearby['price'] + (df_nearby['distance_km'] * 0.5)
                best_value_df = df_nearby.sort_values(by=['value_score']).head(5)
                
                def render_station_card(row):
                    # Attempt to find a logo based on the brand/name
                    name_lower = str(row['station_name']).lower()
                    if 'ampol' in name_lower or 'eg ampol' in name_lower:
                        logo = "🔴" # Ampol red
                    elif 'bp' in name_lower:
                        logo = "🟢" # BP green
                    elif 'shell' in name_lower:
                        logo = "🟡" # Shell yellow
                    elif 'coles' in name_lower or 'shell coles' in name_lower:
                        logo = "🔴" # Coles Express red
                    elif 'united' in name_lower:
                        logo = "🔵" # United blue
                    elif '7-eleven' in name_lower:
                        logo = "🟠" # 7-Eleven orange/green
                    elif 'liberty' in name_lower:
                        logo = "🔷" # Liberty blue
                    else:
                        logo = "⛽" # Default
                        
                    st.markdown(f"""
                        <div style="padding: 10px; border-radius: 5px; border: 1px solid #e0e0e0; margin-bottom: 10px;">
                            <h4 style="margin-top: 0; margin-bottom: 5px;">{logo} {row['station_name']}</h4>
                            <div style="display: flex; align-items: baseline; gap: 10px;">
                                <h3 style="color: #2e7d32; margin: 0;">{row['price']} ¢/L</h3>
                                <span style="color: #666; font-size: 0.9em;">📍 {row['distance_km']:.1f} km</span>
                            </div>
                            <div style="color: #888; font-size: 0.8em; margin-top: 5px;">{row['address']}</div>
                        </div>
                    """, unsafe_allow_html=True)
                
                with tab1:
                    st.markdown("**Top 5 Cheapest Options (Within 10km)**")
                    for index, row in cheapest_df.iterrows():
                        render_station_card(row)
                        
                with tab2:
                    st.markdown("**Top 5 Closest Stations**")
                    for index, row in closest_df.iterrows():
                        render_station_card(row)
                        
                with tab3:
                    st.markdown("**Top 5 Best Value (Price + Driving Distance factor)**")
                    st.info("💡 Takes into account that driving further burns more fuel. Stations further away get a slight price penalty.")
                    for index, row in best_value_df.iterrows():
                        render_station_card(row)
            else:
                st.warning("No stations found nearby with that fuel type.")
        else:
            st.warning("No fuel data available. Please check the database.")

# --- RENDER SINGLE MAP ON LEFT SIDE ---
with map_placeholder.container():
    if coords:
        # Combine the cheapest, closest, and best value stations into one list so they all appear on the single map
        display_df = pd.concat([cheapest_df, closest_df, best_value_df]).drop_duplicates(subset=['station_name'])
        
        from folium import plugins
        m = leafmap.Map(center=coords, zoom=13, draw_control=False, measure_control=False)
        
        # Add Search Control
        plugins.Geocoder().add_to(m)
        
        # Add User Location Pin
        m.add_marker(location=coords, tooltip="Your Location", popup=f"<b>Your Location:</b><br>{user_address}", icon=leafmap.folium.Icon(color="red", icon="info-sign"))
        
        # Add Gas Station Pins
        for idx, row in display_df.iterrows():
            station_coords = (row['latitude'], row['longitude'])
            popup_html = f"<b>{row['station_name']}</b><br>Price: {row['price']} ¢/L<br>Dist: {row['distance_km']:.1f} km<br>{row['address']}"
            m.add_marker(location=station_coords, popup=popup_html, tooltip=row['station_name'], icon=leafmap.folium.Icon(color="green", icon="gas-pump", prefix="fa"))
        
        # returned_objects=[] avoids a rerun on every pan/zoom/click (reduces flashing).
        st_folium(m, height=500, width=None, returned_objects=[], key="fuel_plan_map")
        
        st.markdown("---")
        st.subheader("📊 State-wide Fuel Trends")
        
        trend_col1, trend_col2 = st.columns([1, 1.5])
        
        with trend_col1:
            st.markdown("**Today's Average Prices**")
            avg_df = fetch_current_day_averages()
            if not avg_df.empty:
                avg_df['avg_price'] = avg_df['avg_price'].round(1)
                st.dataframe(
                    avg_df.rename(columns={'fuel_type': 'Fuel Type', 'avg_price': 'Average ¢/L'}),
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("No average data available.")
                
        with trend_col2:
            st.markdown("**7-Day Price History**")
            hist_df = fetch_7_day_price_history()
            if not hist_df.empty:
                chart_data = hist_df.pivot(index='date', columns='fuel_type', values='avg_price')
                st.line_chart(chart_data)
            else:
                st.info("Historical data is building up. Check back tomorrow!")
    else:
        st.info("Map will appear here once location is determined.")

