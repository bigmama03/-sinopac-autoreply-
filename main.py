"""SinoPac AutoReply - Entry point."""

import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.dirname(__file__))


def _show_splash():
    """Show a lightweight splash screen while the app loads.

    Uses a hidden Tk root + Toplevel so CTk can later create its own root
    without conflicting with an existing Tk() instance.
    """
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # Hide the root — CTk will create its own

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#0F1A2E")

    width, height = 380, 200
    x = (root.winfo_screenwidth() - width) // 2
    y = (root.winfo_screenheight() - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")

    # Gold accent line
    tk.Frame(splash, bg="#D4A843", height=3).pack(fill="x")

    tk.Label(
        splash, text="永豐金證券", font=("Helvetica", 20, "bold"),
        bg="#0F1A2E", fg="#FFFFFF",
    ).pack(pady=(30, 5))
    tk.Label(
        splash, text="社群自動回覆系統", font=("Helvetica", 12),
        bg="#0F1A2E", fg="#A0AEC0",
    ).pack()
    tk.Label(
        splash, text="載入中...", font=("Helvetica", 10),
        bg="#0F1A2E", fg="#718096",
    ).pack(pady=(20, 0))

    splash.update()
    return root  # Return root so we can destroy the entire Tk instance


def main():
    from src.utils.logger import setup_logger
    from config import DB_PATH

    # Show splash screen immediately
    splash = _show_splash()

    # Initialize logging
    setup_logger()

    # Initialize database
    from src.data.database import Database
    db = Database(DB_PATH)
    db.initialize()

    # Launch GUI
    from src.gui.app import App
    app = App(db)

    # Close splash after app window is ready
    splash.destroy()

    app.mainloop()


if __name__ == "__main__":
    main()
