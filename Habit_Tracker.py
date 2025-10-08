from pymongo import MongoClient
import datetime
import schedule
import time
import threading
import json
import os

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from calendar import monthrange
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from PIL import Image, ImageTk, ImageEnhance
import sys
import os

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)




# ---------------- Database Setup ----------------
client = MongoClient("mongodb://localhost:27017/")
db = client["habit_game"]

users_collection = db["users"]
habits_collection = db["habits"]
logs_collection = db["logs"]

# Predefined habits
if habits_collection.count_documents({}) == 0:
    habits = [
        {"habit": "Studied for 2 hours", "type": "good", "points": 18},
        {"habit": "Exercise / Physical Activity", "type": "good", "points": 13},
        {"habit": "Practiced a hobby or skill", "type": "good", "points": 12},
        {"habit": "Stayed hydrated", "type": "good", "points": 12},
        {"habit": "Attended lectures on time", "type": "good", "points": 11},
        {"habit": "Read books or articles", "type": "good", "points": 9},
        {"habit": "Overused social media", "type": "bad", "points": -6},
        {"habit": "Skipped class", "type": "bad", "points": -7},
        {"habit": "Skipped meal", "type": "bad", "points": -9},
        {"habit": "Avoided studying or practicing skills", "type": "bad", "points": -9},
        {"habit": "Getting angry / losing cool", "type": "bad", "points": -10},
        {"habit": "Stayed up late", "type": "bad", "points": -12},
    ]
    habits_collection.insert_many(habits)

# ---------------- Core backend functions ----------------
def create_user(username, password):
    if users_collection.find_one({"username": username}):
        return False
    users_collection.insert_one({
        "username": username,
        "password": password,
        "points": 0,
        "level": 1,
        "streak": 0,
        "last_action_date": None,
        "pin": None,
        "pin_recovery": None
    })
    return True

def login_user(username, password):
    return users_collection.find_one({"username": username, "password": password})

