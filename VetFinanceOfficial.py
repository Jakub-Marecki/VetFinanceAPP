# VetFinance – Streamlit + SQLite
# =============================================================================
# Loginy:
#   admin / Grubybob
#   pracownik / kubajestsuper
#
# Uruchom:
#   streamlit run VetFinanceApp.py
#
# Wymagania:
#   pip install streamlit pandas
# =============================================================================

import sqlite3
from datetime import date, timedelta
from calendar import monthrange
import pandas as pd
import streamlit as st

# ------------------ KONTA ------------------
USERS = {
    "admin":     {"password": "Grubybob",      "role": "admin",     "full_name": "Administrator"},
    "pracownik": {"password": "kubajestsuper", "role": "pracownik", "full_name": "Pracownik"},
}

DB = "VetFinanceDB1.db"

# ------------------ DB ---------------------
def cnx():
    return sqlite3.connect(DB, check_same_thread=False)

def ym_bounds(y:int, m:int):
    first = date(y, m, 1)
    last = date(y, m, monthrange(y, m)[1])
    return first, last

def init_db():
    with cnx() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # Recepcja: raport dzienny
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                shift TEXT CHECK(shift IN ('poranna','popołudniowa')) NOT NULL,
                kasa REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                uwagi TEXT,
                staff_vet TEXT,
                staff_tech TEXT
            );
        """)

        # Wielu techników do jednego raportu
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_report_techs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                daily_report_id INTEGER NOT NULL,
                tech_name TEXT NOT NULL,
                FOREIGN KEY(daily_report_id) REFERENCES daily_reports(id) ON DELETE CASCADE
            );
        """)
        # Migracja starego pola staff_tech (jeśli było)
        conn.execute("""
            INSERT INTO daily_report_techs (daily_report_id, tech_name)
            SELECT r.id, r.staff_tech
            FROM daily_reports r
            WHERE r.staff_tech IS NOT NULL AND r.staff_tech <> ''
              AND NOT EXISTS (SELECT 1 FROM daily_report_techs t WHERE t.daily_report_id = r.id)
        """)

        # Faktury kosztowe (AP)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ap_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_date TEXT NOT NULL,
                due_date     TEXT NOT NULL,
                supplier     TEXT NOT NULL,
                number       TEXT,
                category     TEXT,
                amount       REAL NOT NULL,
                notes        TEXT,
                paid         INTEGER DEFAULT 0,
                paid_date    TEXT
            );
        """)

        # NOWE: Faktury przychodowe (AR) – pełen obieg
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ar_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_date  TEXT NOT NULL,  -- data wystawienia
                due_date    TEXT NOT NULL,  -- termin zapłaty
                company     TEXT NOT NULL,
                number      TEXT,
                category    TEXT,
                amount      REAL NOT NULL,
                notes       TEXT,
                paid        INTEGER DEFAULT 0,
                paid_date   TEXT           -- uzupełniane po opłaceniu
            );
        """)

        # MIGRACJA ze starej ar_paid_invoices (jeśli była)
        try:
            has_old = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ar_paid_invoices'"
            ).fetchone()
            if has_old:
                # skopiuj tylko jeśli ar_invoices jest pusta
                cnt_new = conn.execute("SELECT COUNT(*) FROM ar_invoices").fetchone()[0]
                if cnt_new == 0:
                    conn.execute("""
                        INSERT INTO ar_invoices (issue_date, paid_date, company, number, category, amount, notes, paid, due_date)
                        SELECT COALESCE(issue_date, paid_date), paid_date, company, number, category, amount, notes, 1,
                               COALESCE(paid_date, date(paid_date))
                        FROM ar_paid_invoices
                    """)
        except Exception:
            pass

        # Leasingi
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leasings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                monthly_amount REAL NOT NULL,
                start_date     TEXT NOT NULL,
                end_date       TEXT NOT NULL,
                notes          TEXT
            );
        """)

        # Pracownicy
        conn.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                role TEXT CHECK(role IN ('lekarz','technik')) NOT NULL,
                monthly_salary REAL DEFAULT 0,
                active INTEGER DEFAULT 1
            );
        """)

        # Sklep
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                kasa REAL DEFAULT 0,
                terminal REAL DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_date TEXT NOT NULL,
                amount REAL NOT NULL,
                invoice_number TEXT,
                supplier TEXT,
                paid INTEGER DEFAULT 0
            );
        """)

        # Zwierzęta hodowlane
        conn.execute("""
            CREATE TABLE IF NOT EXISTS farm_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                typ TEXT CHECK(typ IN ('magazyn','teren')) NOT NULL,
                kwota REAL DEFAULT 0,
                uwagi TEXT
            );
        """)

        # Seed przykładowych pracowników (jeśli pusto)
        existing = {r[0] for r in conn.execute("SELECT name FROM employees").fetchall()}
        seed_vets = []
        seed_techs = []
        for n in seed_vets:
            if n not in existing:
                conn.execute("INSERT INTO employees (name, role, active) VALUES (?, 'lekarz', 1)", (n,))
        for n in seed_techs:
            if n not in existing:
                conn.execute("INSERT INTO employees (name, role, active) VALUES (?, 'technik', 1)", (n,))

# ------------------ HELPERY -----------------
def get_employee_names_by_role(role: str):
    with cnx() as conn:
        rows = conn.execute("SELECT name FROM employees WHERE active=1 AND role=? ORDER BY name", (role,)).fetchall()
    return [r[0] for r in rows]

def get_employees_df():
    return pd.read_sql_query(
        "SELECT id, name, role, monthly_salary, active FROM employees ORDER BY role, name", cnx()
    )

def sum_leasing_for_month(y:int, m:int) -> float:
    first, last = ym_bounds(y, m)
    with cnx() as conn:
        row = conn.execute(
            "SELECT SUM(monthly_amount) FROM leasings WHERE start_date<=? AND end_date>=?",
            (last.isoformat(), first.isoformat()),
        ).fetchone()
    return float(row[0] or 0)

def sum_salaries_active() -> float:
    with cnx() as conn:
        row = conn.execute("SELECT SUM(monthly_salary) FROM employees WHERE active=1").fetchone()
    return float(row[0] or 0)

def sum_ar_paid_for_month(y:int, m:int) -> float:
    first, last = ym_bounds(y, m)
    with cnx() as conn:
        row = conn.execute(
            "SELECT SUM(amount) FROM ar_invoices WHERE paid=1 AND date(paid_date) BETWEEN ? AND ?",
            (first.isoformat(), last.isoformat())
        ).fetchone()
    return float(row[0] or 0)

# ------------------ UI: RECEPCJA -----------------
def page_recepcja():
    st.header("🧾 Recepcja — raport dzienny")

    # Szybkie dodawanie personelu (inline)
    with st.expander("➕ Szybko dodaj lekarza/technika"):
        c1, c2 = st.columns(2)
        with c1:
            new_vet = st.text_input("Nowy lekarz – imię i nazwisko")
            if st.button("Dodaj lekarza"):
                if new_vet.strip():
                    try:
                        with cnx() as conn:
                            conn.execute("INSERT INTO employees (name, role, active) VALUES (?, 'lekarz', 1)", (new_vet.strip(),))
                        st.success(f"Dodano lekarza: {new_vet.strip()}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Taki pracownik już istnieje.")
        with c2:
            new_tech = st.text_input("Nowy technik – imię i nazwisko")
            if st.button("Dodaj technika"):
                if new_tech.strip():
                    try:
                        with cnx() as conn:
                            conn.execute("INSERT INTO employees (name, role, active) VALUES (?, 'technik', 1)", (new_tech.strip(),))
                        st.success(f"Dodano technika: {new_tech.strip()}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Taki pracownik już istnieje.")

    lekarze = get_employee_names_by_role("lekarz")
    technicy = get_employee_names_by_role("technik")
    if not lekarze or not technicy:
        st.info("Brakuje aktywnych pracowników. Dodaj ich wyżej lub w zakładce **Pracownicy (admin)**.")

    with st.form("raport_form"):
        d = st.date_input("Data", value=date.today())
        shift = st.selectbox("Zmiana", ["poranna", "popołudniowa"])
        staff_vet = st.selectbox("Lekarz na zmianie", lekarze or ["— brak —"])
        staff_tech_list = st.multiselect("Technik(-cy) na zmianie", technicy, default=(technicy[:1] if technicy else []))
        kasa = st.number_input("Kasa [PLN]", min_value=0.0, step=0.01)
        terminal = st.number_input("Terminal [PLN]", min_value=0.0, step=0.01)
        uwagi = st.text_input("Uwagi (opcjonalnie)")
        ok = st.form_submit_button("💾 Zapisz do bazy")

    if ok:
        if staff_vet in (None, "", "— brak —") or not staff_tech_list:
            st.error("Uzupełnij lekarza i co najmniej jednego technika.")
        else:
            try:
                with cnx() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """INSERT INTO daily_reports
                           (report_date, shift, staff_vet, staff_tech, kasa, terminal, uwagi)
                           VALUES (?,?,?,?,?,?,?)""",
                        (d.isoformat(), shift, staff_vet, ", ".join(staff_tech_list), kasa, terminal, uwagi),
                    )
                    report_id = cur.lastrowid
                    for tech in staff_tech_list:
                        cur.execute("INSERT INTO daily_report_techs (daily_report_id, tech_name) VALUES (?,?)",
                                    (report_id, tech))
                    conn.commit()
                st.success("Zapisano raport i przypisano techników.")
            except sqlite3.Error as e:
                st.error(f"Błąd SQL: {e}")

    st.subheader("Ostatnie wpisy")
    try:
        df = pd.read_sql_query(
            """
            SELECT
              r.id,
              r.report_date,
              r.shift,
              r.staff_vet,
              COALESCE((
                 SELECT GROUP_CONCAT(t.tech_name, ', ')
                 FROM daily_report_techs t
                 WHERE t.daily_report_id = r.id
              ), '') AS staff_tech,
              r.kasa, r.terminal, r.uwagi
            FROM daily_reports r
            ORDER BY r.id DESC
            LIMIT 10
            """,
            cnx(),
        )
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning(f"Nie udało się pobrać danych: {e}")

    # Usuwanie (ADMIN)
    u = st.session_state.get("user", {})
    if u.get("role") == "admin":
        st.subheader("🗑️ Usuń raport (ADMIN)")
        cA, cB = st.columns(2)
        with cA:
            d_from = st.date_input("Od dnia", value=date.today() - timedelta(days=30), key="del_from")
        with cB:
            d_to   = st.date_input("Do dnia", value=date.today(), key="del_to")

        try:
            df_del = pd.read_sql_query(
                """
                SELECT
                  r.id, r.report_date, r.shift, r.staff_vet,
                  COALESCE((SELECT GROUP_CONCAT(t.tech_name, ', ') FROM daily_report_techs t
                            WHERE t.daily_report_id = r.id), '') AS techs,
                  (r.kasa + r.terminal) AS razem
                FROM daily_reports r
                WHERE date(r.report_date) BETWEEN ? AND ?
                ORDER BY r.report_date DESC, r.id DESC
                LIMIT 200
                """,
                cnx(),
                params=(d_from.isoformat(), d_to.isoformat()),
            )
        except Exception as e:
            st.warning(f"Nie udało się pobrać listy do usunięcia: {e}")
            df_del = pd.DataFrame()

        if df_del.empty:
            st.info("Brak raportów w podanym zakresie.")
        else:
            options = {
                f"#{row.id} | {row.report_date} {row.shift} | Lekarz: {row.staff_vet} | Tech: {row.techs} | {row.razem:.2f} zł":
                int(row.id)
                for row in df_del.itertuples(index=False)
            }
            chosen = st.selectbox("Wybierz raport do usunięcia", list(options.keys()))
            sure = st.checkbox("Tak, potwierdzam trwałe usunięcie")
            if st.button("🗑️ Usuń wybrany raport") and sure:
                try:
                    with cnx() as conn:
                        conn.execute("DELETE FROM daily_reports WHERE id=?", (options[chosen],))
                        conn.commit()
                    st.success("Raport usunięty.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Nie udało się usunąć: {e}")

# ------------------ UI: FAKTURY (AP) --------------
def page_faktury_kosztowe():
    st.header("📥 Faktury kosztowe (AP)")

    tab_add, tab_list = st.tabs(["➕ Dodaj fakturę", "📋 Lista / Płatności / Usuwanie"])

    with tab_add:
        with st.form("ap_add_form"):
            col1, col2 = st.columns(2)
            with col1:
                inv_date = st.date_input("Data faktury", value=date.today())
                due_date = st.date_input("Termin płatności", value=date.today())
                supplier = st.text_input("Dostawca / Kontrahent")
                number = st.text_input("Nr faktury (opcjonalnie)")
            with col2:
                category = st.selectbox("Kategoria", ["Bayleg", "Leki inne", "Sprzęt", "Media", "Usługi", "Paliwo", "Inne"])
                amount = st.number_input("Kwota brutto [PLN]", min_value=0.0, step=0.01)
                notes = st.text_input("Uwagi (opcjonalnie)")
            ok = st.form_submit_button("💾 Dodaj fakturę")

        if ok:
            if not supplier or amount <= 0:
                st.error("Wymagane: Dostawca oraz kwota > 0.")
            else:
                try:
                    with cnx() as conn:
                        conn.execute(
                            """INSERT INTO ap_invoices
                               (invoice_date, due_date, supplier, number, category, amount, notes, paid)
                               VALUES (?,?,?,?,?,?,?,0)""",
                            (inv_date.isoformat(), due_date.isoformat(), supplier, number, category, amount, notes),
                        )
                    st.success("Faktura dodana.")
                except sqlite3.Error as e:
                    st.error(f"Błąd SQL: {e}")

    with tab_list:
        only_unpaid = st.checkbox("Pokaż tylko niezapłacone", value=True)
        order_by_due = st.checkbox("Sortuj po terminie płatności (rosnąco)", value=True)

        where = "WHERE paid=0" if only_unpaid else ""
        order = "ORDER BY due_date ASC" if order_by_due else "ORDER BY id DESC"

        try:
            df = pd.read_sql_query(
                f"""SELECT id, invoice_date, due_date, supplier, number, category, amount, paid, paid_date, notes
                    FROM ap_invoices {where} {order}""",
                cnx(),
            )
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.warning(f"Nie udało się pobrać listy: {e}")
            df = pd.DataFrame()

        # ADMIN – płatności i usuwanie
        u = st.session_state.get("user", {})
        if u.get("role") == "admin":
            st.subheader("✅ Oznacz jako opłaconą")
            try:
                df_unpaid = pd.read_sql_query(
                    "SELECT id, supplier, number, amount, due_date FROM ap_invoices WHERE paid=0 ORDER BY due_date ASC",
                    cnx(),
                )
            except Exception as e:
                st.warning(f"Nie udało się pobrać niezapłaconych: {e}")
                df_unpaid = pd.DataFrame()

            if not df_unpaid.empty:
                options_pay = {
                    f"#{row.id} | {row.supplier} | {row.number or '—'} | {row.amount:.2f} PLN | termin: {row.due_date}": int(row.id)
                    for row in df_unpaid.itertuples(index=False)
                }
                sel_pay = st.selectbox("Wybierz fakturę do oznaczenia", list(options_pay.keys()), key="pay_sel")
                if st.button("💸 Oznacz jako opłaconą (dzisiaj)"):
                    try:
                        with cnx() as conn:
                            conn.execute(
                                "UPDATE ap_invoices SET paid=1, paid_date=? WHERE id=?",
                                (date.today().isoformat(), options_pay[sel_pay]),
                            )
                        st.success("Oznaczono jako opłaconą.")
                        st.rerun()
                    except sqlite3.Error as e:
                        st.error(f"Błąd SQL: {e}")

            st.subheader("🗑️ Usuń fakturę (ADMIN)")
            try:
                df_all = pd.read_sql_query(
                    "SELECT id, supplier, number, amount, due_date, paid FROM ap_invoices ORDER BY id DESC",
                    cnx(),
                )
            except Exception as e:
                st.warning(f"Nie udało się pobrać faktur: {e}")
                df_all = pd.DataFrame()

            if not df_all.empty:
                options_del = {
                    f"#{row.id} | {row.supplier} | {row.number or '—'} | {row.amount:.2f} PLN | termin: {row.due_date} | {'opłacona' if row.paid else 'NIE'}":
                    int(row.id)
                    for row in df_all.itertuples(index=False)
                }
                sel_del = st.selectbox("Wybierz fakturę do usunięcia", list(options_del.keys()), key="del_sel")
                sure = st.checkbox("Tak, potwierdzam usunięcie tej faktury")
                if st.button("🗑️ Usuń fakturę") and sure:
                    try:
                        with cnx() as conn:
                            conn.execute("DELETE FROM ap_invoices WHERE id=?", (options_del[sel_del],))
                        st.success("Faktura usunięta.")
                        st.rerun()
                    except sqlite3.Error as e:
                        st.error(f"Błąd SQL: {e}")

# ------------------ UI: AR (pełen obieg) ----------
def page_ar():
    st.header(" Faktury przychodowe (AR) – wystawione / nieopłacone / opłacone")

    tab_add, tab_filter, tab_age, tab_admin = st.tabs([
        "➕ Dodaj fakturę",
        "📋 Lista i filtry",
        "⏳ Wiekowanie należności",
        "🗑️ Administracja"
    ])

    # --- Dodawanie ---
    with tab_add:
        st.caption("Możesz dodać fakturę wystawioną (domyślnie nieopłacona) albo już opłaconą.")
        with st.form("ar_add_form"):
            col1, col2 = st.columns(2)
            with col1:
                issue_date = st.date_input("Data wystawienia", value=date.today())
                due_date   = st.date_input("Termin płatności", value=date.today())
                company    = st.text_input("Nabywca / Firma")
                number     = st.text_input("Nr faktury (opcjonalnie)")
            with col2:
                category   = st.selectbox("Kategoria", ["Usługi gabinet", "Usługi teren", "Sprzedaż detaliczna", "Inne"])
                amount     = st.number_input("Kwota brutto [PLN]", min_value=0.0, step=0.01)
                notes      = st.text_input("Uwagi (opcjonalnie)")
                mark_paid  = st.checkbox("Już opłacona?")
                paid_date  = st.date_input("Data zapłaty", value=date.today(), disabled=not mark_paid)
            ok = st.form_submit_button("💾 Dodaj fakturę")

        if ok:
            if not company or amount <= 0:
                st.error("Wymagane: Nabywca i kwota > 0.")
            else:
                try:
                    with cnx() as conn:
                        conn.execute(
                            """INSERT INTO ar_invoices
                               (issue_date, due_date, company, number, category, amount, notes, paid, paid_date)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (issue_date.isoformat(), due_date.isoformat(), company, number, category, amount, notes,
                             int(mark_paid), (paid_date.isoformat() if mark_paid else None)),
                        )
                    st.success("Faktura AR dodana.")
                except sqlite3.Error as e:
                    st.error(f"Błąd SQL: {e}")

    # --- Lista i filtry ---
    with tab_filter:
        st.subheader("Filtry")
        c1, c2, c3 = st.columns(3)
        with c1:
            status = st.selectbox("Status", ["Wszystkie", "Tylko nieopłacone", "Tylko opłacone"])
        with c2:
            date_mode = st.selectbox("Filtruj wg daty", ["Data wystawienia", "Data zapłaty (tylko opłacone)"])
        with c3:
            cat = st.selectbox("Kategoria (opcjonalnie)", ["(wszystkie)", "Usługi gabinet", "Usługi teren", "Sprzedaż detaliczna", "Inne"])

        cd1, cd2 = st.columns(2)
        with cd1:
            dt_from = st.date_input("Od", value=date.today().replace(day=1))
        with cd2:
            dt_to   = st.date_input("Do", value=date.today())

        company_q = st.text_input("Szukaj po firmie / numerze (opcjonalnie)")

        # budowa WHERE
        where = []
        params = []
        if status == "Tylko nieopłacone":
            where.append("paid=0")
        elif status == "Tylko opłacone":
            where.append("paid=1")

        if date_mode == "Data wystawienia":
            where.append("date(issue_date) BETWEEN ? AND ?")
        else:
            where.append("paid=1")
            where.append("date(paid_date) BETWEEN ? AND ?")
        params.extend([dt_from.isoformat(), dt_to.isoformat()])

        if cat != "(wszystkie)":
            where.append("category=?")
            params.append(cat)

        if company_q.strip():
            where.append("(company LIKE ? OR IFNULL(number,'') LIKE ?)")
            like = f"%{company_q.strip()}%"
            params.extend([like, like])

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        order_sql = "ORDER BY (CASE WHEN paid=1 THEN date(paid_date) ELSE date(issue_date) END) DESC, id DESC"

        try:
            df = pd.read_sql_query(
                f"""SELECT id, issue_date, due_date, company, number, category, amount, paid, paid_date, notes
                    FROM ar_invoices
                    {where_sql}
                    {order_sql}""",
                cnx(),
                params=params,
            )
            st.dataframe(df, use_container_width=True)
            st.download_button("⬇️ Eksport CSV", df.to_csv(index=False).encode("utf-8"), "AR_faktury.csv", "text/csv")
        except Exception as e:
            st.warning(f"Nie udało się pobrać listy: {e}")
            df = pd.DataFrame()

        # Akcje: oznacz/odznacz płatność
        if not df.empty:
            st.subheader("Akcje")
            options = {
                f"#{row.id} | {row.company} | {row.number or '—'} | {row.amount:.2f} PLN | "
                f"{'opłacona' if row.paid else 'NIE'} | wyst: {row.issue_date} | termin: {row.due_date} | zapł: {row.paid_date or '—'}"
                : int(row.id)
                for row in df.itertuples(index=False)
            }
            selected = st.selectbox("Wybierz fakturę", list(options.keys()))

            cA, cB = st.columns(2)
            with cA:
                pd_dt = st.date_input("Data zapłaty", value=date.today(), key="ar_paid_dt")
                if st.button("💸 Oznacz jako opłaconą"):
                    try:
                        with cnx() as conn:
                            conn.execute("UPDATE ar_invoices SET paid=1, paid_date=? WHERE id=?", (pd_dt.isoformat(), options[selected]))
                        st.success("Oznaczono jako opłaconą.")
                        st.rerun()
                    except sqlite3.Error as e:
                        st.error(f"Błąd SQL: {e}")
            with cB:
                # odznacz – tylko admin
                u = st.session_state.get("user", {})
                if u.get("role") == "admin":
                    if st.button("↩️ Cofnij płatność (ADMIN)"):
                        try:
                            with cnx() as conn:
                                conn.execute("UPDATE ar_invoices SET paid=0, paid_date=NULL WHERE id=?", (options[selected],))
                            st.success("Cofnięto oznaczenie płatności.")
                            st.rerun()
                        except sqlite3.Error as e:
                            st.error(f"Błąd SQL: {e}")

    # --- Wiekowanie (aging) ---
    with tab_age:
        st.caption("Wiekowanie liczone po **terminie płatności** dla **nieopłaconych** na dziś.")
        today = date.today().isoformat()
        df_age = pd.read_sql_query(
            """
            SELECT id, company, number, amount, due_date,
                   CAST(julianday(?) - julianday(due_date) AS INTEGER) AS days_past_due
            FROM ar_invoices
            WHERE paid=0
            ORDER BY due_date ASC
            """,
            cnx(),
            params=(today,),
        )
        if df_age.empty:
            st.success("Brak nieopłaconych faktur AR.")
        else:
            # kubełki
            def bucket(d):
                if d <= 0: return "0–30"
                if d <= 30: return "0–30"
                if d <= 60: return "31–60"
                if d <= 90: return "61–90"
                return "90+"
            df_age["bucket"] = df_age["days_past_due"].apply(bucket)
            pivot = df_age.groupby("bucket")["amount"].sum().reindex(["0–30", "31–60", "61–90", "90+"], fill_value=0).reset_index()
            st.subheader("Suma zaległości wg kubełków")
            st.dataframe(pivot, use_container_width=True)
            st.bar_chart(pivot.set_index("bucket"))

            st.subheader("Lista nieopłaconych (szczegóły)")
            st.dataframe(df_age, use_container_width=True)

    # --- Administracja (usuń) ---
    with tab_admin:
        u = st.session_state.get("user", {})
        if u.get("role") != "admin":
            st.error("Brak uprawnień do administracji.")
        else:
            df_all = pd.read_sql_query(
                "SELECT id, issue_date, due_date, company, number, amount, paid, paid_date FROM ar_invoices ORDER BY id DESC LIMIT 200",
                cnx(),
            )
            if df_all.empty:
                st.info("Brak faktur do usunięcia.")
            else:
                opts = {
                    f"#{row.id} | {row.company} | {row.number or '—'} | {row.amount:.2f} | wyst: {row.issue_date} | termin: {row.due_date} | {'opłacona' if row.paid else 'NIE'}"
                    : int(row.id)
                    for row in df_all.itertuples(index=False)
                }
                sel = st.selectbox("Wybierz fakturę do usunięcia", list(opts.keys()))
                sure = st.checkbox("Tak, potwierdzam trwałe usunięcie")
                if st.button("🗑️ Usuń fakturę") and sure:
                    try:
                        with cnx() as conn:
                            conn.execute("DELETE FROM ar_invoices WHERE id=?", (opts[sel],))
                        st.success("Faktura usunięta.")
                        st.rerun()
                    except sqlite3.Error as e:
                        st.error(f"Błąd SQL: {e}")

