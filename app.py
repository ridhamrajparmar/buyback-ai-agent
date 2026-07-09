# pyrefly: ignore [missing-import]
import streamlit as st
import os
import agent_extractor
import importlib
importlib.reload(agent_extractor)
from agent_extractor import BuybackAgentExtractor

st.set_page_config(page_title="Dual-PDF Buyback Analyst", layout="wide")
st.title("Stock Buyback Analytics Agent")
st.write("Upload a Buyback Announcement to extract key metrics. Optionally, upload the Annual Report (SHP) to automatically extract retail distribution for a precise Acceptance Ratio calculation.")

# Initialize Extractor
def get_extractor():
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")
    return BuybackAgentExtractor(schema_path=schema_path)

extractor = get_extractor()

# Initialize session state variables
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None
if "shp_data" not in st.session_state:
    st.session_state.shp_data = None
if "raw_text_announcement" not in st.session_state:
    st.session_state.raw_text_announcement = None
if "raw_text_shp" not in st.session_state:
    st.session_state.raw_text_shp = None

# UI Layout
col_main, col_sidebar = st.columns([2, 1])

with col_sidebar:
    st.header("Assumptions & Inputs")
    company_name = st.text_input("Company Name (For Live Search Fallback)", value="TCS")
    cmp_price = st.number_input("Current Market Price (CMP) *Required", min_value=0.0, value=None, step=1.0)
    expected_post_price = st.number_input("Expected Price Post Buyback", min_value=0.0, value=0.0, step=1.0)

with col_main:
    announcement_file = st.file_uploader("1. Upload Buyback Announcement (Required)", type=["pdf"])
    shp_file = st.file_uploader("2. Upload Annual Report / SHP (Optional)", type=["pdf"])
    
    if announcement_file is not None:
        if cmp_price is None or cmp_price <= 0.0:
            st.warning("⚠️ Please enter a valid Current Market Price (CMP) in the sidebar before extracting.")
        elif st.button("Extract & Analyze", key="btn_analyze"):
            with st.spinner("Analyzing documents..."):
                # Process Announcement
                temp_ann_path = f"temp_{announcement_file.name}"
                with open(temp_ann_path, "wb") as f:
                    f.write(announcement_file.getbuffer())
                    
                data, raw_text_ann = extractor.parse_announcement(temp_ann_path)
                
                # BRUTE-FORCE SANITIZER
                if isinstance(data, dict) and isinstance(data.get("buyback_size"), dict):
                    data = data["buyback_size"]
                elif isinstance(data, tuple) and isinstance(data[0], dict):
                    data = data[0]
                    
                st.session_state.extracted_data = data
                st.session_state.raw_text_announcement = raw_text_ann
                
                if os.path.exists(temp_ann_path):
                    os.remove(temp_ann_path)
                    
                # Process SHP (Optional)
                if shp_file is not None:
                    temp_shp_path = f"temp_{shp_file.name}"
                    with open(temp_shp_path, "wb") as f:
                        f.write(shp_file.getbuffer())
                        
                    shp_data, raw_text_shp = extractor.get_shareholding_percentage(temp_shp_path, company_name, cmp_price)
                    st.session_state.shp_data = shp_data
                    st.session_state.raw_text_shp = raw_text_shp
                    
                    if os.path.exists(temp_shp_path):
                        os.remove(temp_shp_path)
                else:
                    # No SHP PDF uploaded — trigger online fallback
                    print(f"No SHP PDF uploaded. Triggering online search for '{company_name}'...")
                    fallback_data = extractor.fetch_shareholding_online(company_name)
                    st.session_state.shp_data = fallback_data
                    st.session_state.raw_text_shp = None

