import base64
import os

def generate_visible_assets():
    # 64x64 Solid White PNG
    white_64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAAAAACPAi4CAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAADVJREFUeNrs"
        "zEERAAAIA6D9S/uXm+A7mAMpYOfR6vV6vV6vV6vV6vV6vV6vV6vV6vV6vV6vV78FGABy8U9pOnS9SwAAAABJRU5ErkJggg=="
    )

    # 64x64 Solid Black PNG
    black_64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAAAAACPAi4CAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAADVJREFUeNrs"
        "zEERAAAIA6At/6VNcB98IAXszKPV6/V6vV6vV6vV6vV6vV6vV6vV6vV6vV6vV68FGAD6pU9pXoO0zgAAAABJRU5ErkJggg=="
    )

    assets = {
        "white.png": white_64,
        "black.png": black_64
    }

    # Get the directory where the script is running
    current_dir = os.path.dirname(os.path.abspath(__file__))

    for filename, b64_data in assets.items():
        file_path = os.path.join(current_dir, filename)
        with open(file_path, "wb") as f:
            f.write(base64.b64decode(b64_data))
        print(f"Created: {file_path} ({os.path.getsize(file_path)} bytes)")

    print("\nVerification: You should now see a solid White square and a solid Black square in your folder.")

if __name__ == "__main__":
    generate_visible_assets()