# ------------------ UI: LEASINGI (ADMIN) ----------
def page_leasingi():
    user = st.session_state.get("user", {})
    if user.get("role") != "admin":
        st.error("Brak uprawnień do sekcji Leasingi.")
        st.stop()

    st.header("🚗 Leasingi (ADMIN)")
    tab_add, tab_list = st.tabs(["➕ Dodaj leasing", "📋 Lista / Usuwanie"])

    with tab_add:
        with st.form("lease_add_form"):
            name = st.text_input("Nazwa / Przedmiot")
            monthly = st.number_input("Rata miesięczna [PLN]", min_value=0.0, step=0.01)
            start = st.date_input("Start umowy", value=date.today())
            end = st.date_input("Koniec umowy", value=date.today())
            notes = st.text_input("Uwagi (opcjonalnie)")
            ok = st.form_submit_button("💾 Dodaj leasing")
        if ok:
            if not name or monthly <= 0:
                st.error("Wymagane: Nazwa i rata miesięczna > 0.")
            else:
                try:
                    with cnx() as conn:
                        conn.execute(
                            """INSERT INTO leasings (name, monthly_amount, start_date, end_date, notes)
                               VALUES (?,?,?,?,?)""",
                            (name, monthly, start.isoformat(), end.isoformat(), notes),
                        )
                    st.success("Leasing dodany.")
                except sqlite3.Error as e:
                    st.error(f"Błąd SQL: {e}")

    with tab_list:
        try:
            df = pd.read_sql_query(
                "SELECT id, name, monthly_amount, start_date, end_date, notes FROM leasings ORDER BY id DESC",
                cnx(),
            )
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.warning(f"Nie udało się wczytać leasingów: {e}")
            df = pd.DataFrame()

        if not df.empty:
            options = {
                f"#{row.id} | {row.name} | {row.monthly_amount:.2f} PLN/m-c | {row.start_date} → {row.end_date}":
                int(row.id)
                for row in df.itertuples(index=False)
            }
            sel = st.selectbox("Wybierz leasing do usunięcia", list(options.keys()))
            sure = st.checkbox("Tak, potwierdzam usunięcie leasingu")
            if st.button("🗑️ Usuń leasing") and sure:
                try:
                    with cnx() as conn:
                        conn.execute("DELETE FROM leasings WHERE id=?", (options[sel],))
                    st.success("Leasing usunięty.")
                    st.rerun()
                except sqlite3.Error as e:
                    st.error(f"Błąd SQL: {e}")
        else:
            st.info("Brak leasingów do usunięcia.")

