<div align="center">
  
  # 🎓 ST Affichage
  
  **A seamless, real-time announcement platform for students of the ST Faculty (Univ Bejaïa).**
  
  [![Version](https://img.shields.io/badge/Version-1.9.9%20Beta-8B5CF6?style=for-the-badge)](https://stbejaia.up.railway.app/)
  [![Python](https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![Flask](https://img.shields.io/badge/Flask-Secure-black?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![Tailwind](https://img.shields.io/badge/Tailwind_CSS-Modern-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)

  > *An independent student-led initiative to modernize university communications.*

</div>

---

## ⚡ Overview

**ST Affichage** is a highly optimized, automated scraper and web application designed to bridge the gap between the university's Moodle e-learning platform and student accessibility. 

Instead of forcing students to repeatedly log into a clunky web interface, this application autonomously monitors the university's announcement board in the background, extracts vital information (text, PDFs, images), and delivers it via a beautiful, native-feeling mobile interface with **real-time push notifications**.

## ✨ Key Features

*   **🔄 Autonomous Scraping Engine:** Runs a continuous background thread that polls the Moodle HTML, intelligently extracting and cleaning data, links, and images while ignoring system UI junk.
*   **🔔 Push Notifications:** Integrated with Firebase Cloud Messaging (FCM). When a new announcement is detected, a high-priority alert is instantly broadcasted to all users.
*   **📱 Premium Glassmorphism UI:** A sleek, dark-mode-exclusive interface built with Tailwind CSS, featuring heavy background blurs (`backdrop-filter`), smooth hardware-accelerated animations, and modern typography (Inter & Syne).
*   **🔗 Hybrid Share System:** Uses the native Web Share API on browsers, and automatically falls back to an intelligent Custom Share Sheet with deep-linking (`tg://`, `whatsapp://`) when running inside the Android APK WebView.
*   **🛡️ Robust Security:** Implements IP Rate Limiting (`Flask-Limiter`) and strict Content Security Policy (CSP) headers to prevent XSS and DDoS attacks.

---

## 🛠️ Tech Stack

**Backend Architecture**
*   **Python 3** (Core Logic)
*   **Flask** (API & Routing)
*   **BeautifulSoup4 & Bleach** (HTML Parsing & Sanitization)
*   **Firebase Admin SDK** (Push Notifications)
*   **Gunicorn** (Production WSGI Server)

**Frontend Architecture**
*   **HTML5 / Vanilla JavaScript** (Zero heavy frameworks, blazing fast)
*   **Tailwind CSS** (Utility-first styling)
*   **Google Fonts** (Syne for headings, Inter for readability)

---

## 🚀 How It Works

1.  **Background Polling:** Every 10 minutes, a daemon thread fetches the target Moodle URL.
2.  **Parsing & Hashing:** Beautiful Soup extracts `li.activity` nodes. The raw text is hashed via SHA-256 to create a unique ID.
3.  **Sanitization:** `bleach` safely strips malicious or broken HTML tags, preserving only safe formatting (`<b>`, `<i>`, `<br>`).
4.  **State Comparison:** If a new SHA-256 hash is detected that wasn't in the previous cycle, the app triggers the `send_fcm_notification` function.
5.  **Client Fetch:** The frontend dynamically fetches the `/api/announcements` endpoint and paints the UI using pure JavaScript DOM manipulation.

---

## ⚙️ Installation & Local Setup

If you wish to run this project locally for development or testing:

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/st-affichage.git
cd st-affichage
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file in the root directory. You will need your Firebase Service Account JSON credentials.
```env
FIREBASE_CREDENTIALS={"type": "service_account", "project_id": "...", ...}
ADMIN_PASSWORD=your_secure_password
PORT=5000
```

### 5. Run the Application
```bash
python app.py
```
The app will be available at `http://localhost:5000`.

---

## 📡 API Reference

### `GET /api/announcements`
Returns the latest scraped announcements in JSON format. Sorted by timestamp (Newest first).

**Response (Example):**
```json
[
  {
    "id": "e4d909c290d0fb1c",
    "title": "Avis aux étudiants des groupes H8, D6",
    "body": "Interrogation N° 02 du module de chimie 02...",
    "date": "16 Avril 2026",
    "timestamp": 1776340800.0,
    "images": ["https://elearning.univ-bejaia.dz/.../image.png"],
    "links": ["https://elearning.univ-bejaia.dz/.../document.pdf"],
    "source": "https://elearning.univ-bejaia.dz/course/view.php?id=19989#module-12345"
  }
]
```

---

## 👨‍💻 Developer & Credits

Designed, developed, and maintained independently by **Adam Mila**. 

This application is an independent initiative to help students and is not officially affiliated with the administration of Université de Bejaïa.

*For bug reports, feature requests, or collaboration, please reach out via [Instagram](https://www.instagram.com/_adam_mila_?igsh=MTJ1em5kN3dneHlnNQ==) or Email.*

---
<p align="center">
  <i>Built with ❤️ for the students.</i>
</p>
```
