# Habit Tracker 🎮

**Habit Tracker** is a Python desktop application designed to gamify your daily habits. Track good and bad habits, earn points, maintain streaks, and visualize your progress with an intuitive dashboard and monthly calendar view.

---

## 🌟 Featuress

- **User Management:** Login, signup, and "Remember Me" functionality  
- **Habit Tracking:** Log good and bad habits with a points system  
- **Undo Logs:** Undo the last logged habit if needed  
- **Gamification:** Earn points and level up based on your habits  
- **PIN Lock Security:** Optional 4-digit PIN and recovery password  
- **Settings:** Add or edit habits dynamically  
- **Visualization:** Monthly calendar and daily habit pie chart  
- **Customizable Resources:** Add background images, logos, and icons  

---

## 🛠️ Prerequisites

- Python ≥ 3.10  
- Git  
- MongoDB (local instance running at `mongodb://localhost:27017/`)  

---

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/anokhgnair/Habit-Tracker.git
cd Habit-Tracker
```
### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
### 3. Run the App
```bash
python Habit_Tracker.py
```

## ⚡ Create a Standalone Executable (.exe) on Windows

### 1. Install PyInstaller
```bash
pip install pyinstaller
```
### 2. Prepare Resources
```bash
icon_path = resource_path("resources/logo.ico")
```
### 3. Generate (.exe)
```bash
pyinstaller --onefile --windowed --icon=resources/my_icon.ico Habit_Tracker.py
```
## Notes
- Ensure MongoDB is running locally (mongodb://localhost:27017/) before starting the app.
- All user data and habit logs are stored in the MongoDB collections.
- Customize backgrounds, icons, and other resources in the resources folder for branding.