# ------------------ UI: PRACOWNICY (ADMIN) --------
def page_employees_admin():
    user = st.session_state.get("user", {})
    if user.get("role") != "admin":
        st.error("Brak uprawnień do sekcji Pracownicy.")
        st.stop()

    st.header("👥 Pracownicy (ADMIN)")
    tabs = st.tabs(["➕ Dodaj / edytuj", "📊 Podsumowanie miesiąca"])

    with tabs[0]:
        st.subheader("Dodaj pracownika")
        with st.form("emp_add_form"):
            name = st.text_input("Imię i nazwisko")
            role = st.selectbox("Rola", ["lekarz", "technik"])
            salary = st.number_input("Pensja miesięczna [PLN]", min_value=0.0, step=0.01)
            ok = st.form_submit_button("💾 Dodaj")
        if ok:
            if not name.strip():
                st.error("Podaj imię i nazwisko.")
            else:
                try:
                    with cnx() as conn:
                        conn.execute(
                            "INSERT INTO employees (name, role, monthly_salary, active) VALUES (?,?,?,1)",
                            (name.strip(), role, salary),
                        )
                    st.success("Pracownik dodany.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Taki pracownik już istnieje (unikalna nazwa).")
                except sqlite3.Error as e:
                    st.error(f"Błąd SQL: {e}")

        st.subheader("Lista i edycja")
        df = get_employees_df()
        st.dataframe(df, use_container_width=True)

        with st.form("emp_edit_form"):
            emp_names = df["name"].tolist()
            if emp_names:
                who = st.selectbox("Wybierz pracownika", emp_names)
                new_role = st.selectbox("Rola", ["lekarz", "technik"])
                new_sal = st.number_input("Pensja [PLN]", min_value=0.0, step=0.01, key="emp_sal")
                active = st.checkbox("Aktywny", value=True)
                ok2 = st.form_submit_button("💾 Zapisz zmiany")
                if ok2:
                    try:
                        with cnx() as conn:
                            conn.execute(
                                "UPDATE employees SET role=?, monthly_salary=?, active=? WHERE name=?",
                                (new_role, new_sal, int(active), who),
                            )
                        st.success("Zaktualizowano dane.")
                        st.rerun()
                    except sqlite3.Error as e:
                        st.error(f"Błąd SQL: {e}")
            else:
                st.info("Brak pracowników w bazie.")

        st.subheader("🗑️ Usuń pracownika")
        if not df.empty:
            who_del = st.selectbox("Kto do usunięcia?", df["name"].tolist(), key="emp_del")
            sure = st.checkbox("Tak, rozumiem skutki (usunięcie z listy personelu).")
            if st.button("Usuń pracownika") and sure:
                try:
                    with cnx() as conn:
                        conn.execute("DELETE FROM employees WHERE name=?", (who_del,))
                    st.success("Usunięto pracownika.")
                    st.rerun()
                except sqlite3.Error as e:
                    st.error(f"Błąd SQL: {e}")

    with tabs[1]:
        st.subheader("Podsumowanie miesięczne (utarg przypisany do zmian)")
        year = st.number_input("Rok", value=date.today().year, step=1, format="%d")
        month = st.number_input("Miesiąc", min_value=1, max_value=12, value=date.today().month, step=1)
        ym = f"{int(year)}-{int(month):02}"

        try:
            stats = pd.read_sql_query(
                """
                WITH vet_shifts AS (
                    SELECT staff_vet AS staff, (kasa+terminal) AS rev
                    FROM daily_reports
                    WHERE strftime('%Y-%m', report_date)=?
                ),
                tech_shifts AS (
                    SELECT t.tech_name AS staff, (r.kasa+r.terminal) AS rev
                    FROM daily_reports r
                    JOIN daily_report_techs t ON t.daily_report_id = r.id
                    WHERE strftime('%Y-%m', r.report_date)=?
                )
                SELECT staff AS name,
                       COUNT(*) AS shifts_count,
                       SUM(rev) AS revenue_on_shifts
                FROM (
                    SELECT * FROM vet_shifts
                    UNION ALL
                    SELECT * FROM tech_shifts
                )
                WHERE staff IS NOT NULL AND staff <> ''
                GROUP BY staff
                ORDER BY revenue_on_shifts DESC
                """,
                cnx(),
                params=(ym, ym),
            )
        except Exception as e:
            st.error(f"Nie udało się policzyć statystyk: {e}")
            stats = pd.DataFrame(columns=["name", "shifts_count", "revenue_on_shifts"])

        emp = get_employees_df()[["name", "role", "monthly_salary", "active"]]
        emp = emp[emp["active"] == 1].drop(columns=["active"])
        merged = emp.merge(stats, on="name", how="left").fillna({"shifts_count": 0, "revenue_on_shifts": 0})
        merged = merged.sort_values("revenue_on_shifts", ascending=False)

        st.dataframe(merged, use_container_width=True)
        if not merged.empty:
            st.metric("Najwyższy utarg (miesiąc)",
                      f"{merged.iloc[0]['revenue_on_shifts']:,.2f} zł",
                      help=merged.iloc[0]["name"])
            st.bar_chart(merged.set_index("name")[["revenue_on_shifts"]])

