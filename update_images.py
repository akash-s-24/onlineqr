import os
import shutil
import sqlite3

images_dir = "images-of-events"
dest_dir = "static/images"

# Mapping from image filename (without extension) to exact Event Name in DB
mapping = {
    "Beatboxing": "Beat Boxing",
    "Content Creator": "Content Creator",
    "Photography": "Photography",
    "Solo Dance": "Solo Dance",
    "Tech Quiz": "Tech Quiz",
    "bgmi": "BGMI",
    "facepanting": "Face Painting",
    "freefire": "Free Fire",
    "get the shield": "Get the Shield",
    "groupdance": "Group Dance",
    "mad adds": "Mad Adds",
    "monoacting": "Mono Acting",
    "pencilesketch": "Pencil Sketch",
    "rampwalk": "Ramp Walk"
}

# Ensure destination directory exists
os.makedirs(dest_dir, exist_ok=True)

conn = sqlite3.connect('eventmate.db')
cursor = conn.cursor()

for img_file in os.listdir(images_dir):
    if not os.path.isfile(os.path.join(images_dir, img_file)):
        continue
    
    name_without_ext, ext = os.path.splitext(img_file)
    event_name = mapping.get(name_without_ext)
    
    if event_name:
        # Copy file
        src_path = os.path.join(images_dir, img_file)
        dest_path = os.path.join(dest_dir, img_file)
        shutil.copy2(src_path, dest_path)
        
        # Update database
        cursor.execute("UPDATE events SET banner_image = ? WHERE event_name = ?", (img_file, event_name))
        
        # Also fix the "Python Test Update String" back to "BGMI"
        if event_name == "BGMI":
            cursor.execute("UPDATE events SET event_name = 'BGMI', banner_image = ? WHERE id = 1", (img_file,))
        
        print(f"Updated {event_name} with {img_file}")
    else:
        print(f"No mapping found for {img_file}")

conn.commit()
conn.close()
print("Done")
