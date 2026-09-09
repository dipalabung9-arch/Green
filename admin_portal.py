# ==========================================
# FACTORY ADMINISTRATOR PORTAL (admin_portal.py)
# ==========================================
import streamlit as st
import sqlite3
import pandas as pd
import datetime
import re
from database import DB_FILE, get_setting, update_setting

def format_inr(amount):
    """Formats numbers strictly according to the Indian numbering system (e.g., 1,50,000.00)"""
    try:
        val = float(amount)
        if val < 0:
            s = f"-{abs(val):.2f}"
        else:
            s = f"{val:.2f}"
        
        parts = s.split('.')
        integer_part = parts[0]
        decimal_part = parts[1]
        
        if len(integer_part) <= 3:
            result = integer_part
        else:
            last_three = integer_part[-3:]
            other_digits = integer_part[:-3]
            
            formatted_other = ""
            while len(other_digits) > 2:
                formatted_other = "," + other_digits[-2:] + formatted_other
                other_digits = other_digits[:-2]
            if other_digits:
                formatted_other = other_digits + formatted_other
                
            result = formatted_other + "," + last_three
            
        return f"{result}.{decimal_part}"
    except Exception:
        return str(amount)

def calculate_and_update_advance_cf(grower_id):
    """Calculates and updates advance carry forward strictly according to accounting norms:
    Closing Balance = Opening Balance + New Advances Issued - Total Advance Recovered
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT advance_balance, cf_balance FROM growers WHERE id = ?", (grower_id,))
    grower = cursor.fetchone()
    if not grower:
        conn.close()
        return 0.0
        
    opening_balance = grower[0] or 0.0
    
    cursor.execute("SELECT SUM(amount) FROM field_advances WHERE grower_id = ?", (grower_id,))
    total_new_advances = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT SUM(advance_recovery) FROM collections WHERE grower_id = ?", (grower_id,))
    total_recoveries = cursor.fetchone()[0] or 0.0
    
    closing_advance_cf = (opening_balance + total_new_advances) - total_recoveries
    closing_advance_cf = max(0.0, closing_advance_cf)
    
    cursor.execute("""
        UPDATE growers 
        SET advance_balance = ?, cf_balance = ? 
        WHERE id = ?
    """, (closing_advance_cf, closing_advance_cf, grower_id))
    
    conn.commit()
    conn.close()
    return closing_advance_cf

def render_admin_portal():
    st.header("💻 Factory Administrator Command Center")
    admin_tab = st.selectbox("Admin Action View", [
        "Overview & Live Metrics", 
        "Grower Master & Online Editor", 
        "Dynamic Categories & Rates", 
        "Chemicals & Advances Ledger", 
        "Collection Ledger",
        "Analytics & Reports",
        "System Backup & Restore"
    ])
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(gross_weight), SUM(net_payable_weight), SUM(advance_recovery), SUM(net_final_payable) FROM collections")
    col_metrics = cursor.fetchone()
    cursor.execute("SELECT SUM(advance_balance), SUM(cf_balance) FROM growers")
    grower_ledgers = cursor.fetchone()
    cursor.execute("SELECT SUM(amount) FROM field_advances")
    total_field_advances = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT COUNT(*) FROM growers")
    g_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM collections")
    c_count = cursor.fetchone()[0]
    conn.close()
    
    total_gross = col_metrics[0] or 0.0
    total_net_wt = col_metrics[1] or 0.0
    total_advance_recovered = col_metrics[2] or 0.0
    total_payable_liability = col_metrics[3] or 0.0
    outstanding_advances = grower_ledgers[0] or 0.0

    if admin_tab == "Overview & Live Metrics":
        st.subheader("📊 Factory Summary Metrics")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Registered Growers", f"{g_count:,}")
        c2.metric("Total Collections", f"{c_count:,}")
        c3.metric("Gross Tonnage (Kg)", format_inr(total_gross))
        c4.metric("Net Payable Wt (Kg)", format_inr(total_net_wt))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Advance Recovered (₹)", f"₹ {format_inr(total_advance_recovered)}")
        c6.metric("Total Field Advances Issued (₹)", f"₹ {format_inr(total_field_advances)}")
        c7.metric("Outstanding Advance Bal (₹)", f"₹ {format_inr(outstanding_advances)}")
        c8.metric("Factory Liability (₹)", f"₹ {format_inr(total_payable_liability)}")
        
        st.markdown("---")
        st.subheader("👥 Grower-Wise Outstanding Balances")
        conn = sqlite3.connect(DB_FILE)
        df_grower_advances = pd.read_sql("SELECT id, name, route, phone, advance_balance, cf_balance, extra_info FROM growers", conn)
        conn.close()
        
        if not df_grower_advances.empty:
            df_grower_advances['advance_balance'] = df_grower_advances['advance_balance'].apply(format_inr)
            df_grower_advances['cf_balance'] = df_grower_advances['cf_balance'].apply(format_inr)
            
        st.dataframe(df_grower_advances, use_container_width=True)

    elif admin_tab == "Grower Master & Online Editor":
        st.subheader("🏷️ Grower Master: Bulk Import & Online Details Editor")
        st.info("Edit grower profiles, bank details, or custom rainy-day water deduction percentages directly. Existing details are preserved.")
        
        with st.expander("📂 Upload Grower Excel / CSV File"):
            uploaded_file = st.file_uploader("Upload your growers spreadsheet", type=["csv", "xlsx"])
            if uploaded_file is not None:
                try:
                    df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, sheet_name=0)
                    if st.button("🚀 Process & Import File (Safe Merge)", type="primary"):
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        success_count = 0
                        
                        cols_lower = {c.lower().strip(): c for c in df_upload.columns}
                        id_col = next((cols_lower[c] for c in ['id', 'grower id', 'gid'] if c in cols_lower), None)
                        name_col = next((cols_lower[c] for c in ['name', 'grower name', 'full name', 'grower'] if c in cols_lower), None)
                        route_col = next((cols_lower[c] for c in ['address', 'route', 'village', 'area'] if c in cols_lower), None)
                        phone_col = next((cols_lower[c] for c in ['phone', 'mobile no', 'mobile', 'contact'] if c in cols_lower), None)
                        bank_col = next((cols_lower[c] for c in ['bank_name', 'bank', 'bank name'] if c in cols_lower), None)
                        acc_col = next((cols_lower[c] for c in ['account_no', 'account', 'acc no', 'account number'] if c in cols_lower), None)
                        water_col = next((cols_lower[c] for c in ['water_ded', 'water', 'deduction', 'custom_water'] if c in cols_lower), None)
                        
                        if not name_col:
                            st.error("Could not find a 'Name' column in your file.")
                        else:
                            for _, row in df_upload.iterrows():
                                g_name = str(row.get(name_col, '')).strip()
                                if not g_name or g_name.lower() in ['nan', 'none', '']: continue
                                    
                                g_id = str(row.get(id_col, '')).strip() if id_col and pd.notna(row[id_col]) else ""
                                if not g_id or g_id.lower() == 'nan':
                                    cursor.execute("SELECT id FROM growers ORDER BY id DESC LIMIT 1")
                                    last_row = cursor.fetchone()
                                    next_num = int(last_row[0].replace('RT', '')) + 1 if last_row and last_row[0].startswith('RT') and last_row[0].replace('RT', '').isdigit() else 101
                                    g_id = f"RT{next_num}"
                                    
                                g_route = str(row.get(route_col, '')).strip() if route_col and pd.notna(row[route_col]) else 'Route-A'
                                g_phone = str(row.get(phone_col, '')).strip() if phone_col and pd.notna(row[phone_col]) else ''
                                if g_phone.endswith('.0'): g_phone = g_phone[:-2]
                                
                                bank_name = str(row.get(bank_col, '')).strip() if bank_col and pd.notna(row[bank_col]) else ''
                                acc_no = str(row.get(acc_col, '')).strip() if acc_col and pd.notna(row[acc_col]) else ''
                                if acc_no.endswith('.0'): acc_no = acc_no[:-2]
                                water_val = str(row.get(water_col, '')).strip() if water_col and pd.notna(row[water_col]) else ''
                                
                                extra_dict = {}
                                if bank_name: extra_dict['Bank_Name'] = bank_name
                                if acc_no: extra_dict['Account_No'] = acc_no
                                if water_val and water_val != 'nan': extra_dict['Water_Ded'] = water_val
                                extra_info_str = " | ".join([f"{k}: {v}" for k, v in extra_dict.items()])
                                
                                cursor.execute("SELECT name, route, phone, extra_info FROM growers WHERE id = ?", (g_id,))
                                existing_row = cursor.fetchone()
                                
                                if existing_row:
                                    ex_name, ex_route, ex_phone, ex_extra = existing_row
                                    final_name = g_name if g_name and g_name != 'nan' else ex_name
                                    final_route = g_route if g_route and g_route != 'nan' else ex_route
                                    final_phone = g_phone if g_phone and g_phone != 'nan' else ex_phone
                                    
                                    ex_dict = {}
                                    if ex_extra:
                                        for p in ex_extra.split(" | "):
                                            if ":" in p:
                                                k, v = p.split(":", 1)
                                                ex_dict[k.strip()] = v.strip()
                                    for k, v in extra_dict.items():
                                        if v and v != 'nan': ex_dict[k] = v
                                    final_extra = " | ".join([f"{k}: {v}" for k, v in ex_dict.items()])
                                        
                                    cursor.execute("UPDATE growers SET name = ?, route = ?, phone = ?, extra_info = ? WHERE id = ?", 
                                                   (final_name, final_route, final_phone, final_extra, g_id))
                                else:
                                    cursor.execute("INSERT INTO growers (id, name, route, phone, advance_balance, cf_balance, extra_info, created_at) VALUES (?, ?, ?, ?, 0.0, 0.0, ?, ?)", 
                                                   (g_id, g_name, g_route, g_phone, extra_info_str, datetime.date.today().isoformat()))
                                success_count += 1
                                
                            conn.commit()
                            conn.close()
                            st.success(f"Successfully processed **{success_count}** growers!")
                            st.rerun()
                except Exception as e:
                    st.error(f"Error parsing file: {e}")

        st.markdown("---")
        st.subheader("✏️ Interactive Online Grower Details & Custom Water Deductions")
        conn = sqlite3.connect(DB_FILE)
        df_growers = pd.read_sql("SELECT id, name, route, phone, advance_balance, extra_info FROM growers", conn)
        conn.close()
        
        bank_list, acc_list, water_list = [], [], []
        for extra in df_growers['extra_info']:
            b_val, a_val, w_val = "", "", ""
            if extra:
                for p in extra.split(" | "):
                    if "Bank_Name:" in p: b_val = p.replace("Bank_Name:", "").strip()
                    if "Account_No:" in p: a_val = p.replace("Account_No:", "").strip()
                    if "Water_Ded:" in p: w_val = p.replace("Water_Ded:", "").strip()
            bank_list.append(b_val)
            acc_list.append(a_val)
            water_list.append(w_val)
            
        df_growers['Bank_Name'] = bank_list
        df_growers['Account_No'] = acc_list
        df_growers['Water_Ded (%)'] = water_list
        df_editable = df_growers[['id', 'name', 'route', 'phone', 'Bank_Name', 'Account_No', 'Water_Ded (%)', 'advance_balance']]
        
        edited_growers_df = st.data_editor(df_editable, use_container_width=True, num_rows="dynamic", key="online_grower_grid")
        
        if st.button("💾 Save All Online Changes & Custom Deductions", type="primary"):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            for _, row in edited_growers_df.iterrows():
                g_id = str(row['id']).strip()
                g_name = str(row['name']).strip()
                if not g_id or g_id == 'nan' or not g_name or g_name == 'nan': continue
                    
                g_route = str(row['route']).strip() if pd.notna(row['route']) else 'Route-A'
                g_phone = str(row['phone']).strip() if pd.notna(row['phone']) else ''
                if g_phone.endswith('.0'): g_phone = g_phone[:-2]
                
                b_name = str(row['Bank_Name']).strip() if pd.notna(row['Bank_Name']) else ''
                a_no = str(row['Account_No']).strip() if pd.notna(row['Account_No']) else ''
                if a_no.endswith('.0'): a_no = a_no[:-2]
                w_pct = str(row['Water_Ded (%)']).strip() if pd.notna(row['Water_Ded (%)']) else ''
                
                extra_parts = []
                if b_name and b_name != 'nan': extra_parts.append(f"Bank_Name: {b_name}")
                if a_no and a_no != 'nan': extra_parts.append(f"Account_No: {a_no}")
                if w_pct and w_pct != 'nan': extra_parts.append(f"Water_Ded: {w_pct}")
                new_extra = " | ".join(extra_parts)
                
                cursor.execute("SELECT id FROM growers WHERE id = ?", (g_id,))
                if cursor.fetchone():
                    cursor.execute("UPDATE growers SET name = ?, route = ?, phone = ?, extra_info = ? WHERE id = ?", 
                                   (g_name, g_route, g_phone, new_extra, g_id))
                else:
                    cursor.execute("INSERT INTO growers (id, name, route, phone, advance_balance, cf_balance, extra_info, created_at) VALUES (?, ?, ?, ?, 0.0, 0.0, ?, ?)", 
                                   (g_id, g_name, g_route, g_phone, new_extra, datetime.date.today().isoformat()))
            conn.commit()
            conn.close()
            st.success("All grower details and custom water deductions saved successfully!")
            st.rerun()

    elif admin_tab == "Dynamic Categories & Rates":
        st.subheader("⚙️ Fully Dynamic Categories, Pricing, Moisture & Agency Controls")
        current_agency = get_setting("agency_name", "NUMA GREENLEAF ENTERPRISE")
        new_agency = st.text_input("Agent / Company Name (Displays on Slips)", value=current_agency)
        
        st.markdown("---")
        current_override = get_setting("sunday_override", "OFF")
        override_toggle = st.radio("Emergency Sunday Collection Override", ["OFF", "ON (Allow Sunday Collection)"], index=0 if current_override == "OFF" else 1, horizontal=True)
        def_w = float(get_setting("default_water_deduction", 0.0))
        def_w_in = st.number_input("Default Wet Deduction (%)", value=def_w, step=0.1, format="%.2f")

        st.markdown("---")
        st.subheader("🌿 Manage Leaf Categories & Rates (Dynamic)")
        conn = sqlite3.connect(DB_FILE)
        cat_df = pd.read_sql("SELECT name, rate FROM categories", conn)
        conn.close()
        
        edited_cat_df = st.data_editor(cat_df, use_container_width=True, num_rows="dynamic", key="cat_editor_grid")
        
        if st.button("Save All Dynamic Settings & Rates", type="primary"):
            update_setting("agency_name", new_agency.strip())
            update_setting("sunday_override", "ON" if "ON" in override_toggle else "OFF")
            update_setting("default_water_deduction", str(def_w_in))
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM categories")
            
            new_rates_map = {}
            for _, row in edited_cat_df.iterrows():
                c_name = str(row['name']).strip().upper()
                c_rate = float(row['rate'])
                if c_name and c_name != 'NAN':
                    cursor.execute("INSERT OR REPLACE INTO categories (name, rate) VALUES (?, ?)", (c_name, c_rate))
                    new_rates_map[c_name] = c_rate
                    
            conn.commit()
            
            cursor.execute("SELECT id, category, net_payable_weight, advance_recovery FROM collections")
            all_cols = cursor.fetchall()
            synced_count = 0
            for col_id, cat_name, net_wt, adv_rec in all_cols:
                upper_cat = str(cat_name).upper().strip()
                if upper_cat in new_rates_map:
                    new_rate = new_rates_map[upper_cat]
                    gross_amt = net_wt * new_rate
                    net_payable = gross_amt - adv_rec
                    cursor.execute('''
                        UPDATE collections 
                        SET category_rate = ?, total_amount = ?, net_final_payable = ?
                        WHERE id = ?
                    ''', (new_rate, gross_amt, net_payable, col_id))
                    synced_count += 1
                    
            conn.commit()
            conn.close()
            st.success(f"Successfully saved rates and dynamically updated **{synced_count}** collection records across the system!")

    elif admin_tab == "Chemicals & Advances Ledger":
        st.subheader("🧪 Field Advances & Chemical/Fertilizer Distribution Ledger")
        st.info("Issue cash advances or chemicals starting at zero. Includes duplicate warning protection and ledger management.")
        
        with st.expander("➕ Issue Advance or Chemical to a Grower Instantly"):
            conn = sqlite3.connect(DB_FILE)
            g_list_df = pd.read_sql("SELECT id, name, route FROM growers", conn)
            conn.close()
            
            if g_list_df.empty:
                st.warning("Please add growers first.")
            else:
                quick_admin_id = st.text_input("⚡ Quick-ID Shortcut (Type Number like 101)", placeholder="Type ID digits...", key="admin_quick_id")
                target_admin_id = ""
                if quick_admin_id:
                    matched_admin = g_list_df[g_list_df['id'].str.contains(quick_admin_id.strip(), case=False, na=False)]
                    if not matched_admin.empty:
                        target_admin_id = matched_admin.iloc[0]['id']
                        st.success(f"⚡ Matched: {matched_admin.iloc[0]['name']} ({target_admin_id})")

                raw_g_options = g_list_df.apply(lambda r: f"{r['name']} (ID: {r['id']} | Route: {r['route']})", axis=1).tolist()
                g_options = [""] + raw_g_options
                
                admin_default_idx = 0
                if target_admin_id:
                    for idx, opt in enumerate(raw_g_options):
                        if target_admin_id in opt:
                            admin_default_idx = idx + 1
                            break

                sel_g_str = st.selectbox(
                    "🔍 Search & Select Grower", 
                    options=g_options, 
                    index=admin_default_idx, 
                    placeholder="Choose or type grower name/ID...", 
                    key="admin_issue_g"
                )
                
                sel_g_id = ""
                if sel_g_str:
                    id_match = re.search(r'\(ID: (.*?) \|', sel_g_str)
                    sel_g_id = id_match.group(1) if id_match else sel_g_str.split(" - ")[0]
                
                adv_type = st.radio("Issue Type", ["Cash Advance", "Chemical / Fertilizer"], horizontal=True, key="admin_issue_type")
                
                if adv_type == "Cash Advance":
                    item_lbl = "Cash"
                    qty_val = 1.0
                    amt_val = st.number_input("Total Amount / Debit (₹)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="admin_issue_amt")
                else:
                    item_lbl = st.text_input("Item Name", value="Urea / Fertilizer", key="admin_issue_item")
                    col_q, col_p = st.columns(2)
                    qty_val = col_q.number_input("Quantity", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="admin_issue_qty")
                    price_val = col_p.number_input("Price per Unit (₹)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="admin_issue_price")
                    
                    amt_val = qty_val * price_val
                    st.success(f"💰 **Total Cost Calculated:** ₹ {format_inr(amt_val)}")
                
                if st.button("🚀 Issue Advance & Update Balance", type="primary", key="admin_issue_btn"):
                    if not sel_g_id:
                        st.warning("Please select a valid grower first.")
                    elif amt_val <= 0:
                        st.warning("Please enter a valid amount or calculate a cost greater than zero.")
                    else:
                        today_d = datetime.date.today().isoformat()
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        
                        cursor.execute('''
                            SELECT COUNT(*) FROM field_advances 
                            WHERE grower_id = ? AND advance_type = ? AND item_name = ? AND amount = ? AND advance_date = ?
                        ''', (sel_g_id, adv_type, item_lbl, amt_val, today_d))
                        dup_count = cursor.fetchone()[0]
                        
                        proceed = True
                        if dup_count > 0:
                            st.warning(f"⚠️ **Duplicate Warning:** An identical entry of ₹{format_inr(amt_val)} for this grower was already recorded today ({today_d}).")
                            confirm_duplicate = st.checkbox("I confirm this is a separate, intentional transaction and not a mistake.", key="admin_dup_conf")
                            proceed = confirm_duplicate

                        if proceed:
                            cursor.execute('''
                                INSERT INTO field_advances (grower_id, driver_id, advance_type, item_name, quantity, amount, advance_date)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (sel_g_id, "ADMIN", adv_type, item_lbl, qty_val, amt_val, today_d))
                            conn.commit()
                            conn.close()
                            
                            calculate_and_update_advance_cf(sel_g_id)
                            
                            st.success(f"Successfully issued ₹{format_inr(amt_val)} to grower ID {sel_g_id}!")
                            for key in ["admin_issue_g", "admin_issue_amt", "admin_issue_qty", "admin_issue_price", "admin_quick_id"]:
                                if key in st.session_state:
                                    del st.session_state[key]
                            st.rerun()

        with st.expander("📂 Bulk Import Advances / Chemicals via Excel or CSV"):
            sample_adv_csv = "grower_id,advance_type,item_name,quantity,amount\nRT101,Cash Advance,Cash,1,1000\nRT102,Chemical / Fertilizer,Urea,2,800"
            st.download_button("📥 Download Advance Sample CSV Template", sample_adv_csv, "advances_template.csv", "text/csv")
            
            adv_file = st.file_uploader("Upload Advances Spreadsheet", type=["csv", "xlsx"], key="adv_upload_file")
            if adv_file is not None:
                try:
                    df_adv_up = pd.read_csv(adv_file) if adv_file.name.endswith('.csv') else pd.read_excel(adv_file)
                    st.write("Preview:", df_adv_up.head())
                    if st.button("🚀 Process & Import Bulk Advances", type="primary", key="proc_adv_btn"):
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        today_d = datetime.date.today().isoformat()
                        imp_count = 0
                        affected_growers = set()
                        for _, row in df_adv_up.iterrows():
                            g_id = str(row.get('grower_id', '')).strip()
                            a_type = str(row.get('advance_type', 'Cash Advance')).strip()
                            i_name = str(row.get('item_name', 'Cash')).strip()
                            qty = float(row.get('quantity', 0.0))
                            amt = float(row.get('amount', 0.0))
                            
                            if g_id and amt > 0:
                                cursor.execute('''
                                    INSERT INTO field_advances (grower_id, driver_id, advance_type, item_name, quantity, amount, advance_date)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', (g_id, "ADMIN-BULK", a_type, i_name, qty, amt, today_d))
                                affected_growers.add(g_id)
                                imp_count += 1
                        conn.commit()
                        conn.close()
                        
                        for g_id in affected_growers:
                            calculate_and_update_advance_cf(g_id)
                            
                        st.success(f"Successfully imported {imp_count} advance records and updated grower balances!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error importing file: {e}")

        st.markdown("---")
        st.subheader("📋 Existing Advances & Chemical Distributions Ledger")
        conn = sqlite3.connect(DB_FILE)
        df_adv = pd.read_sql('''
            SELECT f.id, f.grower_id, g.name as grower_name, f.driver_id, f.advance_type, f.item_name, f.quantity, f.amount, f.advance_date 
            FROM field_advances f 
            LEFT JOIN growers g ON f.grower_id = g.id 
            ORDER BY f.id DESC
        ''', conn)
        conn.close()
        
        if not df_adv.empty and 'amount' in df_adv.columns:
            df_adv['amount'] = df_adv['amount'].apply(format_inr)
            
        st.dataframe(df_adv, use_container_width=True)

        st.markdown("---")
        st.subheader("🗑️ Delete / Correct an Accidental Advance Entry")
        st.warning("⚠️ Deleting a transaction will automatically reverse and recompute the grower's outstanding balance.")
        
        conn = sqlite3.connect(DB_FILE)
        adv_list_df = pd.read_sql('''
            SELECT f.id, f.grower_id, g.name as grower_name, f.advance_type, f.amount, f.advance_date 
            FROM field_advances f 
            LEFT JOIN growers g ON f.grower_id = g.id 
            ORDER BY f.id DESC LIMIT 50
        ''', conn)
        conn.close()
        
        if adv_list_df.empty:
            st.info("No advance records found to delete.")
        else:
            del_options = [""] + adv_list_df.apply(lambda r: f"ID: {r['id']} | {r['grower_name']} ({r['grower_id']}) - ₹{format_inr(r['amount'])} ({r['advance_type']} on {r['advance_date']})", axis=1).tolist()
            sel_del_str = st.selectbox(
                "Select Transaction to Delete", 
                options=del_options, 
                index=0, 
                placeholder="Choose a transaction to delete...", 
                key="del_adv_select"
            )
            
            if sel_del_str:
                id_match = re.search(r'ID: (\d+) \|', sel_del_str)
                if id_match:
                    del_id = int(id_match.group(1))
                    
                    if st.button("🚨 Confirm & Delete Transaction (Reverses Balance)", type="primary", key="confirm_del_btn"):
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        cursor.execute("SELECT grower_id, amount FROM field_advances WHERE id = ?", (del_id,))
                        rec = cursor.fetchone()
                        
                        if rec:
                            g_id, amt = rec
                            cursor.execute("DELETE FROM field_advances WHERE id = ?", (del_id,))
                            conn.commit()
                            conn.close()
                            
                            calculate_and_update_advance_cf(g_id)
                            
                            st.success(f"Successfully deleted transaction ID {del_id} and recomputed grower {g_id}'s balance!")
                            if "del_adv_select" in st.session_state:
                                del st.session_state["del_adv_select"]
                            st.rerun()
                        else:
                            conn.close()
                            st.error("Selected transaction could not be found in the database.")

    elif admin_tab == "Collection Ledger":
        st.subheader("📋 Master Collection Ledger & Manual Date-Wise Water Adjustment")
        st.info("Select a date to view collections. Dates and grower names are shown first. Updating water deductions recalculates values and synchronizes carry forward balances strictly according to accounting norms.")
        
        conn = sqlite3.connect(DB_FILE)
        dates_df = pd.read_sql("SELECT DISTINCT collection_date FROM collections ORDER BY collection_date DESC", conn)
        conn.close()
        
        if dates_df.empty:
            st.info("No collection records found in the database.")
        else:
            date_options = [""] + dates_df['collection_date'].tolist()
            selected_date = st.selectbox(
                "📅 Select Collection Date", 
                options=date_options, 
                index=0, 
                placeholder="Choose collection date...", 
                key="ledger_date_select"
            )
            
            if selected_date:
                conn = sqlite3.connect(DB_FILE)
                query = """
                    SELECT c.collection_date, c.grower_id, g.name as grower_name, 
                           c.id, c.gross_weight, c.category, c.water_deduction_pct, 
                           c.net_payable_weight, c.category_rate, c.total_amount, 
                           c.advance_recovery, c.net_final_payable 
                    FROM collections c 
                    LEFT JOIN growers g ON c.grower_id = g.id 
                    WHERE c.collection_date = ? 
                    ORDER BY c.id DESC
                """
                day_cols_df = pd.read_sql(query, conn, params=(selected_date,))
                
                rates_df = pd.read_sql("SELECT name, rate FROM categories", conn)
                conn.close()
                
                rates_dict = dict(zip(rates_df['name'].str.upper().str.strip(), rates_df['rate']))
                
                if day_cols_df.empty:
                    st.warning(f"No collections found for date: {selected_date}")
                else:
                    st.write(f"Showing **{len(day_cols_df)}** collections for **{selected_date}**. Edit `water_deduction_pct` directly below:")
                    
                    cols_order = ['collection_date', 'grower_id', 'grower_name', 'id', 'gross_weight', 'category', 'water_deduction_pct', 'net_payable_weight', 'category_rate', 'total_amount', 'advance_recovery', 'net_final_payable']
                    day_cols_editable = day_cols_df[cols_order]
                    
                    edited_cols_df = st.data_editor(
                        day_cols_editable, 
                        use_container_width=True, 
                        disabled=['collection_date', 'grower_id', 'grower_name', 'id', 'gross_weight', 'category', 'category_rate', 'advance_recovery'],
                        key="editable_collection_ledger"
                    )
                    
                    if st.button("💾 Save & Recalculate Water Deductions", type="primary"):
                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        update_count = 0
                        affected_growers = set()
                        
                        for _, row in edited_cols_df.iterrows():
                            col_id = int(row['id'])
                            g_id = str(row['grower_id'])
                            new_water_pct = float(row['water_deduction_pct'])
                            g_wt = float(row['gross_weight'])
                            cat_name = str(row['category']).upper().strip()
                            adv_rec = float(row['advance_recovery'])
                            
                            live_rate = float(rates_dict.get(cat_name, row['category_rate']))
                            
                            net_wt = g_wt * (1.0 - (new_water_pct / 100.0))
                            gross_amt = net_wt * live_rate
                            net_payable = gross_amt - adv_rec
                            
                            cursor.execute('''
                                UPDATE collections 
                                SET water_deduction_pct = ?, category_rate = ?, net_payable_weight = ?, total_amount = ?, net_final_payable = ?
                                WHERE id = ?
                            ''', (new_water_pct, live_rate, net_wt, gross_amt, net_payable, col_id))
                            update_count += 1
                            affected_growers.add(g_id)
                            
                        conn.commit()
                        conn.close()
                        
                        for g_id in affected_growers:
                            calculate_and_update_advance_cf(g_id)
                            
                        st.success(f"Successfully updated water deductions, synced live category rates, and recalculated **{update_count}** entries for {selected_date}!")
                        st.rerun()

    elif admin_tab == "Analytics & Reports":
        st.subheader("📈 Factory Analytics & Reports")
        tab_sub1, tab_sub2, tab_sub3 = st.tabs(["🚚 Route Tonnage Summary", "💧 Moisture Trends", "📄 Monthly Statement"])
        
        with tab_sub1:
            conn = sqlite3.connect(DB_FILE)
            route_df = pd.read_sql('''
                SELECT g.route, COUNT(c.id) as total_trips, SUM(c.gross_weight) as total_gross_wt, SUM(c.net_payable_weight) as total_net_wt 
                FROM collections c JOIN growers g ON c.grower_id = g.id 
                GROUP BY g.route
            ''', conn)
            conn.close()
            if not route_df.empty:
                route_df['total_gross_wt'] = route_df['total_gross_wt'].apply(format_inr)
                route_df['total_net_wt'] = route_df['total_net_wt'].apply(format_inr)
                st.dataframe(route_df, use_container_width=True)
            else:
                st.info("No collection data recorded yet.")
                
        with tab_sub2:
            conn = sqlite3.connect(DB_FILE)
            moist_df = pd.read_sql("SELECT collection_date, water_deduction_pct FROM collections ORDER BY collection_date ASC", conn)
            conn.close()
            if not moist_df.empty:
                st.dataframe(moist_df, use_container_width=True)
            else:
                st.info("No data available.")

        with tab_sub3:
            conn = sqlite3.connect(DB_FILE)
            g_list = pd.read_sql("SELECT id, name FROM growers", conn)
            conn.close()
            if not g_list.empty:
                g_options_stmt = [""] + g_list.apply(lambda r: f"{r['id']} - {r['name']}", axis=1).tolist()
                selected_g_stmt = st.selectbox(
                    "Select Grower for Statement", 
                    options=g_options_stmt, 
                    index=0, 
                    placeholder="Choose a grower...", 
                    key="stmt_grower_select"
                )
                
                if selected_g_stmt:
                    g_id_stmt = selected_g_stmt.split(" - ")[0]
                    
                    conn = sqlite3.connect(DB_FILE)
                    stmt_cols = pd.read_sql("SELECT collection_date, gross_weight, category, water_deduction_pct, net_payable_weight, category_rate, total_amount, advance_recovery, net_final_payable FROM collections WHERE grower_id = ?", conn, params=(g_id_stmt,))
                    stmt_advs = pd.read_sql("SELECT advance_date, advance_type, item_name, amount FROM field_advances WHERE grower_id = ?", conn, params=(g_id_stmt,))
                    g_row_info = pd.read_sql("SELECT * FROM growers WHERE id = ?", conn, params=(g_id_stmt,)).iloc[0]
                    conn.close()
                    
                    st.markdown(f"#### Statement for: {g_row_info['id']} - {g_row_info['name']} (Route: {g_row_info['route']})")
                    st.metric("Current Outstanding Advance Balance", f"₹ {format_inr(g_row_info['advance_balance'])}")
                    st.metric("Carry Forward (CF) Advance Balance", f"₹ {format_inr(g_row_info['cf_balance'])}")
                    
                    if not stmt_cols.empty:
                        for col in ['gross_weight', 'net_payable_weight', 'category_rate', 'total_amount', 'advance_recovery', 'net_final_payable']:
                            if col in stmt_cols.columns:
                                stmt_cols[col] = stmt_cols[col].apply(format_inr)
                                
                    if not stmt_advs.empty and 'amount' in stmt_advs.columns:
                        stmt_advs['amount'] = stmt_advs['amount'].apply(format_inr)
                        
                    st.write("**Collections Ledger:**")
                    st.dataframe(stmt_cols, use_container_width=True)
                    st.write("**Advances Ledger:**")
                    st.dataframe(stmt_advs, use_container_width=True)
            else:
                st.info("No growers available.")

    elif admin_tab == "System Backup & Restore":
        st.subheader("🛡️ Database Backup & Restore")
        with open(DB_FILE, "rb") as f:
            db_bytes = f.read()
        st.download_button("📥 Database Backup (.db)", data=db_bytes, file_name=f"tea_factory_backup_{datetime.date.today().strftime('%Y%m%d')}.db", mime="application/octet-stream", type="primary")
        
        uploaded_db = st.file_uploader("Upload .db file to restore", type=["db"])
        if uploaded_db is not None:
            if st.button("⚠️ Confirm Restore", type="primary"):
                with open(DB_FILE, "wb") as f:
                    f.write(uploaded_db.getbuffer())
                st.success("Database restored successfully!")
                st.rerun()