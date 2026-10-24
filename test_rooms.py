
from main import find_available_rooms

rooms = find_available_rooms(
    "Taj Hotel",
    "2026-10-25",
    "2026-10-26"
)

print("Available rooms:")
for room in rooms:
    print(room)
