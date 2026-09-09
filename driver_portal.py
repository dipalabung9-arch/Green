# ==========================================
# DRIVER PORTAL - SLIP DIRECTLY BELOW SAVE BUTTON (driver_portal.py)
# ==========================================
import streamlit as st
import sqlite3
import pandas as pd
import datetime
import urllib.parse
import re
from database import DB_FILE, get_setting

def render_driver_portal():
    st.header("📱 Driver Field Collection & App")
    st.info("Record weights and grades. Slips issued to growers contain weights and grades only.")
    
    conn = sqlite3.connect(DB_FILE)
    growers_df = pd.read_sql("SELECT id, name, route, phone, advance_balance FROM growers", conn)
    categories_df = pd.read_sql("SELECT name, rate FROM categories", conn)
    conn.close()
    
    if growers_df.empty:
        st.warning("No registered growers found. Please ask Admin to add growers first.")
        return
        
    if categories_df.empty:
        st.warning("No leaf categories defined. Please ask Admin to add categories in the admin dashboard.")
        return
        
    driver_id = st.text_input("Driver ID", value="DRIVER-01")
    driver_tab = st.selectbox("Driver Action Mode", ["Log Green Leaf Collection", "Issue Field Advance / Chemicals", "Manage Today's Entries (Update/Delete)"])
    cat_options = categories_df['name'].tolist()
    cat_rates_dict = dict(zip(categories_df['name'], categories_df['rate']))
    
    if driver_tab == "Log Green Leaf Collection":
        is_sunday = datetime.date.today().weekday() == 6
        sunday_override_status = get_setting("sunday_override", "OFF")
        
        if is_sunday and sunday_override_status == "OFF":
            st.markdown(
                """
                <div style="background-color:#FF4B4B; padding:15px; border-radius:8px; margin-bottom:20px; text-align:center;">
                    <h2 style="color:white; margin:0; font-weight:bold;">🚨 TODAY IS SUNDAY! 🚨</h2>
                    <p style="color:white; font-size:16px; margin:5px 0 0 0;">Factory holiday / non-procurement day. Green leaf collections are closed.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
        elif is_sunday and sunday_override_status == "ON":
            st.markdown(
                """
                <div style="background-color:#FFA500; padding:12px; border-radius:8px; margin-bottom:20px; text-align:center;">
                    <h3 style="color:white; margin:0; font-weight:bold;">⚠️ SUNDAY OVERRIDE ACTIVE ⚠️</h3>
                    <p style="color:white; font-size:14px; margin:3px 0 0 0;">Admin has permitted emergency collection for today.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        st.subheader("🎙️ AI Voice-to-Text Entry Assistant")
        voice_transcript = st.text_input("Voice Input / Raw Transcript", placeholder="e.g., RT101 45.5 A 50", key="driver_voice_input")
        
        parsed_grower, parsed_wt, parsed_cat, parsed_adv = "", 0.0, cat_options[0] if cat_options else "", 0.0
        
        if voice_transcript:
            parts = voice_transcript.split()
            for p in parts:
                p_upper = p.upper()
                if any(char.isdigit() for char in p_upper) and not any(c.isalpha() for c in p_upper):
                    try:
                        val = float(p)
                        if val > 10: parsed_wt = val
                        else: parsed_adv = val
                    except ValueError:
                        pass
                if p_upper in cat_options: parsed_cat = p_upper
                if "RT" in p_upper or "GRW" in p_upper: parsed_grower = p_upper
            st.success(f"🤖 AI Parsed -> Grower: **{parsed_grower or 'None'}**, Wt: **{parsed_wt}Kg**, Cat: **{parsed_cat}**, Adv Rec: **₹{parsed_adv}**")

        st.markdown("---")
        st.subheader("Leaf Collection Entry Form")
        
        # --- QUICK-ID SHORTCUT BOX ---
        quick_id_input = st.text_input("⚡ Quick-ID Shortcut (Type ID Digits e.g. 101 or Scan Barcode)", placeholder="Type ID digits here...", key="driver_quick_id")
        target_id = ""
        if quick_id_input:
            clean_input = quick_id_input.strip().upper()
            matched_row = growers_df[growers_df['id'].str.contains(clean_input, case=False, na=False)]
            if not matched_row.empty:
                target_id = matched_row.iloc[0]['id']
                st.success(f"⚡ Shortcut Matched: **{matched_row.iloc[0]['name']} ({target_id})**")

        raw_grower_options = growers_df.apply(lambda row: f"{row['name']} (ID: {row['id']} | Route: {row['route']})", axis=1).tolist()
        grower_options = [""] + raw_grower_options
        
        default_index = 0
        if target_id:
            for idx, opt in enumerate(raw_grower_options):
                if target_id in opt:
                    default_index = idx + 1
                    break
        elif parsed_grower:
            for idx, opt in enumerate(raw_grower_options):
                if parsed_grower in opt:
                    default_index = idx + 1
                    break
                
        selected_grower_str = st.selectbox(
            "🔍 Dynamic Search & Select Grower (Type Name or ID)", 
            options=grower_options, 
            index=default_index,
            placeholder="Select or type grower name/ID...",
            key="driver_selected_grower"
        )
        
        selected_grower_id = ""
        selected_grower_name = ""
        g_phone = ""
        
        if selected_grower_str:
            id_match = re.search(r'\(ID: (.*?) \|', selected_grower_str)
            selected_grower_id = id_match.group(1) if id_match else selected_grower_str.split(" - ")[0]
            selected_grower_name_row = growers_df[growers_df['id'] == selected_grower_id]
            selected_grower_name = selected_grower_name_row['name'].values[0] if not selected_grower_name_row.empty else ""
            raw_phone_val = selected_grower_name_row['phone'].values[0] if not selected_grower_name_row.empty else ""
            g_phone = str(raw_phone_val).strip()
            if g_phone.endswith('.0'):
                g_phone = g_phone[:-2]
        
        gross_wt = st.number_input(
            "Gross Weight of Green Leaves (Kg)", 
            min_value=0.0, 
            value=float(parsed_wt) if parsed_wt > 0 else 0.0, 
            step=0.5, 
            format="%.2f", 
            key="driver_gross_wt"
        )
        
        cat_default_idx = cat_options.index(parsed_cat) if parsed_cat in cat_options else 0
        category = st.selectbox("Leaf Category Grade", options=cat_options, index=cat_default_idx, key="driver_category")
        advance_rec = st.number_input(
            "Advance Recovery Amount (₹)", 
            min_value=0.0, 
            value=float(parsed_adv) if parsed_adv > 0 else 0.0, 
            step=1.0, 
            format="%.2f", 
            key="driver_advance_rec"
        )
        
        save_button_disabled = (is_sunday and sunday_override_status == "OFF")
        if save_button_disabled:
            st.error("🔒 Collection saving is locked because today is Sunday.")
            
        if st.button("💾 Save Collection & Sync", type="primary", use_container_width=True, disabled=save_button_disabled):
            if not selected_grower_id:
                st.warning("Please select a valid grower before saving.")
            elif gross_wt <= 0:
                st.warning("Please enter a valid gross weight greater than zero.")
            else:
                today_date = datetime.date.today().isoformat()
                
                # --- DUPLICATE ENTRY CHECK ---
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM collections 
                    WHERE grower_id = ? AND gross_weight = ? AND category = ? AND collection_date = ?
                ''', (selected_grower_id, gross_wt, category, today_date))
                dup_count = cursor.fetchone()[0]
                conn.close()
                
                proceed = True
                if dup_count > 0:
                    st.warning(f"⚠️ **Duplicate Warning:** An identical entry for Grower {selected_grower_id} with Gross Weight {gross_wt}Kg and Grade {category} was already recorded today.")
                    confirm_dup = st.checkbox("I confirm this is a separate, intentional collection and not a duplicate.", key="driver_dup_confirm")
                    proceed = confirm_dup

                if proceed:
                    default_water = float(get_setting("default_water_deduction", 0.0))
                    active_rate = float(cat_rates_dict.get(category, 0.0))
                    
                    net_wt = gross_wt * (1.0 - (default_water / 100.0))
                    gross_amt = net_wt * active_rate
                    net_payable = gross_amt - advance_rec
                    
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO collections (
                            grower_id, driver_id, gross_weight, category, water_deduction_pct,
                            net_payable_weight, category_rate, total_amount, advance_recovery,
                            net_final_payable, collection_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        selected_grower_id, driver_id, gross_wt, category, default_water,
                        net_wt, active_rate, gross_amt, advance_rec, net_payable,
                        today_date
                    ))
                    
                    cursor.execute("UPDATE growers SET advance_balance = advance_balance - ? WHERE id = ?", (advance_rec, selected_grower_id))
                    conn.commit()
                    conn.close()
                    
                    agency_title = get_setting("agency_name", "NUMA GREENLEAF ENTERPRISE").upper()
                    
                    slip_text = f"""--- {agency_title} COLLECTION SLIP ---
Grower ID   : {selected_grower_id}
Grower Name : {selected_grower_name}
Date        : {today_date}
----------------------------------------
Gross Weight: {gross_wt} Kg
Category    : Grade {category}
----------------------------------------
Status      : Recorded & Synced to Factory"""
                    
                    st.session_state["last_slip"] = slip_text
                    st.session_state["last_phone"] = g_phone
                    
                    for key in ["driver_selected_grower", "driver_gross_wt", "driver_advance_rec", "driver_quick_id", "driver_voice_input", "driver_dup_confirm"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()

        # --- INSTANT SLIP, WHATSAPP & LOCAL DOWNLOAD PLACED DIRECTLY BELOW SAVE BUTTON ---
        if "last_slip" in st.session_state and st.session_state["last_slip"]:
            st.markdown("---")
            st.success("✅ Collection saved successfully and synced with factory server!")
            st.code(st.session_state["last_slip"])
            
            # --- Local Download Button for Phone/Device Document Folder ---
            slip_filename = f"Collection_Slip_{datetime.date.today().isoformat()}.txt"
            st.download_button(
                label="📥 Save Slip to Phone / Device",
                data=st.session_state["last_slip"],
                file_name=slip_filename,
                mime="text/plain",
                use_container_width=True
            )
            
            last_phone = st.session_state.get("last_phone", "")
            if last_phone and last_phone != "nan" and len(last_phone) >= 10:
                wa_text = urllib.parse.quote(st.session_state["last_slip"])
                st.markdown(f"📲 **[Click to Send Receipt via WhatsApp](https://wa.me/91{last_phone}?text={wa_text})**", unsafe_allow_html=True)
            else:
                st.warning("⚠️ Grower phone number is missing or invalid; WhatsApp receipt option is unavailable for this entry.")
                
            if st.button("🔄 Clear / Dismiss Slip & Log Next"):
                del st.session_state["last_slip"]
                if "last_phone" in st.session_state:
                    del st.session_state["last_phone"]
                st.rerun()

    elif driver_tab == "Issue Field Advance / Chemicals":
        st.subheader("💵 Issue Cash Advance or Factory Chemicals/Fertilizers")
        
        quick_id_adv = st.text_input("⚡ Quick-ID Shortcut (Type ID Digits)", placeholder="Type ID digits...", key="driver_adv_quick")
        target_adv_id = ""
        if quick_id_adv:
            matched_adv = growers_df[growers_df['id'].str.contains(quick_id_adv.strip().upper(), case=False, na=False)]
            if not matched_adv.empty:
                target_adv_id = matched_adv.iloc[0]['id']
                st.success(f"⚡ Matched: {matched_adv.iloc[0]['name']} ({target_adv_id})")

        raw_adv_options = growers_df.apply(lambda row: f"{row['name']} (ID: {row['id']} | Route: {row['route']})", axis=1).tolist()
        adv_options = [""] + raw_adv_options
        
        def_adv_idx = 0
        if target_adv_id:
            for idx, opt in enumerate(raw_adv_options):
                if target_adv_id in opt:
                    def_adv_idx = idx + 1
                    break

        selected_grower_str = st.selectbox(
            "🔍 Search & Select Grower for Issue", 
            options=adv_options, 
            index=def_adv_idx, 
            placeholder="Select or type grower name/ID...",
            key="driver_adv_sel"
        )
        
        selected_grower_id = ""
        if selected_grower_str:
            id_match = re.search(r'\(ID: (.*?) \|', selected_grower_str)
            selected_grower_id = id_match.group(1) if id_match else selected_grower_str.split(" - ")[0]
        
        advance_type = st.radio("Issue Type", ["Cash Advance", "Chemical / Fertilizer"], horizontal=True, key="driver_adv_type")
        
        if advance_type == "Cash Advance":
            item_name = "Cash"
            quantity = 1.0
            amount_val = st.number_input("Total Debit Amount (₹)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="driver_adv_amt")
        else:
            item_name = st.text_input("Chemical / Fertilizer Name", value="Urea / Tea Special Pesticide", key="driver_chem_name")
            col_q, col_p = st.columns(2)
            quantity = col_q.number_input("Quantity (Bottles/Bags)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="driver_chem_qty")
            price_val = col_p.number_input("Price per Unit (₹)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="driver_chem_price")
            
            amount_val = quantity * price_val
            st.success(f"💰 **Total Cost Calculated:** ₹ {amount_val:.2f}")
        
        if st.button("🚀 Issue & Sync Advance", type="primary", use_container_width=True, key="driver_issue_adv_btn"):
            if not selected_grower_id:
                st.warning("Please select a valid grower first.")
            elif amount_val <= 0:
                st.warning("Please enter a valid amount or calculate a cost greater than zero.")
            else:
                today_date = datetime.date.today().isoformat()
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT COUNT(*) FROM field_advances 
                    WHERE grower_id = ? AND advance_type = ? AND item_name = ? AND amount = ? AND advance_date = ?
                ''', (selected_grower_id, advance_type, item_name, amount_val, today_date))
                dup_adv_count = cursor.fetchone()[0]
                
                proceed_adv = True
                if dup_adv_count > 0:
                    st.warning(f"⚠️ **Duplicate Warning:** An identical advance of ₹{amount_val} for this grower was already recorded today.")
                    confirm_adv_dup = st.checkbox("I confirm this is a separate, intentional transaction.", key="driver_adv_dup_conf")
                    proceed_adv = confirm_adv_dup

                if proceed_adv:
                    cursor.execute('''
                        INSERT INTO field_advances (grower_id, driver_id, advance_type, item_name, quantity, amount, advance_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (selected_grower_id, driver_id, advance_type, item_name, quantity, amount_val, today_date))
                    
                    cursor.execute("UPDATE growers SET advance_balance = advance_balance + ? WHERE id = ?", (amount_val, selected_grower_id))
                    conn.commit()
                    conn.close()
                    st.success(f"Successfully issued ₹{amount_val} ({advance_type}) to grower {selected_grower_id}!")
                    for key in ["driver_adv_sel", "driver_adv_amt", "driver_chem_qty", "driver_chem_price", "driver_adv_quick", "driver_adv_dup_conf"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()

    elif driver_tab == "Manage Today's Entries (Update/Delete)":
        st.subheader("🛠️ Manage & Correct Today's Collections")
        st.info("View, edit weight/category, or delete erroneous collection records logged today.")
        
        today_date = datetime.date.today().isoformat()
        conn = sqlite3.connect(DB_FILE)
        today_cols_df = pd.read_sql('''
            SELECT c.id, c.grower_id, g.name as grower_name, c.gross_weight, c.category, c.net_payable_weight, c.advance_recovery, c.net_final_payable 
            FROM collections c 
            LEFT JOIN growers g ON c.grower_id = g.id 
            WHERE c.collection_date = ? 
            ORDER BY c.id DESC
        ''', conn, params=(today_date,))
        conn.close()
        
        if today_cols_df.empty:
            st.warning("No collections recorded for today yet.")
        else:
            st.write(f"Found **{len(today_cols_df)}** entries today. Edit values directly in the table or select a record to delete below:")
            
            edited_today_df = st.data_editor(
                today_cols_df, 
                use_container_width=True, 
                disabled=['id', 'grower_id', 'grower_name', 'net_payable_weight', 'net_final_payable'],
                key="driver_today_editor"
            )
            
            if st.button("💾 Save Table Edits", type="primary", key="save_driver_edits"):
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                for _, row in edited_today_df.iterrows():
                    c_id = int(row['id'])
                    new_wt = float(row['gross_weight'])
                    new_cat = str(row['category']).upper().strip()
                    adv_rec = float(row['advance_recovery'])
                    
                    cursor.execute("SELECT rate FROM categories WHERE name = ?", (new_cat,))
                    r_res = cursor.fetchone()
                    live_rate = r_res[0] if r_res else 0.0
                    
                    default_water = float(get_setting("default_water_deduction", 0.0))
                    net_wt = new_wt * (1.0 - (default_water / 100.0))
                    gross_amt = net_wt * live_rate
                    net_payable = gross_amt - adv_rec
                    
                    cursor.execute('''
                        UPDATE collections 
                        SET gross_weight = ?, category = ?, category_rate = ?, net_payable_weight = ?, total_amount = ?, net_final_payable = ?
                        WHERE id = ?
                    ''', (new_wt, new_cat, live_rate, net_wt, gross_amt, net_payable, c_id))
                conn.commit()
                conn.close()
                st.success("Today's collection records updated successfully!")
                st.rerun()

            st.markdown("---")
            st.subheader("🗑️ Delete Incorrect Collection Entry")
            del_options = [""] + today_cols_df.apply(lambda r: f"ID: {r['id']} | {r['grower_name']} ({r['grower_id']}) - {r['gross_weight']}Kg [{r['category']}]", axis=1).tolist()
            sel_del_col = st.selectbox("Select Entry to Delete", options=del_options, index=0, key="driver_del_col_sel")
            
            if sel_del_col:
                id_match = re.search(r'ID: (\d+) \|', sel_del_col)
                if id_match:
                    target_col_id = int(id_match.group(1))
                    if st.button("🚨 Confirm Delete Collection", type="primary", key="confirm_driver_del_col"):
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        cursor.execute("SELECT grower_id, advance_recovery FROM collections WHERE id = ?", (target_col_id,))
                        c_rec = cursor.fetchone()
                        if c_rec:
                            g_id, adv_rec = c_rec
                            cursor.execute("DELETE FROM collections WHERE id = ?", (target_col_id,))
                            if adv_rec > 0:
                                cursor.execute("UPDATE growers SET advance_balance = advance_balance + ? WHERE id = ?", (adv_rec, g_id))
                            conn.commit()
                            conn.close()
                            st.success(f"Successfully deleted collection ID {target_col_id}!")
                            st.rerun()
                        else:
                            conn.close()
                            st.error("Collection record not found.")