# ------------------ UI: SKLEP ---------------------
def page_shop():
    st.header("🛒 Sklep")
    tab_utarg, tab_zakup = st.tabs(["Utarg dzienny", "Faktury zakupowe"])

    with tab_utarg:
        with st.form("shop_sales_form"):
            sdt = st.date_input("Data utargu", value=date.today())
            sk  = st.number_input("Kasa (PLN)", min_value=0.0, step=0.01, key="ssk")
            stt = st.number_input("Terminal (PLN)", min_value=0.0, step=0.01, key="sst")
            ok = st.form_submit_button("💾 Zapisz utarg")
        if ok:
            try:
                with cnx() as conn:
                    conn.execute("INSERT INTO shop_sales (sale_date, kasa, terminal) VALUES (?,?,?)",
                                 (sdt.isoformat(), sk, stt))
                st.success("Utarg zapisany")
            except sqlite3.Error as e:
                st.error(f"Błąd SQL: {e}")

        try:
            df_sales = pd.read_sql_query(
                "SELECT id, sale_date, kasa, terminal, (kasa+terminal) AS razem FROM shop_sales ORDER BY sale_date DESC, id DESC LIMIT 10",
                cnx(),
            )
            st.dataframe(df_sales, use_container_width=True)
        except Exception as e:
            st.warning(f"Nie udało się pobrać utargów: {e}")

    with tab_zakup:
        with st.form("shop_exp_form"):
            zdt = st.date_input("Data faktury", value=date.today(), key="zdt")
            zam = st.number_input("Kwota", min_value=0.0, step=0.01, key="zam")
            znr = st.text_input("Nr faktury", key="znr")
            zsup= st.text_input("Dostawca", key="zsup")
            zpa = st.checkbox("Zapłacona?", key="zpa")
            ok2 = st.form_submit_button("💾 Dodaj fakturę zakupu")
        if ok2:
            try:
                with cnx() as conn:
                    conn.execute(
                        "INSERT INTO shop_expenses (expense_date, amount, invoice_number, supplier, paid) VALUES (?,?,?,?,?)",
                        (zdt.isoformat(), zam, znr, zsup, int(zpa)),
                    )
                st.success("Faktura dodana")
            except sqlite3.Error as e:
                st.error(f"Błąd SQL: {e}")

        try:
            df_ex = pd.read_sql_query(
                "SELECT id, expense_date, supplier, invoice_number, amount, paid FROM shop_expenses ORDER BY expense_date DESC, id DESC LIMIT 10",
                cnx(),
            )
            st.dataframe(df_ex, use_container_width=True)
        except Exception as e:
            st.warning(f"Nie udało się pobrać faktur sklepu: {e}")

