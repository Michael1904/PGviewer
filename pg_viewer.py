"""
Лабораторна робота №5. Реалізація інтерфейсу з PostgreSQL.
Графічний додаток (Tkinter + psycopg2):
  1) введення логіна і пароля та з'єднання з БД;
  2) отримання даних з таблиць БД за вибором користувача.

Запуск:
    pip install psycopg2-binary
    python pg_viewer.py
"""

import csv
import decimal
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:  # підказка, якщо драйвер не встановлено
    tk.Tk().withdraw()
    messagebox.showerror(
        "Немає драйвера",
        "Не знайдено модуль psycopg2.\nВстановіть його командою:\n\npip install psycopg2-binary",
    )
    raise SystemExit(1)


def pg_error_text(err):
    """Повертає зрозумілий текст помилки PostgreSQL."""
    if isinstance(err, UnicodeDecodeError):
        # Сервер на Windows надсилає повідомлення у cp1251, а не в UTF-8
        try:
            raw = err.object.decode("cp1251").strip()
        except Exception:
            raw = ""
        hint = "Невірний логін або пароль, неіснуюча база даних або сервер недоступний."
        return f"{hint}\n\nВідповідь сервера:\n{raw}" if raw else hint
    text = getattr(err, "pgerror", None) or str(err)
    return text.strip() or err.__class__.__name__


def sort_key(value):
    """Ключ сортування: спочатку числа, потім текст, NULL наприкінці."""
    if value is None:
        return (2, "")
    if isinstance(value, (int, float, decimal.Decimal)):
        return (0, value)
    return (1, str(value).lower())


class PgViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PostgreSQL Viewer — ЛР №5")
        self.geometry("1150x680")
        self.minsize(900, 520)

        self.conn = None
        self.conn_info = {}
        self.tables = []          # список кортежів (schema, table, type)
        self.current_table = None
        self.cur_columns = []
        self.cur_rows = []
        self.container = None

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=22)
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_login()

    # ------------------------------------------------------------------
    # Загальне
    # ------------------------------------------------------------------
    def clear_window(self):
        if self.container is not None:
            self.container.destroy()
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

    def on_close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.destroy()

    # ------------------------------------------------------------------
    # Пункт 1. Вікно входу
    # ------------------------------------------------------------------
    def show_login(self):
        self.clear_window()
        self.title("PostgreSQL Viewer — вхід")

        box = ttk.Frame(self.container, padding=30)
        box.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(box, text="З'єднання з базою даних PostgreSQL",
                  style="Title.TLabel").grid(row=0, column=0, columnspan=2, pady=(0, 18))

        self.login_vars = {
            "host": tk.StringVar(value=self.conn_info.get("host", "localhost")),
            "port": tk.StringVar(value=self.conn_info.get("port", "5432")),
            "dbname": tk.StringVar(value=self.conn_info.get("dbname", "base_lb3")),
            "user": tk.StringVar(value=self.conn_info.get("user", "postgres")),
            "password": tk.StringVar(),
        }
        fields = [
            ("Сервер (host):", "host", None),
            ("Порт:", "port", None),
            ("База даних:", "dbname", None),
            ("Логін:", "user", None),
            ("Пароль:", "password", "•"),
        ]
        entries = {}
        for i, (label, key, show) in enumerate(fields, start=1):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="e", padx=(0, 10), pady=4)
            e = ttk.Entry(box, textvariable=self.login_vars[key], width=32, show=show or "")
            e.grid(row=i, column=1, sticky="w", pady=4)
            entries[key] = e

        self.show_pwd = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            box, text="Показати пароль", variable=self.show_pwd,
            command=lambda: entries["password"].configure(show="" if self.show_pwd.get() else "•"),
        ).grid(row=6, column=1, sticky="w", pady=(2, 10))

        ttk.Button(box, text="Підключитися", command=self.connect).grid(
            row=7, column=0, columnspan=2, sticky="ew", ipady=4)

        self.login_status = ttk.Label(box, text="", foreground="#b00020")
        self.login_status.grid(row=8, column=0, columnspan=2, pady=(10, 0))

        self.bind("<Return>", lambda _e: self.connect())
        (entries["password"] if self.conn_info else entries["user"]).focus_set()

    def connect(self):
        params = {k: v.get().strip() for k, v in self.login_vars.items()}
        params["password"] = self.login_vars["password"].get()  # пароль не обрізаємо

        if not params["user"]:
            self.login_status.configure(text="Введіть логін.")
            return
        if not params["port"].isdigit():
            self.login_status.configure(text="Порт має бути числом.")
            return

        self.login_status.configure(text="З'єднання...", foreground="#555555")
        self.update_idletasks()
        try:
            conn = psycopg2.connect(
                host=params["host"], port=int(params["port"]),
                dbname=params["dbname"], user=params["user"],
                password=params["password"], connect_timeout=5,
            )
            conn.autocommit = True   # помилка одного запиту не блокує наступні
        except Exception as err:
            self.login_status.configure(text="Не вдалося з'єднатися.", foreground="#b00020")
            messagebox.showerror("Помилка з'єднання", pg_error_text(err))
            return

        self.conn = conn
        self.conn_info = {k: v for k, v in params.items() if k != "password"}
        self.unbind("<Return>")
        self.show_main()

    def disconnect(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None
        self.current_table = None
        self.show_login()

    # ------------------------------------------------------------------
    # Пункт 2. Головне вікно: вибір таблиці та перегляд даних
    # ------------------------------------------------------------------
    def show_main(self):
        self.clear_window()
        info = self.conn_info
        self.title(f"PostgreSQL Viewer — {info['user']}@{info['host']}:{info['port']}/{info['dbname']}")

        # Верхня панель
        top = ttk.Frame(self.container, padding=(10, 8))
        top.pack(fill="x")
        server_ver = self.conn.server_version
        ver_text = f"{server_ver // 10000}.{server_ver % 10000}" if server_ver >= 100000 else str(server_ver)
        ttk.Label(
            top,
            text=f"Підключено: користувач «{info['user']}», база «{info['dbname']}», "
                 f"сервер {info['host']}:{info['port']} (PostgreSQL {ver_text})",
        ).pack(side="left")
        ttk.Button(top, text="Від'єднатися", command=self.disconnect).pack(side="right")

        paned = ttk.PanedWindow(self.container, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Ліва частина: список таблиць
        left = ttk.Frame(paned, padding=(0, 0, 6, 0))
        ttk.Label(left, text="Таблиці та представлення").pack(anchor="w")
        self.table_search = tk.StringVar()
        self.table_search.trace_add("write", lambda *_: self.fill_table_list())
        ttk.Entry(left, textvariable=self.table_search).pack(fill="x", pady=(4, 4))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.table_list = tk.Listbox(list_frame, exportselection=False, activestyle="none")
        lsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.table_list.yview)
        self.table_list.configure(yscrollcommand=lsb.set)
        self.table_list.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        self.table_list.bind("<<ListboxSelect>>", self.on_table_select)
        ttk.Button(left, text="Оновити список", command=self.load_tables).pack(fill="x", pady=(6, 0))
        paned.add(left, weight=1)

        # Права частина: параметри вибірки і таблиця результатів
        right = ttk.Frame(paned)
        paned.add(right, weight=4)

        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Стовпці:").pack(side="left")
        ttk.Button(bar, text="Вибрати…", command=self.choose_columns).pack(side="left", padx=(4, 12))
        ttk.Label(bar, text="Фільтр за стовпцем:").pack(side="left")
        self.filter_col = ttk.Combobox(bar, state="readonly", width=18)
        self.filter_col.pack(side="left", padx=4)
        self.filter_val = ttk.Entry(bar, width=18)
        self.filter_val.pack(side="left", padx=(0, 12))
        self.filter_val.bind("<Return>", lambda _e: self.load_data())
        ttk.Label(bar, text="Рядків:").pack(side="left")
        self.limit_var = tk.StringVar(value="500")
        ttk.Spinbox(bar, from_=1, to=1_000_000, increment=100, width=8,
                    textvariable=self.limit_var).pack(side="left", padx=(4, 12))
        ttk.Button(bar, text="Показати", command=self.load_data).pack(side="left")
        ttk.Button(bar, text="Експорт у CSV", command=self.export_csv).pack(side="right")

        grid_frame = ttk.Frame(right)
        grid_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(grid_frame, show="headings")
        vsb = ttk.Scrollbar(grid_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(grid_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.columnconfigure(0, weight=1)

        # Довільний SQL-запит
        sql_frame = ttk.LabelFrame(right, text="Довільний SQL-запит (Ctrl+Enter — виконати)", padding=6)
        sql_frame.pack(fill="x", pady=(6, 0))
        self.sql_text = tk.Text(sql_frame, height=3, wrap="word", font=("Consolas", 10))
        self.sql_text.pack(side="left", fill="x", expand=True)
        self.sql_text.bind("<Control-Return>", lambda _e: (self.run_sql(), "break")[1])
        ttk.Button(sql_frame, text="Виконати", command=self.run_sql).pack(side="right", padx=(6, 0), fill="y")

        # Рядок стану
        self.status = ttk.Label(self.container, text="Оберіть таблицю зі списку ліворуч.",
                                relief="sunken", anchor="w", padding=(8, 3))
        self.status.pack(fill="x", side="bottom")

        self.selected_columns = None
        self.all_columns = []
        self.load_tables()

    def set_status(self, text):
        self.status.configure(text=text)

    def execute(self, query, params=None):
        """Виконує запит; повертає (стовпці, рядки) або None у разі помилки."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description is None:
                    return [], [], cur.rowcount
                cols = [d[0] for d in cur.description]
                return cols, cur.fetchall(), cur.rowcount
        except psycopg2.InterfaceError as err:
            messagebox.showerror("З'єднання втрачено", pg_error_text(err))
            self.disconnect()
        except Exception as err:
            messagebox.showerror("Помилка запиту", pg_error_text(err))
            self.set_status("Помилка виконання запиту.")
        return None

    def load_tables(self):
        # information_schema показує лише ті таблиці, до яких поточна роль має права
        result = self.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """
        )
        if result is None:
            return
        _, rows, _ = result
        self.tables = rows
        self.fill_table_list()
        self.set_status(f"Доступно таблиць і представлень: {len(rows)}. Оберіть одну зі списку.")

    def fill_table_list(self):
        mask = self.table_search.get().strip().lower()
        self.table_list.delete(0, "end")
        self.visible_tables = []
        for schema, name, ttype in self.tables:
            label = f"{schema}.{name}" + ("  (view)" if ttype == "VIEW" else "")
            if mask and mask not in label.lower():
                continue
            self.visible_tables.append((schema, name))
            self.table_list.insert("end", label)

    def on_table_select(self, _event=None):
        sel = self.table_list.curselection()
        if not sel:
            return
        schema, name = self.visible_tables[sel[0]]
        result = self.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, name),
        )
        if result is None:
            return
        self.current_table = (schema, name)
        self.all_columns = [r[0] for r in result[1]]
        self.selected_columns = None
        self.filter_col.configure(values=["(без фільтра)"] + self.all_columns)
        self.filter_col.current(0)
        self.filter_val.delete(0, "end")
        self.load_data()

    def choose_columns(self):
        if not self.current_table:
            messagebox.showinfo("Стовпці", "Спочатку оберіть таблицю.")
            return
        win = tk.Toplevel(self)
        win.title("Вибір стовпців")
        win.transient(self)
        win.grab_set()
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        current = set(self.selected_columns or self.all_columns)
        vars_ = []
        for col in self.all_columns:
            v = tk.BooleanVar(value=col in current)
            ttk.Checkbutton(frame, text=col, variable=v).pack(anchor="w")
            vars_.append((col, v))

        def apply():
            chosen = [c for c, v in vars_ if v.get()]
            if not chosen:
                messagebox.showwarning("Стовпці", "Оберіть хоча б один стовпець.", parent=win)
                return
            self.selected_columns = None if len(chosen) == len(self.all_columns) else chosen
            win.destroy()
            self.load_data()

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Усі", command=lambda: [v.set(True) for _, v in vars_]).pack(side="left")
        ttk.Button(btns, text="Жодного", command=lambda: [v.set(False) for _, v in vars_]).pack(side="left", padx=4)
        ttk.Button(btns, text="Застосувати", command=apply).pack(side="right")

    def load_data(self):
        if not self.current_table:
            messagebox.showinfo("Дані", "Спочатку оберіть таблицю зі списку.")
            return
        schema, name = self.current_table
        try:
            limit = int(self.limit_var.get())
            if limit < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Кількість рядків", "Вкажіть додатне ціле число.")
            return

        table_id = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))
        if self.selected_columns:
            cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in self.selected_columns)
        else:
            cols_sql = sql.SQL("*")

        where_sql = sql.SQL("")
        params = []
        fcol = self.filter_col.get()
        fval = self.filter_val.get()
        if fcol and fcol != "(без фільтра)" and fval != "":
            where_sql = sql.SQL(" WHERE {}::text ILIKE %s").format(sql.Identifier(fcol))
            params.append(f"%{fval}%")

        query = sql.SQL("SELECT {} FROM {}{} LIMIT %s").format(cols_sql, table_id, where_sql)
        count_query = sql.SQL("SELECT count(*) FROM {}{}").format(table_id, where_sql)

        result = self.execute(query, params + [limit])
        if result is None:
            return
        cols, rows, _ = result
        self.show_result(cols, rows)

        total = self.execute(count_query, params)
        total_text = f" з {total[1][0][0]}" if total else ""
        flt = f", фільтр: {fcol} містить «{fval}»" if params else ""
        self.set_status(f"Таблиця {schema}.{name}: показано {len(rows)}{total_text} рядків{flt}.")

    def run_sql(self):
        query = self.sql_text.get("1.0", "end").strip()
        if not query:
            return
        result = self.execute(query)
        if result is None:
            return
        cols, rows, rowcount = result
        if cols:
            self.show_result(cols, rows)
            self.set_status(f"Запит виконано, отримано рядків: {len(rows)}.")
        else:
            self.set_status(f"Команду виконано. Оброблено рядків: {rowcount}.")
            self.load_tables()

    def show_result(self, columns, rows):
        self.cur_columns = list(columns)
        self.cur_rows = list(rows)
        ids = [f"c{i}" for i in range(len(columns))]
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=ids)
        for i, (cid, name) in enumerate(zip(ids, columns)):
            sample = [len(str(r[i])) for r in rows[:50] if r[i] is not None]
            width = min(max([len(name)] + sample) * 8 + 20, 320)
            self.tree.heading(cid, text=name, command=lambda j=i: self.sort_by(j, False))
            self.tree.column(cid, width=width, minwidth=50, stretch=False)
        self.fill_tree()

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for n, row in enumerate(self.cur_rows):
            values = ["NULL" if v is None else str(v) for v in row]
            self.tree.insert("", "end", values=values, tags=("odd" if n % 2 else "even",))
        self.tree.tag_configure("odd", background="#f3f6fa")

    def sort_by(self, index, reverse):
        self.cur_rows.sort(key=lambda r: sort_key(r[index]), reverse=reverse)
        self.fill_tree()
        arrow = " ▼" if reverse else " ▲"
        for i, name in enumerate(self.cur_columns):
            self.tree.heading(f"c{i}", text=name + (arrow if i == index else ""),
                              command=lambda j=i: self.sort_by(j, j == index and not reverse))

    def export_csv(self):
        if not self.cur_columns:
            messagebox.showinfo("Експорт", "Немає даних для збереження.")
            return
        default = f"{self.current_table[1]}.csv" if self.current_table else "result.csv"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default,
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(self.cur_columns)
            writer.writerows(["" if v is None else v for v in r] for r in self.cur_rows)
        self.set_status(f"Збережено {len(self.cur_rows)} рядків у файл {path}")


if __name__ == "__main__":
    PgViewerApp().mainloop()