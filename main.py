"""SinoPac AutoReply - Entry point."""

import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.dirname(__file__))


def main():
    from src.utils.logger import setup_logger
    from config import DB_PATH

    # Initialize logging
    setup_logger()

    # Initialize database
    from src.data.database import Database
    db = Database(DB_PATH)
    db.initialize()

    # Launch GUI
    from src.gui.app import App
    app = App(db)
    app.mainloop()


if __name__ == "__main__":
    main()
