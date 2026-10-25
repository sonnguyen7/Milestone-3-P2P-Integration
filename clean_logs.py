import os
import glob

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

def clean_logs():
    if not os.path.exists(LOG_DIR):
        print("No logs directory found.")
        return

    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
    if not log_files:
        print("Logs directory is already empty.")
        return

    for file_path in log_files:
        try:
            os.remove(file_path)
            print(f"Removed: {os.path.basename(file_path)}")
        except OSError as e:
            print(f"Could not delete {os.path.basename(file_path)} (is a process still running?): {e}")

    print("\nLogs cleaned successfully.")

if __name__ == "__main__":
    clean_logs()