# Display Results
if st.session_state.extracted_data:
    st.write("---")
    st.subheader("Extraction & Decision Results")
    extracted_data = st.session_state.extracted_data
    shp_data = st.session_state.shp_data
    
    if "error" in extracted_data:
        st.error(f"Announcement Error: {extracted_data['error']}")
    else:
        # Determine Holding Percentage
        holding_pct = 2.0
        source_label = "Assumed Baseline (2%)"
        is_approximate = False
        
        if shp_data:
            holding_pct = shp_data.get("retail_holding_percentage", 2.0)
            is_approximate = shp_data.get("is_approximate", True)
            data_source = shp_data.get("source", "PDF")
            
            if "Online" in data_source:
                source_label = f"Fetched via Live Search"
                st.info(f"🌐 Live Search: {holding_pct:.2f}% (Source: {data_source})")
            elif "Distribution" in data_source:
                source_label = "Calculated from Distribution Table + CMP"
                st.warning(f"📊 Calculated Retail Holding: {holding_pct:.2f}% (Source: {data_source})")
            else:
                source_label = "Extracted from PDF"
                if is_approximate:
                    st.warning(f"🟡 Extracted Approximate Retail Holding: {holding_pct:.2f}% (Source: {data_source})")
                else:
                    st.info(f"🟢 Successfully extracted Exact Retail Holding: {holding_pct:.2f}% (Source: {data_source})")
                
        # Calculations
        price_val = extracted_data.get('buyback_price')
        try:
            buyback_price = float(str(price_val).replace(',', '')) if price_val else 0.0
        except ValueError:
            buyback_price = 0.0
            
        size_val = extracted_data.get('buyback_size')
        
        participation_assumption = 100.0
        acceptance_ratio = extractor.calculate_acceptance_ratio(size_val, buyback_price, holding_pct, participation_assumption)
        
        with st.expander("🔍 Raw Field Extraction Debugger"):
            st.write("What the AI Agent found before processing:")
            st.json(extracted_data)

        # Massive Decision Banner
        if acceptance_ratio > 8.0:
            st.success(f"✅ SIGNAL: APPLY FOR BUYBACK (Est. Acceptance: {acceptance_ratio:.2f}%)")
        else:
            st.error(f"❌ SIGNAL: AVOID (Est. Acceptance: {acceptance_ratio:.2f}%)")
            
        st.info(f"⚙️ Method Detected: **{extracted_data.get('offer_type', 'Unknown')}**")
            
        # Metric Cards
        st.write("### Announcement Details")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Buyback Size (Cr)", extracted_data.get("buyback_size", "N/A"))
        col2.metric("Buyback Price", extracted_data.get("buyback_price", "N/A"))
        col3.metric("Record Date", extracted_data.get("record_date", "N/A"))
        col4.metric("Offer Type", extracted_data.get("offer_type", "N/A"))
        
        st.write("### Profitability Metrics")
        dcol1, dcol2, dcol3, dcol4 = st.columns(4)
        dcol1.metric("Retail Holding %", f"{holding_pct:.2f}%", source_label)
        dcol2.metric("Est. Acceptance Ratio", f"{acceptance_ratio:.2f}%")
        
        if buyback_price > 0 and cmp_price is not None and cmp_price > 0:
            expected_profit, avg_realized = extractor.calculate_profitability(cmp_price, expected_post_price, buyback_price, acceptance_ratio)
            profit_pct = (expected_profit / cmp_price) * 100 if cmp_price > 0 else 0.0
            
            dcol3.metric("Avg Realized Price", f"₹{avg_realized:.2f}")
            dcol4.metric("Expected Profit (Per Share)", f"₹{expected_profit:.2f}", f"{profit_pct:.2f}%")
        else:
            dcol3.metric("Avg Realized Price", "N/A")
            dcol4.metric("Expected Profit (Per Share)", "N/A")

        st.write("---")
        
        if st.checkbox("Show Raw Extracted PDF Text"):
            if st.session_state.raw_text_announcement and len(st.session_state.raw_text_announcement.strip()) > 0:
                st.write("**Announcement Text**")
                st.code(st.session_state.raw_text_announcement, language="text")
            if st.session_state.raw_text_shp and len(st.session_state.raw_text_shp.strip()) > 0:
                st.write("**SHP Text**")
                st.code(st.session_state.raw_text_shp, language="text")