# ------------------ UI: ZWIERZĘTA -----------------
def page_farm():
    st.header("🐄 Zwierzęta hodowlane")

    tab_mag, tab_ter, tab_pod = st.tabs(["Magazyn", "Teren", "Podsumowanie (miesiąc)"])

    # Wpisy: magazyn
    with tab_mag:
        with st.form("farm_mag_form"):
            d = st.date_input("Data (magazyn)", value=date.today())
            kw = st.number_input("Kwota (PLN) – magazyn", min_value=0.0, step=0.01)
            uw = st.text_input("Uwagi (opcjonalnie)")
            ok = st.form_submit_button("💾 Dodaj wpis (magazyn)")
        if ok:
            with cnx() as conn:
                conn.execute("INSERT INTO farm_reports (report_date, typ, kwota, uwagi) VALUES (?,?,?,?)",
                             (d.isoformat(), "magazyn", kw, uw))
            st.success("Dodano wpis magazynowy.")
        dfm = pd.read_sql_query(
            "SELECT id, report_date, kwota, uwagi FROM farm_reports WHERE typ='magazyn' ORDER BY report_date DESC, id DESC LIMIT 20",
            cnx()
        )
        st.dataframe(dfm, use_container_width=True)

    # Wpisy: teren
    with tab_ter:
        with st.form("farm_ter_form"):
            d = st.date_input("Data (teren)", value=date.today(), key="farm_d2")
            kw = st.number_input("Kwota (PLN) – teren", min_value=0.0, step=0.01, key="farm_kw2")
            uw = st.text_input("Uwagi (opcjonalnie)", key="farm_uw2")
            ok = st.form_submit_button("💾 Dodaj wpis (teren)")
        if ok:
            with cnx() as conn:
                conn.execute("INSERT INTO farm_reports (report_date, typ, kwota, uwagi) VALUES (?,?,?,?)",
                             (d.isoformat(), "teren", kw, uw))
            st.success("Dodano wpis terenowy.")
        dft = pd.read_sql_query(
            "SELECT id, report_date, kwota, uwagi FROM farm_reports WHERE typ='teren' ORDER BY report_date DESC, id DESC LIMIT 20",
            cnx()
        )
        st.dataframe(dft, use_container_width=True)

    # Podsumowanie (miesiąc)
    with tab_pod:
        y = st.number_input("Rok", value=date.today().year, step=1, format="%d", key="farm_y")
        m = st.number_input("Miesiąc", min_value=1, max_value=12, value=date.today().month, step=1, key="farm_m")
        first, last = ym_bounds(int(y), int(m))
        df_sum = pd.read_sql_query(
            """
            SELECT typ, SUM(kwota) AS suma
            FROM farm_reports
            WHERE date(report_date) BETWEEN ? AND ?
            GROUP BY typ
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )
        st.dataframe(df_sum, use_container_width=True)
        total = float(df_sum["suma"].sum() if not df_sum.empty else 0.0)
        st.metric("Suma (miesiąc, magazyn+teren)", f"{total:,.2f} zł")

# ------------------ UI: PODSUMOWANIE --------------
def page_summary_admin():
    st.header("📊 Podsumowanie (admin)")

    tabs = st.tabs(["📅 Miesiąc", "📈 Trend 12 mies.", "⏰ Do zapłaty (najbliższe)", "🛒 Sklep", "🐄 Zwierzęta"])

    # Miesiąc
    with tabs[0]:
        y = st.number_input("Rok", value=date.today().year, step=1, format="%d")
        m = st.number_input("Miesiąc", min_value=1, max_value=12, value=date.today().month)
        first, last = ym_bounds(int(y), int(m))

        # Przychody dzienne (Recepcja)
        df_rev_day = pd.read_sql_query(
            """
            SELECT date(report_date) AS d, SUM(kasa+terminal) AS revenue
            FROM daily_reports
            WHERE date(report_date) BETWEEN ? AND ?
            GROUP BY date(report_date)
            ORDER BY d
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )

        # AP (koszty) – zapłacone dziennie
        df_ap_day = pd.read_sql_query(
            """
            SELECT date(paid_date) AS d, SUM(amount) AS ap_paid
            FROM ap_invoices
            WHERE paid=1 AND date(paid_date) BETWEEN ? AND ?
            GROUP BY date(paid_date)
            ORDER BY d
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )

        # AR (przychody) – opłacone dziennie
        df_ar_day = pd.read_sql_query(
            """
            SELECT date(paid_date) AS d, SUM(amount) AS ar_paid
            FROM ar_invoices
            WHERE paid=1 AND date(paid_date) BETWEEN ? AND ?
            GROUP BY date(paid_date)
            ORDER BY d
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )

        chart = pd.DataFrame({"d": pd.date_range(first, last)})
        chart["d"] = chart["d"].dt.date
        chart = (chart
                 .merge(df_rev_day, on="d", how="left")
                 .merge(df_ap_day, on="d", how="left")
                 .merge(df_ar_day, on="d", how="left")
                 .fillna(0.0)
                 .set_index("d"))
        st.subheader("Przychody gabinet + AR (opłacone) vs. AP (koszty, zapłacone)")
        st.line_chart(chart[["revenue", "ar_paid", "ap_paid"]])

        # KPI
        sum_revenue_gp = float(chart["revenue"].sum())
        sum_ap_paid    = float(chart["ap_paid"].sum())
        sum_ar_paid    = float(chart["ar_paid"].sum())
        sum_leasing    = sum_leasing_for_month(int(y), int(m))
        sum_salaries   = sum_salaries_active()
        net = (sum_revenue_gp + sum_ar_paid) - (sum_ap_paid + sum_leasing + sum_salaries)

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Przychody (gabinet)", f"{sum_revenue_gp:,.2f} zł")
        c2.metric("Przychody z faktur (AR opłacone)", f"{sum_ar_paid:,.2f} zł")
        c3.metric("AP zapłacone (koszty)", f"{sum_ap_paid:,.2f} zł")
        c4.metric("Leasingi (mies.)", f"{sum_leasing:,.2f} zł")
        c5.metric("Wynagrodzenia (mies.)", f"{sum_salaries:,.2f} zł")
        c6.metric("Wynik netto", f"{net:,.2f} zł")

    # TREND 12 MIES.
    with tabs[1]:
        today = date.today()
        months = []
        y2, m2 = today.year, today.month
        for _ in range(12):
            months.append(f"{y2}-{m2:02}")
            m2 -= 1
            if m2 == 0:
                m2 = 12
                y2 -= 1
        months = months[::-1]

        df_r = pd.read_sql_query(
            "SELECT strftime('%Y-%m', report_date) AS ym, SUM(kasa+terminal) AS revenue FROM daily_reports GROUP BY ym",
            cnx(),
        )
        rev_map = dict(zip(df_r["ym"], df_r["revenue"]))

        df_ap = pd.read_sql_query(
            "SELECT strftime('%Y-%m', paid_date) AS ym, SUM(amount) AS ap_paid FROM ap_invoices WHERE paid=1 GROUP BY ym",
            cnx(),
        )
        ap_map = dict(zip(df_ap["ym"], df_ap["ap_paid"]))

        df_ar = pd.read_sql_query(
            "SELECT strftime('%Y-%m', paid_date) AS ym, SUM(amount) AS ar_paid FROM ar_invoices WHERE paid=1 GROUP BY ym",
            cnx(),
        )
        ar_map = dict(zip(df_ar["ym"], df_ar["ar_paid"]))

        salaries_monthly = sum_salaries_active()
        lease_list = []
        for ym in months:
            yy, mm = map(int, ym.split("-"))
            lease_list.append(sum_leasing_for_month(yy, mm))

        df12 = pd.DataFrame({
            "ym": months,
            "Przychody_gabinet": [float(rev_map.get(ym, 0.0) or 0.0) for ym in months],
            "AR_oplacone":       [float(ar_map.get(ym, 0.0) or 0.0) for ym in months],
            "AP_zaplacone":      [float(ap_map.get(ym, 0.0) or 0.0) for ym in months],
            "Leasingi":          lease_list,
            "Wynagrodzenia":     [salaries_monthly]*len(months),
        }).set_index("ym")
        df12["Przychody_razem"] = df12["Przychody_gabinet"] + df12["AR_oplacone"]
        df12["Koszty_razem"]    = df12[["AP_zaplacone", "Leasingi", "Wynagrodzenia"]].sum(axis=1)
        df12["Wynik_netto"]     = df12["Przychody_razem"] - df12["Koszty_razem"]

        st.subheader("Przychody (gabinet+AR) vs koszty (12 mies.)")
        st.line_chart(df12[["Przychody_razem", "Koszty_razem"]])
        st.subheader("Wynik netto (12 mies.)")
        st.bar_chart(df12[["Wynik_netto"]])
        st.dataframe(df12, use_container_width=True)

    # Do zapłaty (najbliższe) – AP
    with tabs[2]:
        days = st.slider("Pokaż zobowiązania AP na najbliższe (dni)", min_value=7, max_value=60, value=14, step=1)
        today_str = date.today().isoformat()
        future_str = (pd.Timestamp.today() + pd.Timedelta(days=days)).date().isoformat()
        df_due = pd.read_sql_query(
            """
            SELECT id, supplier, number, amount, due_date
            FROM ap_invoices
            WHERE paid=0 AND date(due_date) BETWEEN ? AND ?
            ORDER BY due_date ASC
            """,
            cnx(),
            params=(today_str, future_str),
        )
        if df_due.empty:
            st.success("Brak zobowiązań AP w wybranym horyzoncie.")
        else:
            st.dataframe(df_due, use_container_width=True)

    # Sklep – skrót
    with tabs[3]:
        y = st.number_input("Rok (sklep)", value=date.today().year, step=1, format="%d", key="shop_y")
        m = st.number_input("Miesiąc (sklep)", min_value=1, max_value=12, value=date.today().month, key="shop_m")
        first, last = ym_bounds(int(y), int(m))

        df_shop_rev = pd.read_sql_query(
            """
            SELECT date(sale_date) AS d, SUM(kasa+terminal) AS sales
            FROM shop_sales
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY date(sale_date)
            ORDER BY d
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )
        sum_shop_sales = float(df_shop_rev["sales"].sum()) if not df_shop_rev.empty else 0.0

        df_shop_paid = pd.read_sql_query(
            """
            SELECT date(expense_date) AS d, SUM(amount) AS shop_paid
            FROM shop_expenses
            WHERE paid=1 AND date(expense_date) BETWEEN ? AND ?
            GROUP BY date(expense_date)
            ORDER BY d
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )
        sum_shop_paid = float(df_shop_paid["shop_paid"].sum()) if not df_shop_paid.empty else 0.0

        chart = pd.DataFrame({"d": pd.date_range(first, last)})
        chart["d"] = chart["d"].dt.date
        chart = chart.merge(df_shop_rev, on="d", how="left").merge(df_shop_paid, on="d", how="left").fillna(0.0)
        chart = chart.set_index("d")
        st.subheader("Sklep: utargi i zapłacone wydatki (dziennie)")
        st.line_chart(chart[["sales", "shop_paid"]])

        c1, c2 = st.columns(2)
        c1.metric("Suma utargów (sklep)", f"{sum_shop_sales:,.2f} zł")
        c2.metric("Suma zapłaconych wydatków (sklep)", f"{sum_shop_paid:,.2f} zł")

    # Zwierzęta – skrót
    with tabs[4]:
        y = st.number_input("Rok (zwierzęta)", value=date.today().year, step=1, format="%d", key="farm_y2")
        m = st.number_input("Miesiąc (zwierzęta)", min_value=1, max_value=12, value=date.today().month, step=1, key="farm_m2")
        first, last = ym_bounds(int(y), int(m))
        df_sum = pd.read_sql_query(
            """
            SELECT typ, SUM(kwota) AS suma
            FROM farm_reports
            WHERE date(report_date) BETWEEN ? AND ?
            GROUP BY typ
            """,
            cnx(),
            params=(first.isoformat(), last.isoformat()),
        )
        st.dataframe(df_sum, use_container_width=True)
        total = float(df_sum["suma"].sum() if not df_sum.empty else 0.0)
        st.metric("Suma (miesiąc, magazyn+teren)", f"{total:,.2f} zł")