def calculate_level(points):
    return max(1, points // 100 + 1)

def add_habit_log_for_user(username, habit_name):
    habit = habits_collection.find_one({"habit": habit_name})
    if not habit:
        return None
    points = int(habit["points"])
    entry = {
        "user": username,
        "habit": habit_name,
        "points": points,
        # store ISO date for day-based grouping and a precise timestamp for ordering
        "date": datetime.date.today().isoformat(),
        "timestamp": datetime.datetime.utcnow()
    }
    logs_collection.insert_one(entry)

    user = users_collection.find_one({"username": username})
    if not user:
        return None

    today = datetime.date.today()
    last = user.get("last_action_date")
    streak = user.get("streak", 0)

    if last:
        try:
            last_date = datetime.date.fromisoformat(last)
            if today == last_date + datetime.timedelta(days=1):
                streak += 1
            elif today == last_date:
                streak = streak
            else:
                streak = 1
        except:
            streak = 1
    else:
        streak = 1

    new_points = user.get("points", 0) + points
    new_level = calculate_level(new_points)

    users_collection.update_one(
        {"username": username},
        {"$set": {
            "points": new_points,
            "level": new_level,
            "streak": streak,
            "last_action_date": today.isoformat()
        }}
    )
    return points

def undo_last_habit_log(username):
    # Find the most recently inserted log using timestamp (fallback to date ordering)
    last_log = logs_collection.find({"user": username}).sort([("timestamp", -1), ("date", -1)]).limit(1)
    last_log = list(last_log)
    if not last_log:
        return False

    logs_collection.delete_one({"_id": last_log[0]["_id"]})

    # Fetch logs ordered by timestamp ascending so we can recompute streaks in chronological order
    logs = list(logs_collection.find({"user": username}).sort([("timestamp", 1), ("date", 1)]))
    total_points = sum(l.get("points", 0) for l in logs)
    level = calculate_level(total_points)

    streak = 0
    last_date = None
    for l in logs:
        pts = l.get("points", 0)
        try:
            log_date = datetime.date.fromisoformat(l["date"])
        except:
            continue
        if last_date:
            if (log_date - last_date).days == 1 and pts > 0:
                streak += 1
            elif (log_date - last_date).days > 1 and pts > 0:
                streak = 1
            else:
                streak = 0
        else:
            streak = 1 if pts > 0 else 0
        last_date = log_date

    last_action_date = last_date.isoformat() if last_date else None

    users_collection.update_one(
        {"username": username},
        {"$set": {
            "points": total_points,
            "level": level,
            "streak": streak,
            "last_action_date": last_action_date
        }}
    )
    return True

def get_user_stats(username):
    return users_collection.find_one({"username": username})

def get_logs_for_user(username, limit=1000):
    return list(logs_collection.find({"user": username}).sort("date", -1).limit(limit))

def build_habit_list():
    return list(habits_collection.find({}))

# ---------------- Scheduler ----------------
def remind_log(user):
    print(f"🔔 Hey {user}, don’t forget to log your habits today!")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# ---------------- Habit Game App ----------------
class HabitGameApp:
    REMEMBER_FILE = "remember_user.json"


    def start_daily_rollover_check(self):
        """Start a background thread to check when a new day starts."""
        def check_day_change():
            last_checked = datetime.date.today()
            while True:
                today = datetime.date.today()
                if today != last_checked:
                    # Day has changed
                    self.on_new_day(last_checked, today)
                    last_checked = today
                time.sleep(30)  # Check every 30 seconds

        threading.Thread(target=check_day_change, daemon=True).start()

    def on_new_day(self, yesterday, today):
        """Handle the rollover to a new day."""
        # Refresh dashboard so new day is reflected
        self.refresh_dashboard()
        # Optionally: show a notification
        print(f"🌅 New day: {today}. Yesterday's logs saved for {yesterday}.")
        # Optionally, update the monthly calendar immediately
        self.show_monthly_calendar()

    def __init__(self, root):
        self.root = root
        self.root.title("🎮 Habit Game")
        self.root.geometry("900x700")
        self.current_user = None
        self.displayed_year = datetime.date.today().year
        self.displayed_month = datetime.date.today().month
        self.root.iconbitmap(resource_path("resources/logo.ico"))

        self.style = ttk.Style()
        self.style.configure("TLabel", font=("Arial", 11))
        self.style.configure("TButton", font=("Arial", 11))
        self.style.configure("Header.TLabel", font=("Arial", 16, "bold"))

        self.load_remembered_user()
        self.start_daily_rollover_check()


    # ---------- Remember Me ----------
    def save_remembered_user(self, username):
        with open(self.REMEMBER_FILE, "w") as f:
            json.dump({"username": username}, f)

    def load_remembered_user(self):
        if os.path.exists(self.REMEMBER_FILE):
            with open(self.REMEMBER_FILE, "r") as f:
                data = json.load(f)
                user = get_user_stats(data.get("username"))
                if user:
                    self.current_user = user
                    if user.get("pin"):
                        self.show_pin_lock()
                    else:
                        self.show_dashboard()
                    return
        self.show_login_screen()

    def clear_remembered_user(self):
        if os.path.exists(self.REMEMBER_FILE):
            os.remove(self.REMEMBER_FILE)

    # ---------- Login / Signup ----------
    def show_login_screen(self):
        self.clear_screen()

        # Load background image (original)
        try:
            self.original_bg_image = Image.open(resource_path("resources/background.png"))
            enhancer = ImageEnhance.Brightness(self.original_bg_image)
            self.original_bg_image = enhancer.enhance(0.4)  # Darken once
        except Exception as e:
            print("Background image error:", e)
            self.original_bg_image = None

        self.bg_label = tk.Label(self.root)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        if self.original_bg_image:
            self.update_bg_image()  # initial resize
            self.root.bind("<Configure>", lambda e: self.update_bg_image())

        # Container frame on top of background
        container = ttk.Frame(self.root, padding=16)
        container.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(container, text="Habit Game — Login or Sign Up", style="Header.TLabel").pack(pady=(0,12))

        form = ttk.Frame(container)
        form.pack()

        ttk.Label(form, text="Username:").grid(row=0, column=0, sticky="w", pady=6)
        self.username_entry = ttk.Entry(form, width=30)
        self.username_entry.grid(row=0, column=1, pady=6)

        ttk.Label(form, text="Password:").grid(row=1, column=0, sticky="w", pady=6)
        self.password_entry = ttk.Entry(form, width=30, show="*")
        self.password_entry.grid(row=1, column=1, pady=6)

        self.remember_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Remember Me", variable=self.remember_var).grid(row=2, column=1, sticky="w", pady=6)

        btn_frame = ttk.Frame(container)
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="Login", command=self.handle_login).grid(row=0, column=0, padx=6)
        ttk.Button(btn_frame, text="Sign Up", command=self.handle_signup).grid(row=0, column=1, padx=6)
        ttk.Button(btn_frame, text="Quit", command=self.root.quit).grid(row=0, column=2, padx=6)


    def update_bg_image(self):
        if not self.original_bg_image:
            return
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        resized = self.original_bg_image.resize((w, h), Image.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(resized)
        self.bg_label.config(image=self.bg_photo)


    def handle_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Please enter username and password")
            return
        user = login_user(username, password)
        if user:
            self.current_user = user
            if self.remember_var.get():
                self.save_remembered_user(username)
            if user.get("pin"):
                self.show_pin_lock()
            else:
                self.show_dashboard()
        else:
            messagebox.showerror("Error", "Invalid username or password")

    def handle_signup(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Please provide username and password")
            return
        success = create_user(username, password)
        if success:
            messagebox.showinfo("Success", "User created. Please login.")
        else:
            messagebox.showerror("Error", "User already exists")

    # ---------- PIN Lock ----------
    def show_pin_lock(self):
        window = tk.Toplevel(self.root)
        window.title("🔒 Enter App PIN")
        window.geometry("300x180")
        window.grab_set()

        tk.Label(window, text="Enter your 4-digit PIN:", font=("Arial", 12)).pack(pady=8)
        pin_entry = ttk.Entry(window, width=10, show="*")
        pin_entry.pack(pady=6)
        pin_entry.focus()

        def verify_pin():
            entered = pin_entry.get().strip()
            if entered == self.current_user.get("pin"):
                window.destroy()
                self.show_dashboard()
            else:
                messagebox.showerror("Error", "Incorrect PIN")

        ttk.Button(window, text="Enter", command=verify_pin).pack(pady=4)

        def recover_pin():
            pw = simpledialog.askstring("Recovery", "Enter your recovery password:", show="*")
            if pw == self.current_user.get("pin_recovery"):
                messagebox.showinfo("Success", f"Your PIN is: {self.current_user.get('pin')}")
            else:
                messagebox.showerror("Error", "Incorrect recovery password")
        ttk.Button(window, text="Forgot PIN?", command=recover_pin).pack(pady=4)

    # ---------- Dashboard ----------
    def show_dashboard(self):
        self.clear_screen()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard_tab = ttk.Frame(self.notebook)
        self.calendar_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.calendar_tab, text="Monthly Points")

        # Header
        header = ttk.Frame(self.dashboard_tab, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text=f"Welcome, {self.current_user['username']}!", style="Header.TLabel").pack(side="left")
        ttk.Button(header, text="Logout", command=self.logout).pack(side="right")
        ttk.Button(header, text="⚙", command=self.show_settings).pack(side="right", padx=8)

        # Top stats
        top_frame = ttk.Frame(self.dashboard_tab, padding=12)
        top_frame.pack(fill="x")
        self.points_var = tk.StringVar()
        self.level_var = tk.StringVar()
        self.streak_var = tk.StringVar()
        ttk.Label(top_frame, textvariable=self.points_var, font=("Arial", 14)).grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Label(top_frame, textvariable=self.level_var, font=("Arial", 14)).grid(row=0, column=1, sticky="w", padx=6, pady=6)
        ttk.Label(top_frame, textvariable=self.streak_var, font=("Arial", 14)).grid(row=0, column=2, sticky="w", padx=6, pady=6)

        # Recent activity
        middle = ttk.Frame(self.dashboard_tab, padding=(12,8))
        middle.pack(fill="both", expand=False)
        ttk.Label(middle, text="Recent Activity:", font=("Arial", 12, "bold")).pack(anchor="w")
        self.recent_box = tk.Text(middle, height=6, width=80, state="disabled")
        self.recent_box.pack(pady=(6,0))

        # Log habits
        bottom = ttk.Frame(self.dashboard_tab, padding=12)
        bottom.pack(fill="both", expand=True)
        ttk.Label(bottom, text="Log a Habit (click):", font=("Arial", 12, "bold")).pack(anchor="w")
        habit_templates = build_habit_list()
        good_habits_frame = ttk.LabelFrame(bottom, text="Good Habits", padding=10)
        good_habits_frame.pack(side="left", fill="both", expand=True, padx=(0,6))
        bad_habits_frame = ttk.LabelFrame(bottom, text="Bad Habits", padding=10)
        bad_habits_frame.pack(side="left", fill="both", expand=True, padx=(6,0))
        today = datetime.date.today().isoformat()
        user_logs_today = [l['habit'] for l in get_logs_for_user(self.current_user['username']) if l['date'] == today]

        self.habit_buttons = {}  # Store buttons to update later

        for h in habit_templates:
            color = "#E6F0FF" if h["type"] == "good" else "#FFE6E6"
            frame = good_habits_frame if h["type"] == "good" else bad_habits_frame
            btn = tk.Button(frame, text=f"{h['habit']} ({h['points']} pts)",
                            command=lambda name=h['habit']: self.handle_habit_click(name),
                            bg=color, fg="black", font=("Arial", 12), width=20, height=2,
                            relief="flat", bd=0, activebackground=color)
            btn.pack(pady=4, padx=4, fill="x")

            # Disable button if already logged today
            if h['habit'] in user_logs_today:
                btn.config(state="disabled", bg="#D3D3D3")  # greyed out

            self.habit_buttons[h['habit']] = btn  # store reference for later


        action_frame = ttk.Frame(bottom)
        action_frame.pack(pady=8, anchor="w")
        ttk.Button(action_frame, text="Undo Last Habit", command=self.handle_undo_last).pack(side="left", padx=6)
        

        
        self.chart_holder = ttk.Frame(bottom)
        self.chart_holder.pack(fill="both", expand=True)

        self.refresh_dashboard()


    # ---------- Settings ----------
    def show_settings(self):
        #self.clear_screen()
        window = tk.Toplevel(self.root)
        window.title("⚙ Settings")
        window.geometry("500x450")
        window.grab_set()

        ttk.Label(window, text="Settings", font=("Arial", 16, "bold")).pack(pady=10)

        # Option to choose between PIN and Habit
        option_var = tk.StringVar(value="pin")
        ttk.Radiobutton(window, text="App Lock PIN", variable=option_var, value="pin").pack(anchor="w", padx=20)
        ttk.Radiobutton(window, text="Add/Edit Habits", variable=option_var, value="habit").pack(anchor="w", padx=20)

        content_frame = ttk.Frame(window, padding=12)
        content_frame.pack(fill="both", expand=True)

        def refresh_content(*args):
            for w in content_frame.winfo_children():
                w.destroy()
            if option_var.get() == "pin":
                self.build_pin_settings(content_frame)
            else:
                self.build_habit_settings(content_frame)
        option_var.trace_add("write", refresh_content)
        refresh_content()

    def build_pin_settings(self, frame):
        # App lock section
        lock_frame = ttk.LabelFrame(frame, text="App Lock PIN", padding=10)
        lock_frame.pack(fill="x", pady=10)
        ttk.Label(lock_frame, text="Set 4-digit PIN:").pack(anchor="w")
        pin_entry = ttk.Entry(lock_frame, width=10, show="*")
        pin_entry.pack(anchor="w", pady=4)
        ttk.Label(lock_frame, text="Recovery Password:").pack(anchor="w")
        rec_entry = ttk.Entry(lock_frame, width=20, show="*")
        rec_entry.pack(anchor="w", pady=4)

        def save_pin():
            pin = pin_entry.get().strip()
            rec = rec_entry.get().strip()
            if not pin or not rec:
                messagebox.showerror("Error", "PIN and Recovery Password required")
                return
            if len(pin) != 4 or not pin.isdigit():
                messagebox.showerror("Error", "PIN must be 4 digits")
                return
            users_collection.update_one({"username": self.current_user["username"]},
                                        {"$set": {"pin": pin, "pin_recovery": rec}})
            messagebox.showinfo("Success", "PIN set successfully")
            self.current_user = get_user_stats(self.current_user["username"])
        ttk.Button(lock_frame, text="Save PIN", command=save_pin).pack(pady=6)
        def remove_pin():
            users_collection.update_one({"username": self.current_user["username"]},
                                        {"$set": {"pin": None, "pin_recovery": None}})
            messagebox.showinfo("Success", "PIN removed")
            self.current_user = get_user_stats(self.current_user["username"])
        ttk.Button(lock_frame, text="Remove PIN", command=remove_pin).pack(pady=2)

    def build_habit_settings(self, frame):
        habit_frame = ttk.LabelFrame(frame, text="Add or Edit Habits", padding=10)
        habit_frame.pack(fill="both", expand=True)

        ttk.Label(habit_frame, text="Habit Name:").pack(anchor="w", pady=2)
        habit_name_entry = ttk.Entry(habit_frame, width=30)
        habit_name_entry.pack(anchor="w", pady=2)
        ttk.Label(habit_frame, text="Points (use negative for bad habits):").pack(anchor="w", pady=2)
        points_entry = ttk.Entry(habit_frame, width=10)
        points_entry.pack(anchor="w", pady=2)

        habit_type_var = tk.StringVar(value="good")
        ttk.Radiobutton(habit_frame, text="Good Habit", variable=habit_type_var, value="good").pack(anchor="w")
        ttk.Radiobutton(habit_frame, text="Bad Habit", variable=habit_type_var, value="bad").pack(anchor="w")

        def add_or_update_habit():
            name = habit_name_entry.get().strip()
            pts = points_entry.get().strip()
            if not name or not pts:
                messagebox.showerror("Error", "Provide habit name and points")
                return
            try:
                pts = int(pts)
            except:
                messagebox.showerror("Error", "Points must be an integer")
                return
            habit_type = habit_type_var.get()
            existing = habits_collection.find_one({"habit": name})
            if existing:
                habits_collection.update_one({"habit": name}, {"$set": {"points": pts, "type": habit_type}})
                messagebox.showinfo("Updated", f"Habit '{name}' updated")
            else:
                habits_collection.insert_one({"habit": name, "points": pts, "type": habit_type})
                messagebox.showinfo("Added", f"Habit '{name}' added")
        ttk.Button(habit_frame, text="Save Habit", command=add_or_update_habit).pack(pady=6)

    # ---------- Monthly Calendar ----------
    def show_monthly_calendar(self):
        for w in self.calendar_tab.winfo_children():
            w.destroy()
        nav_frame = ttk.Frame(self.calendar_tab)
        nav_frame.pack(fill="x", pady=8)
        ttk.Button(nav_frame, text="◀", command=lambda: self.change_month(-1)).pack(side="left", padx=8)
        month_name = datetime.date(self.displayed_year, self.displayed_month, 1).strftime("%B %Y")
        ttk.Label(nav_frame, text=month_name, font=("Arial", 16, "bold")).pack(side="left", padx=8)
        today = datetime.date.today()
        if (self.displayed_year < today.year) or (self.displayed_year == today.year and self.displayed_month < today.month):
            ttk.Button(nav_frame, text="▶", command=lambda: self.change_month(1)).pack(side="left", padx=8)

        cal_frame = tk.Frame(self.calendar_tab, bg="#F5F5F5")
        cal_frame.pack(fill="both", expand=True, padx=12, pady=12)

        logs = get_logs_for_user(self.current_user["username"])
        logs_by_date = {}
        for l in logs:
            date = datetime.date.fromisoformat(l["date"])
            if date.year == self.displayed_year and date.month == self.displayed_month:
                logs_by_date.setdefault(date, []).append(l)

        days_of_week = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
        for i, day in enumerate(days_of_week):
            tk.Label(cal_frame, text=day, font=("Arial", 12, "bold"), bg="#F5F5F5").grid(row=0, column=i, padx=2, pady=2, sticky="nsew")

        first_weekday, days_in_month = monthrange(self.displayed_year, self.displayed_month)
        row = 1
        col = first_weekday

        for day in range(1, days_in_month+1):
            current_date = datetime.date(self.displayed_year, self.displayed_month, day)
            day_logs = logs_by_date.get(current_date, [])
            total_points = sum(l["points"] for l in day_logs)
            
            if current_date > today:
                bg_color = "#FFFFFF"  # future days
            elif not day_logs:
                bg_color = "#FFFACD"  # no logs
            else:
                if total_points < 45:
                    bg_color = "#FF9999"  # Slight Red
                elif 45 <= total_points <= 60:
                    bg_color = "#ADD8E6"  # Blue
                elif total_points > 60:
                    bg_color = "#98FB98"  # Slight Green
                else:
                    bg_color = "#FFB6B6"  # fallback light red

            card = tk.Frame(cal_frame, bg=bg_color, bd=1, relief="raised")
            card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            tk.Label(card, text=str(day), font=("Arial", 14, "bold"), bg=bg_color).pack(padx=4, pady=4)
            if day_logs:
                tk.Label(card, text=f"{total_points:+} pts", font=("Arial", 10), bg=bg_color).pack(padx=4, pady=2)
            card.bind("<Button-1>", lambda e, d=current_date: self.show_day_logs(d))

            cal_frame.grid_rowconfigure(row, weight=1)
            cal_frame.grid_columnconfigure(col, weight=1)
            col += 1
            if col > 6:
                col = 0
                row += 1



    def change_month(self, delta):
        new_month = self.displayed_month + delta
        new_year = self.displayed_year
        if new_month < 1:
            new_month = 12
            new_year -= 1
        elif new_month > 12:
            new_month = 12
        today = datetime.date.today()
        if new_year > today.year or (new_year == today.year and new_month > today.month):
            return
        self.displayed_month = new_month
        self.displayed_year = new_year
        self.show_monthly_calendar()

    # ---------- Day Logs ----------
    def show_day_logs(self, date):
        logs = get_logs_for_user(self.current_user["username"])
        day_logs = [l for l in logs if datetime.date.fromisoformat(l["date"]) == date]
        window = tk.Toplevel(self.root)
        window.title(f"Habits for {date.isoformat()}")
        for l in day_logs:
            habit = habits_collection.find_one({"habit": l["habit"]})
            color = "#ADD8E6" if habit["type"] == "good" else "#FFB6B6"
            frame = tk.Frame(window, bg=color, padx=8, pady=6)
            frame.pack(fill="x", padx=12, pady=4)
            tk.Label(frame, text=f"{l['habit']} ({l['points']} pts)", bg=color, font=("Arial", 12)).pack(anchor="w")

    # ---------- Utility ----------
    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def logout(self):
        self.clear_remembered_user()
        self.current_user = None
        self.show_login_screen()

    def refresh_dashboard(self):
        self.current_user = get_user_stats(self.current_user["username"])
        pts = self.current_user.get("points", 0)
        lvl = self.current_user.get("level", 1)
        streak = self.current_user.get("streak", 0)
        self.points_var.set(f"Points: {pts}")
        self.level_var.set(f"Level: {lvl}")
        self.streak_var.set(f"Streak: {streak}")

        recent_logs = get_logs_for_user(self.current_user["username"], limit=5)
        self.recent_box.config(state="normal")
        self.recent_box.delete("1.0", tk.END)
        for l in recent_logs:
            self.recent_box.insert(tk.END, f"{l['date']}: {l['habit']} ({l['points']} pts)\n")
        self.recent_box.config(state="disabled")

        # Ensure habit buttons and today's chart reflect the latest DB state.
        try:
            # Update button enabled/disabled states based on today's logs
            self.update_habit_buttons_state()
        except Exception:
            # Fail-safe: don't crash UI if update fails
            pass

        try:
            # Update the daily pie chart (if any logs for today)
            self.update_daily_pie_chart()
        except Exception:
            pass

        # Refresh the monthly calendar (rebuilds calendar tiles)
        self.show_monthly_calendar()
    def handle_habit_click(self, habit_name):
        today = datetime.date.today().isoformat()
        logs = get_logs_for_user(self.current_user["username"])
        
        # Prevent double logging
        for l in logs:
            if l['habit'] == habit_name and l['date'] == today:
                messagebox.showinfo("Already Logged", f"You've already logged '{habit_name}' today!")
                return

        # Log the habit
        add_habit_log_for_user(self.current_user["username"], habit_name)
        self.refresh_dashboard()
        self.update_daily_pie_chart()

        # Disable the button after logging
        if habit_name in self.habit_buttons:
            self.habit_buttons[habit_name].config(state="disabled", bg="#D3D3D3")


    def handle_undo_last(self):
        # Undo the last habit
        undone = undo_last_habit_log(self.current_user["username"])
        if undone:
            self.refresh_dashboard()
            self.update_daily_pie_chart()
            self.update_habit_buttons_state()

    def update_habit_buttons_state(self):
        today = datetime.date.today().isoformat()
        user_logs_today = [l['habit'] for l in get_logs_for_user(self.current_user['username']) if l['date'] == today]

        for habit, btn in getattr(self, 'habit_buttons', {}).items():
            if habit in user_logs_today:
                btn.config(state="disabled", bg="#D3D3D3")
            else:
                # Enable it if not logged today
                h = habits_collection.find_one({"habit": habit})
                color = "#E6F0FF" if h["type"] == "good" else "#FFE6E6"
                btn.config(state="normal", bg=color)




    def update_daily_pie_chart(self):
            # Clear previous chart
            for widget in self.chart_holder.winfo_children():
                widget.destroy()

            today = datetime.date.today()
            logs = get_logs_for_user(self.current_user["username"])
            today_logs = [l for l in logs if datetime.date.fromisoformat(l["date"]) == today]

            if not today_logs:
                return  # Nothing to show

            good_count = sum(1 for l in today_logs if habits_collection.find_one({"habit": l["habit"]})["type"] == "good")
            bad_count = sum(1 for l in today_logs if habits_collection.find_one({"habit": l["habit"]})["type"] == "bad")

            fig = Figure(figsize=(3,3), dpi=80)
            ax = fig.add_subplot(111)
            ax.pie([good_count, bad_count], labels=["Good", "Bad"], colors=["#ADD8E6","#FFB6B6"], autopct='%1.0f%%')
            ax.set_title("Today's Habits")

            canvas = FigureCanvasTkAgg(fig, master=self.chart_holder)
            canvas.draw()
            canvas.get_tk_widget().pack()


# ---------------- Run App ----------------
root = tk.Tk()
app = HabitGameApp(root)
threading.Thread(target=run_scheduler, daemon=True).start()
root.mainloop()