# ------------------ LOGOWANIE ---------------------
def login_box():
    st.title("🔐 Logowanie")
    with st.form("login_form"):
        u = st.text_input("Login")
        p = st.text_input("Hasło", type="password")
        ok = st.form_submit_button("Zaloguj")
    if ok:
        user = USERS.get(u)
        if not user or p != user["password"]:
            st.error("Nieprawidłowy login lub hasło.")
            return
        st.session_state.user = {"username": u, "full_name": user["full_name"], "role": user["role"]}
        st.rerun()

def user_topbar():
    with st.sidebar:
        u = st.session_state.get("user")
        if u:
            st.success(f"Zalogowano: {u['full_name']} ({u['role']})")
            if st.button("Wyloguj"):
                st.session_state.pop("user")
                st.rerun()

# ------------------ MAIN -------------------------
def main():
    st.set_page_config(page_title="VetFinance", layout="wide", page_icon="🐾")
    init_db()

    if "user" not in st.session_state:
        login_box()
        return

    user_topbar()
    role = st.session_state["user"]["role"]

    pages = {
        "Recepcja": page_recepcja,
        "Faktury kosztowe (AP)": page_faktury_kosztowe,
        "Faktury przychodowe (AR)": page_ar,         
        "Sklep": page_shop,
        "Zwierzęta": page_farm,
    }
    if role == "admin":
        pages["Leasingi"] = page_leasingi
        pages["Pracownicy (admin)"] = page_employees_admin
        pages["Podsumowanie (admin)"] = page_summary_admin

    choice = st.sidebar.radio("Nawigacja", list(pages.keys()))
    pages[choice]()

if __name__ == "__main__":
    main()
